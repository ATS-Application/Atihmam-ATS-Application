import json
import re
import requests
import google.generativeai as genai
from typing import Optional
from app.config import get_settings

from app.services.scoring_service import compute_candidate_score

# =========================================================
# JSON PARSER
# =========================================================

def _parse_json_response(text: str) -> dict:
    if not text:
        raise ValueError("Empty AI response")
    # Extract JSON if wrapped in markdown
    clean = re.sub(r"```(?:json)?", "", text)
    clean = clean.replace("```", "").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        print("[JSON PARSE ERROR]", clean)
        raise ValueError(f"Invalid JSON response: {e}")

# =========================================================
# PROVIDER CALLS
# =========================================================

def _call_gemini(prompt: str, settings) -> str:
    if not settings.gemini_api_key:
        raise Exception("Missing Gemini API key")
    genai.configure(api_key=settings.gemini_api_key)
    # Using 1.5-flash-latest to avoid 404 errors
    model = genai.GenerativeModel("gemini-1.5-flash-latest")
    response = model.generate_content(prompt)
    return response.text

def _call_openrouter(prompt: str, settings) -> str:
    if not settings.openrouter_api_key:
        raise Exception("Missing OpenRouter API key")
    
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
        raise Exception("Missing DeepSeek API key")
    
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
        raise Exception("Missing Mistral API key")
        
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


def score_candidate(cv_data: dict, job_title: str, job_requirements: str) -> dict:
    """
    Pass-through function to satisfy the import in drive_sync.py
    """
    return compute_candidate_score(cv_data, job_title, job_requirements)


# =========================================================
# FALLBACK ENGINE & EXPORTS
# =========================================================

def _generate_with_fallback(prompt: str) -> str:
    settings = get_settings()
    providers = [
        ("OpenRouter", _call_openrouter),
        ("DeepSeek", _call_deepseek),
        ("Mistral", _call_mistral),
        ("Gemini", _call_gemini),
    ]

    for name, fn in providers:
        try:
            return fn(prompt, settings)
        except Exception as e:
            print(f"[AI] {name} failed: {e}")
    
    raise Exception("All AI providers failed.")

def extract_cv_info(raw_text: str) -> dict:
    """
    Parses CV text into a JSON object.
    """
    prompt = f"""
    You are an ATS resume parser. Extract the following information from the provided CV text into JSON format:
    {{
      "full_name": "string",
      "email": "string",
      "phone": "string",
      "current_position": "string",
      "skills": ["list", "of", "strings"],
      "experience_years": number
    }}
    
    CV Text:
    {raw_text[:8000]}
    """
    response_text = _generate_with_fallback(prompt)
    return _parse_json_response(response_text)