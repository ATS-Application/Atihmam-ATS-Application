import json
import re
import google.generativeai as genai
from app.config import get_settings

_model: genai.GenerativeModel | None = None


def _get_model() -> genai.GenerativeModel:
    global _model
    if _model is None:
        settings = get_settings()
        genai.configure(api_key=settings.gemini_api_key)
        _model = genai.GenerativeModel("gemini-2.5-flash")
    return _model


def _parse_json_response(text: str) -> dict:
    clean = re.sub(r"```(?:json)?\n?", "", text).strip().rstrip("```").strip()
    return json.loads(clean)


def extract_cv_info(raw_text: str) -> dict:
    model = _get_model()
    prompt = f"""You are an expert HR assistant. Extract structured information from the CV below.

Return ONLY a valid JSON object with this exact structure (no preamble, no explanation):
{{
  "full_name": "string or null",
  "email": "string or null",
  "phone": "string or null",
  "current_position": "string or null",
  "skills": ["skill1", "skill2"],
  "experience_years": integer or null,
  "summary": "2-3 sentence professional summary"
}}

CV TEXT:
{raw_text[:8000]}
"""
    response = model.generate_content(prompt)
    return _parse_json_response(response.text)


def score_candidate(cv_data: dict, job_title: str, job_requirements: str) -> float:
    model = _get_model()
    prompt = f"""You are an expert recruiter. Score this candidate for the job below.

JOB TITLE: {job_title}
JOB REQUIREMENTS:
{job_requirements[:3000]}

CANDIDATE PROFILE:
- Position: {cv_data.get('current_position', 'N/A')}
- Experience: {cv_data.get('experience_years', 'N/A')} years
- Skills: {', '.join(cv_data.get('skills', []))}
- Summary: {cv_data.get('summary', 'N/A')}

Return ONLY a valid JSON object (no explanation):
{{
  "score": <float between 0.0 and 10.0>,
  "reasoning": "<one sentence explaining the score>"
}}
"""
    response = model.generate_content(prompt)
    result = _parse_json_response(response.text)
    return float(result.get("score", 0.0))