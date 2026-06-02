# app/tasks/cv_processing.py

"""
CV Processing Pipeline (MVP VERSION - NO CELERY)

This is a simplified synchronous/background-safe version of the original pipeline.

Replaces:
- Celery tasks (.delay)
- Redis queue
- Worker services

With:
- Direct function execution
- FastAPI BackgroundTasks compatibility

Flow:
1. Download CV from Supabase Storage
2. Extract text from PDF
3. AI extraction (skills, experience, etc.)
4. Job matching + scoring
5. Save structured candidate data

⚠️ Designed for MVP / small-to-medium workloads.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.db.supabase_client import get_supabase_admin
from app.services.ai_service import extract_cv_info
from app.services.cv_parser import extract_text_from_bytes
from app.services.scoring_service import compute_candidate_score

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIG
# ============================================================================

MAX_TEXT_LENGTH = 50_000
MAX_AI_DATA_SIZE = 100_000

PERMANENT_ERRORS = (
    ValueError,
    PermissionError,
)

REQUIRED_CV_FIELDS = [
    "skills",
    "work_history",
    "education",
]

# ============================================================================
# HELPERS
# ============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def ensure_string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def sanitize_ai_data(data: dict) -> dict:
    try:
        serialized = json.dumps(data)

        if len(serialized) > MAX_AI_DATA_SIZE:
            serialized = serialized[:MAX_AI_DATA_SIZE]

        return json.loads(serialized)
    except Exception:
        return {}


def validate_cv_info(cv_info: dict) -> None:
    if not isinstance(cv_info, dict):
        raise ValueError("AI extraction must return dict")

    for field in REQUIRED_CV_FIELDS:
        if field not in cv_info:
            logger.warning("Missing field: %s", field)


def extract_text_safe(pdf_bytes: bytes, timeout: int = 30) -> str:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(extract_text_from_bytes, pdf_bytes)
        return future.result(timeout=timeout)

# ============================================================================
# DB HELPERS
# ============================================================================

def update_candidate(supabase, candidate_id: str, data: dict):
    supabase.table("candidates").update(data).eq("id", candidate_id).execute()


def fetch_candidate(supabase, candidate_id: str):
    return (
        supabase.table("candidates")
        .select("*")
        .eq("id", candidate_id)
        .single()
        .execute()
        .data
    )


def fetch_job(supabase, job_id: str):
    return (
        supabase.table("jobs")
        .select("*")
        .eq("id", job_id)
        .single()
        .execute()
        .data
    )


def fetch_active_jobs(supabase):
    return (
        supabase.table("jobs")
        .select("id, title, requirements")
        .eq("is_active", True)
        .execute()
        .data
        or []
    )

# ============================================================================
# MAIN PROCESSING FUNCTION (NO CELERY)
# ============================================================================

def process_cv(candidate_id: str, storage_path: str, job_id: str | None = None):
    """
    Main CV processing pipeline (MVP version).

    This function is designed to be executed:
    - via FastAPI BackgroundTasks
    - or direct synchronous call

    It replaces the previous Celery-based implementation.
    """

    supabase = get_supabase_admin()

    try:
        logger.info(f"Processing CV: {candidate_id}")

        candidate = fetch_candidate(supabase, candidate_id)

        if not candidate:
            raise ValueError("Candidate not found")

        if candidate.get("processing_status") == "completed":
            return {"message": "Already processed"}

        update_candidate(supabase, candidate_id, {
            "processing_status": "processing",
            "processing_error": None,
            "updated_at": utc_now(),
        })

        pdf_bytes = (
            supabase.storage
            .from_("cvs")
            .download(storage_path)
        )

        if not pdf_bytes:
            raise ValueError("Failed to download CV")

        raw_text = extract_text_safe(pdf_bytes)

        if not raw_text.strip():
            raise ValueError("Empty CV text")

        cv_info = extract_cv_info(raw_text)
        validate_cv_info(cv_info)

        score_result = None
        resolved_job_id = job_id

        if job_id:
            job = fetch_job(supabase, job_id)
            if job:
                score_result = compute_candidate_score(
                    cv_data=cv_info,
                    job_title=job.get("title", ""),
                    job_requirements=job.get("requirements", ""),
                    supabase=supabase,
                )

        else:
            jobs = fetch_active_jobs(supabase)

            best_score = -1
            best_result = None
            best_job_id = None

            for job in jobs:
                try:
                    result = compute_candidate_score(
                        cv_data=cv_info,
                        job_title=job.get("title", ""),
                        job_requirements=job.get("requirements", ""),
                        supabase=supabase,
                    )

                    score = result.get("score", 0)

                    if score > best_score:
                        best_score = score
                        best_result = result
                        best_job_id = job.get("id")

                except Exception as e:
                    logger.error(f"Job scoring failed: {e}")

            score_result = best_result
            resolved_job_id = best_job_id

        if not score_result:
            score_result = {
                "score": 0,
                "dimension_scores": {},
                "confidence": 0.0,
                "reasoning": "",
                "matched_keywords": [],
                "missing_keywords": [],
            }

        payload = {
            "cv_raw_text": raw_text[:MAX_TEXT_LENGTH],
            "ai_extracted_data": sanitize_ai_data(cv_info),

            "full_name": ensure_string(cv_info.get("full_name")),
            "email": ensure_string(cv_info.get("email")),
            "phone": ensure_string(cv_info.get("phone")),

            "skills": ensure_list(cv_info.get("skills")),
            "education": ensure_list(cv_info.get("education")),
            "work_history": ensure_list(cv_info.get("work_history")),

            "experience_years": cv_info.get("experience_years", 0),

            "score": score_result.get("score", 0),
            "dimension_scores": score_result.get("dimension_scores", {}),
            "score_confidence": score_result.get("confidence", 0),

            "processing_status": "completed",
            "updated_at": utc_now(),
        }

        if resolved_job_id:
            payload["job_id"] = resolved_job_id

        update_candidate(supabase, candidate_id, payload)

        logger.info(f"CV processed successfully: {candidate_id}")

        return {
            "success": True,
            "candidate_id": candidate_id,
            "score": payload["score"],
        }

    except Exception as e:
        logger.exception(f"CV processing failed: {e}")

        update_candidate(supabase, candidate_id, {
            "processing_status": "failed",
            "processing_error": str(e),
            "updated_at": utc_now(),
        })

        return {
            "success": False,
            "error": str(e),
        }
