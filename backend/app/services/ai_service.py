# backend/app/services/ai_service.py
"""
AI Service — multi-provider with fallback chain.
Extraction structurée de CV (prompt strict) et délégation du scoring à scoring_service.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any

import google.generativeai as genai
import requests

from app.config import get_settings
from app.services.cv_extractor import CVExtractor
from app.services.scoring_service import compute_candidate_score

logger = logging.getLogger(__name__)

MAX_CV_TEXT_LENGTH = 8_000


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict:
    if not text:
        raise ValueError("Réponse de l'IA vide")

    clean = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()

    if clean.startswith("["):
        clean = clean[1 : clean.rfind("]")]

    try:
        return json.loads(clean)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse error — first 200 chars: %s", clean[:200])
        raise ValueError(f"Invalid JSON from AI provider: {exc}") from exc


def _normalize_extracted_cv(data: dict[str, Any]) -> dict[str, Any]:
    """Harmonise les clés renvoyées par l'IA avec le schéma attendu par le pipeline."""
    normalized = dict(data)

    if not normalized.get("current_position"):
        normalized["current_position"] = (
            normalized.pop("extracted_title", None)
            or normalized.pop("title", None)
        )

    if normalized.get("experience_years") is None:
        years = normalized.pop("years_of_experience", None)
        if years is not None:
            normalized["experience_years"] = years

    normalized.setdefault("full_name", None)
    normalized.setdefault("email", None)
    normalized.setdefault("phone", None)
    normalized.setdefault("current_position", None)
    normalized.setdefault("skills", [])
    normalized.setdefault("experience_years", None)
    normalized.setdefault("summary", None)
    normalized.setdefault("work_history", [])
    normalized.setdefault("projects", [])
    normalized.setdefault("certifications", [])
    normalized.setdefault("education", [])
    normalized.setdefault("languages", [])

    return normalized


# ---------------------------------------------------------------------------
# Provider calls
# ---------------------------------------------------------------------------

def _call_gemini(prompt: str, settings) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("Missing Gemini API key")
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    return response.text


def _call_nvidia(prompt: str, settings) -> str:
    if not settings.nvidia_api_key:
        raise RuntimeError("Missing NVIDIA API key")

    from openai import OpenAI

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=settings.nvidia_api_key.strip(),
    )

    completion = client.chat.completions.create(
        model="z-ai/glm-5.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=1,
        top_p=1,
        max_tokens=16384,
        stream=False,
    )

    return completion.choices[0].message.content


def _call_deepseek(prompt: str, settings) -> str:
    if not settings.deepseek_api_key:
        raise RuntimeError("Missing DeepSeek API key")
    response = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.deepseek_api_key.strip()}",
            "Content-Type": "application/json",
        },
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _call_mistral(prompt: str, settings) -> str:
    if not settings.mistral_api_key:
        raise RuntimeError("Missing Mistral API key")
    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.mistral_api_key.strip()}",
            "Content-Type": "application/json",
        },
        json={
            "model": "mistral-small-latest",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _call_github_models(prompt: str, settings) -> str:
    if not settings.github_token:
        raise RuntimeError("Missing GitHub token")
    response = requests.post(
        "https://models.inference.ai.azure.com/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.github_token.strip()}",
            "Content-Type": "application/json",
        },
        json={
            "model": "deepseek/deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


_PROVIDERS = [
    ("NVIDIA", _call_nvidia),
    ("DeepSeek", _call_deepseek),
    ("Mistral", _call_mistral),
    ("Gemini", _call_gemini),
    ("GitHub Models", _call_github_models),
]


def _generate_with_fallback(prompt: str) -> str:
    settings = get_settings()
    for name, fn in _PROVIDERS:
        try:
            return fn(prompt, settings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s failed: %s", name, exc)
    raise RuntimeError("All AI providers failed — no response available.")


# ---------------------------------------------------------------------------
# CV depth analysis
# ---------------------------------------------------------------------------

_CV_DEPTH_PROMPT = """
You are a senior auditor and expert recruiter. Today's date is {today}.
Analyze the provided structured CV data for DEPTH and EVIDENCE.

CRITICAL RULES:
1. METRIC MANDATE:
   - A 'High Quality' entry must contain at least one quantifiable metric
     (e.g., $, %, time saved, team size, revenue growth).
   - If the candidate has > 5 years of experience but NO metrics in their
     recent roles, the 'overall_depth_score' MUST be capped at 40/100.

2. SCORING PENALTIES (Start from 100):
   - Subtract 5 points for every entry in 'missing_metrics'.
   - Subtract 5 points for every entry in 'weak_descriptions'.
   - Subtract 4 points for every unexplained 'employment_gap' > 3 months.
   - Floor the final score at 0.

Return ONLY the following JSON object:
{{
  "overall_depth_score": <int 0-100>,
  "missing_metrics": [],
  "weak_descriptions": [],
  "employment_gaps": [],
  "summary": "Strict, 2-3 sentence assessment of the CV's depth and professional quality."
}}

Structured CV data:
{cv_json}
"""


def analyze_cv_depth(cv_data: dict[str, Any]) -> dict[str, Any]:
    today = date.today().strftime("%Y-%m")
    slim = {
        "work_history": cv_data.get("work_history", []),
        "projects": cv_data.get("projects", []),
        "experience_years": cv_data.get("experience_years"),
        "summary": cv_data.get("summary"),
    }
    prompt = _CV_DEPTH_PROMPT.format(
        today=today,
        cv_json=json.dumps(slim, ensure_ascii=False, indent=2),
    )

    try:
        raw = _generate_with_fallback(prompt)
        report = _parse_json_response(raw)
        report.setdefault("overall_depth_score", 0)
        report.setdefault("missing_metrics", [])
        report.setdefault("weak_descriptions", [])
        report.setdefault("employment_gaps", [])
        report.setdefault("summary", "")
        return report
    except Exception as exc:
        logger.error("CV depth analysis failed: %s", exc)
        return {
            "overall_depth_score": None,
            "missing_metrics": [],
            "weak_descriptions": [],
            "employment_gaps": [],
            "summary": "Depth analysis unavailable.",
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_cv_info(raw_text: str) -> dict[str, Any]:
    """
    Parse raw CV text into a structured dict via prompt strict (CVExtractor).
    Falls back to a minimal safe dict if all providers fail.
    """
    prompt = CVExtractor.build_strict_extraction_prompt(raw_text[:MAX_CV_TEXT_LENGTH])
    try:
        response_text = _generate_with_fallback(prompt)
        data = _normalize_extracted_cv(_parse_json_response(response_text))
        return data
    except Exception as exc:  # noqa: BLE001
        logger.error("CV extraction failed: %s", exc)
        return _normalize_extracted_cv({})


def score_candidate(
    cv_data: dict[str, Any],
    job_title: str,
    job_requirements: str,
) -> dict[str, Any]:
    """Délègue au scorer hiérarchique (compatibilité tests / tasks)."""
    return compute_candidate_score(
        cv_data=cv_data,
        job_title=job_title,
        job_requirements=job_requirements,
    )


def compute_final_score(
    cv_data: dict[str, Any],
    job_title: str,
    job_requirements: str,
) -> float:
    """Score blend : 70 % pertinence poste + 30 % profondeur CV."""
    depth_report = analyze_cv_depth(cv_data)
    quality_score = float(depth_report.get("overall_depth_score") or 0)
    quality_score = max(0.0, min(100.0, quality_score))

    score_result = compute_candidate_score(
        cv_data=cv_data,
        job_title=job_title,
        job_requirements=job_requirements,
    )
    relevance_score = float(score_result.get("score", 0))
    relevance_score = max(0.0, min(100.0, relevance_score))

    return round(relevance_score * 0.70 + quality_score * 0.30, 2)
