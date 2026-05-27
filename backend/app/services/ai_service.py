# backend/app/services/ai_service.py
"""
AI Service — multi-provider with fallback chain.
Extracts structured CV data and delegates scoring to scoring_service.
"""
from __future__ import annotations

import json
import re
from typing import Any

import requests
import google.generativeai as genai

from app.config import get_settings
from app.services.scoring_service import compute_candidate_score


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict:
    if not text:
        raise ValueError("Empty AI response")

    clean = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()

    if clean.startswith("["):
        clean = clean[1 : clean.rfind("]")]

    try:
        return json.loads(clean)
    except json.JSONDecodeError as exc:
        print(f"[ai_service] JSON parse error — first 200 chars: {clean[:200]}")
        raise ValueError(f"Invalid JSON from AI provider: {exc}") from exc


# ---------------------------------------------------------------------------
# Provider calls
# ---------------------------------------------------------------------------

def _call_gemini(prompt: str, settings) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("Missing Gemini API key")
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content(prompt)
    return response.text


def _call_openrouter(prompt: str, settings) -> str:
    if not settings.openrouter_api_key:
        raise RuntimeError("Missing OpenRouter API key")
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key.strip()}",
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


# ---------------------------------------------------------------------------
# Fallback engine
# ---------------------------------------------------------------------------

_PROVIDERS = [
    ("OpenRouter", _call_openrouter),
    ("DeepSeek",   _call_deepseek),
    ("Mistral",    _call_mistral),
    ("Gemini",     _call_gemini),
]


def _generate_with_fallback(prompt: str) -> str:
    settings = get_settings()
    for name, fn in _PROVIDERS:
        try:
            return fn(prompt, settings)
        except Exception as exc:  # noqa: BLE001
            print(f"[ai_service] {name} failed: {exc}")
    raise RuntimeError("All AI providers failed — no response available.")


# ---------------------------------------------------------------------------
# CV extraction prompt
# ---------------------------------------------------------------------------

_CV_PROMPT_TEMPLATE = """
You are an expert ATS resume parser. Extract the following structured information
from the CV text below. Return ONLY valid JSON with no extra text, preamble, or
markdown fences.

Required JSON schema:
{{
  "full_name": "string",
  "email": "string or null",
  "phone": "string or null",
  "current_position": "string or null",
  "skills": ["list of technical skills as strings"],
  "experience_years": number or null,
  "summary": "2-3 sentence professional summary or null",
  "work_history": [
    {{
      "title": "Job title",
      "company": "Company name",
      "start_date": "YYYY-MM or null",
      "end_date": "YYYY-MM or null (null = present)",
      "duration_months": number or null,
      "description": "Key responsibilities and achievements"
    }}
  ],
  "projects": [
    {{
      "name": "Project name",
      "tech": "Technologies used",
      "description": "What was built, scale, impact",
      "complexity": "low|medium|high"
    }}
  ],
  "certifications": ["list of certification names"],
  "education": [
    {{
      "degree": "Degree name",
      "institution": "School name",
      "year": number or null
    }}
  ],
  "languages": ["spoken languages"],
  "linkedin": "URL or null",
  "github": "URL or null"
}}

Rules:
- experience_years: sum of UNIQUE non-overlapping professional experience.
  If two roles overlap in time, count only the longer one.
- skills: include programming languages, frameworks, tools, platforms, methodologies.
- projects: include significant personal, open-source, or work projects.
- complexity: "high" if production/large-scale, "medium" if moderate, "low" if tutorial/small.
- work_history: always include duration_months if you can calculate it from dates.

CV Text (max 8000 chars):
{cv_text}
"""


# ---------------------------------------------------------------------------
# Public: CV extraction
# ---------------------------------------------------------------------------

def extract_cv_info(raw_text: str) -> dict[str, Any]:
    """
    Parse raw CV text into a rich structured dict.
    Falls back to a minimal safe dict if all providers fail.
    """
    prompt = _CV_PROMPT_TEMPLATE.format(cv_text=raw_text[:8000])
    try:
        response_text = _generate_with_fallback(prompt)
        data = _parse_json_response(response_text)
        data.setdefault("skills", [])
        data.setdefault("work_history", [])
        data.setdefault("projects", [])
        data.setdefault("certifications", [])
        data.setdefault("education", [])
        data.setdefault("languages", [])
        return data
    except Exception as exc:  # noqa: BLE001
        print(f"[ai_service] CV extraction failed: {exc}")
        return {
            "full_name":        None,
            "email":            None,
            "phone":            None,
            "current_position": None,
            "skills":           [],
            "experience_years": None,
            "summary":          None,
            "work_history":     [],
            "projects":         [],
            "certifications":   [],
            "education":        [],
            "languages":        [],
        }


# ---------------------------------------------------------------------------
# Public: scoring shim
# ---------------------------------------------------------------------------

def score_candidate(
    cv_data: dict[str, Any],
    job_title: str,
    job_requirements: str,
) -> dict[str, Any]:
    """
    Delegate to the intelligent scorer.

    Returns the full scoring dict from compute_candidate_score:
      {
        "score":            float,   ← 0-100, this is what callers extract
        "confidence":       float,
        "domain":           str,
        "reasoning":        str,
        "matched_keywords": list,
        "missing_keywords": list,
        "dimension_scores": dict,
      }

    Callers must extract ["score"] — never cast the whole dict to float.
    _compute_score in drive_sync.py handles this via _extract_scalar_score().
    """
    return compute_candidate_score(
        cv_data=cv_data,
        job_title=job_title,
        job_requirements=job_requirements,
    )