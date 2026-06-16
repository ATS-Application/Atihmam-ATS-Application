# backend/app/services/ai_service.py
"""
AI Service — multi-provider with fallback chain.
Extracts structured CV data and delegates scoring to scoring_service.

CV depth analysis also lives here to avoid the circular import that would
arise if scoring_service imported from ai_service (ai_service already imports
compute_candidate_score from scoring_service).
"""
from __future__ import annotations

import json
import re
from typing import Any

import requests
import google.generativeai as genai
#from google import genai

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
        stream=False,  # non-streaming to return a plain string like the original
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


# ---------------------------------------------------------------------------
# Fallback engine
# ---------------------------------------------------------------------------

_PROVIDERS = [
    ("NVIDIA", _call_nvidia),
    ("DeepSeek",   _call_deepseek),
    ("Mistral",    _call_mistral),
    ("Gemini",     _call_gemini),
    ("GitHub Models", _call_github_models)
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
      "tools": "Tools used",
      "description": "What was built, budget, scale, impact",
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
}}

Rules:
- experience_years: sum of UNIQUE non-overlapping professional experience.
  If two roles overlap in time, count only the longer one.
- skills: include programming languages, frameworks, tools, platforms, methodologies.
- projects: include significant personal, open-source, or work projects and the complexity.
- complexity: "high" if production/large-scale with metrics or numbers, "medium" if moderate, "low" if tutorial/small.
- work_history: always include duration_months if you can calculate it from dates.
- Candidates with a Master's degree are ranked above those with a BTS (Brevet de Technicien Supérieur), provided all other qualifications, skills, and experience are equal.

CV Text (max 8000 chars):
{cv_text}

"""

# ---------------------------------------------------------------------------
# CV depth analysis prompt
# ---------------------------------------------------------------------------

# NOTE: {today} was removed from the format call because the template body
# never referenced it — the variable was computed and passed but silently
# discarded, which caused confusion.  The prompt now makes today's date
# available to the model through a dedicated header line instead.
_CV_DEPTH_PROMPT = """
You are a senior auditor and expert recruiter. Today's date is {today}.
Analyze the provided structured CV data for DEPTH and EVIDENCE.

CRITICAL RULES:
1. METRIC MANDATE:
   - A 'High Quality' entry must contain at least one quantifiable metric
     (e.g., $, %, time saved, team size, revenue growth).
   - If the candidate has > 5 years of experience but NO metrics in their
     recent roles, the 'overall_depth_score' MUST be capped at 40/100,
     regardless of job titles.

2. SCORING PENALTIES (Start from 100):
   - Subtract 5 points for every entry in 'missing_metrics'.
   - Subtract 5 points for every entry in 'weak_descriptions'.
   - Subtract 4 points for every unexplained 'employment_gap' > 3 months.
   - Floor the final score at 0.

3. FLAG DEFINITIONS:
   - missing_metrics: Flag any work_history/project entry where the description
     lacks numbers, percentages, currency, or team sizes.
   - weak_descriptions: Flag any entry under 60 words OR that lists generic
     duties (e.g., "Managed team X") without specific achievements or outcomes.

Return ONLY the following JSON object:
{{
  "overall_depth_score": <int 0-100>,
  "missing_metrics": [
    {{"section": "work_history|projects", "entry": "string", "issue": "string", "suggestion": "string"}}
  ],
  "weak_descriptions": [
    {{"section": "work_history|projects", "entry": "string", "issue": "string", "suggestion": "string"}}
  ],
  "employment_gaps": [
    {{"from": "YYYY-MM", "to": "YYYY-MM", "duration_months": <int>, "note": "string"}}
  ],
  "summary": "Strict, 2-3 sentence assessment of the CV's depth and professional quality."
}}

Structured CV data:
{cv_json}

"""


def analyze_cv_depth(cv_data: dict[str, Any]) -> dict[str, Any]:
    """
    Assess the depth and completeness of a parsed CV.

    Expects cv_data as returned by extract_cv_info() (or a CV row from the DB
    with ai_extracted_data already parsed).

    Returns a CvDepthReport dict:
      {
        "overall_depth_score": int,        # 0-100
        "missing_metrics":     list[dict],  # entries without numbers
        "weak_descriptions":   list[dict],  # vague / too-short entries
        "employment_gaps":     list[dict],  # unexplained time periods
        "summary":             str,
      }
    """
    from datetime import date

    today = date.today().strftime("%Y-%m")

    # Slim the payload: the AI only needs these fields
    slim = {
        "work_history":     cv_data.get("work_history", []),
        "projects":         cv_data.get("projects", []),
        "experience_years": cv_data.get("experience_years"),
        "summary":          cv_data.get("summary"),
    }

    # FIX: {today} is now actually used inside the prompt template body.
    prompt = _CV_DEPTH_PROMPT.format(
        today=today,
        cv_json=json.dumps(slim, ensure_ascii=False, indent=2),
    )

    try:
        raw = _generate_with_fallback(prompt)
        report = _parse_json_response(raw)
        # Guarantee all keys exist even if the AI omits one
        report.setdefault("overall_depth_score", 0)
        report.setdefault("missing_metrics", [])
        report.setdefault("weak_descriptions", [])
        report.setdefault("employment_gaps", [])
        report.setdefault("summary", "")
        return report
    except Exception as exc:
        print(f"[ai_service] CV depth analysis failed: {exc}")
        return {
            "overall_depth_score": None,
            "missing_metrics":     [],
            "weak_descriptions":   [],
            "employment_gaps":     [],
            "summary":             "Depth analysis unavailable.",
            "error":               str(exc),
        }


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

# ---------------------------------------------------------------------------
# Public: scoring shim
# ---------------------------------------------------------------------------

def score_candidate(
    cv_data: dict[str, Any],
    job_title: str,
    job_requirements: str,
) -> dict[str, Any]:
    """
    Delegate to the intelligent hierarchical scorer (v2.0).
    """
    return compute_candidate_score(
        cv_data=cv_data,
        job_title=job_title,
        job_requirements=job_requirements,
    )


# ---------------------------------------------------------------------------
# Public: combined relevance + depth score
# ---------------------------------------------------------------------------

def compute_final_score(
    cv_data: dict[str, Any],
    job_title: str,
    job_requirements: str,
) -> float:
    """
    Blended score = 70 % pertinence poste + 30 % qualité/profondeur CV.

    Pondération v2.2 :
      • 70 % relevance_score  — keywords + sémantique vs le POSTE (corrigé v2.2 :
                                 les keywords proviennent de job_requirements, plus
                                 des skills du candidat lui-même).
      • 30 % quality_score    — profondeur du CV (métriques chiffrées, descriptions
                                 riches, progression de carrière). Rôle secondaire :
                                 un candidat très pertinent mais CV peu détaillé ne
                                 doit pas être pénalisé autant qu'avant (40 % → 30 %).

    La qualité seule ne doit pas compenser un mauvais alignement métier.

    Returns a float in [0, 100].
    """
    # 1. CV depth / quality score (AI-powered, 0-100)
    depth_report  = analyze_cv_depth(cv_data)
    quality_score = float(depth_report.get("overall_depth_score") or 0)
    quality_score = max(0.0, min(100.0, quality_score))   # borne défensive

    # 2. Relevance score : keywords du POSTE vs CV (0-100).
    #    compute_candidate_score utilise maintenant _parse_job_keywords(job_requirements)
    #    donc ce score mesure bien l'alignement candidat ↔ poste.
    score_result    = compute_candidate_score(
        cv_data=cv_data,
        job_title=job_title,
        job_requirements=job_requirements,
    )
    relevance_score = float(score_result.get("score", 0))
    relevance_score = max(0.0, min(100.0, relevance_score))  # borne défensive

    # 3. Blend pondéré : pertinence > qualité
    return round(relevance_score * 0.70 + quality_score * 0.30, 2)