# app/tasks/cv_processing.py
"""
Intelligent CV Processing Pipeline
=================================

Pipeline:
    1. Download CV from Supabase Storage
    2. Extract text from PDF
    3. AI-powered CV parsing
    4. Intelligent ATS scoring + job matching
    5. Persist structured candidate profile to DB

Features:
    - Automatic retry with exponential backoff
    - Permanent vs transient error handling
    - AI response validation
    - Parallel job scoring
    - Safe JSON normalization
    - Backfill rescoring task
    - Drive-sync queued candidate recovery
    - Idempotent processing
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
from datetime import datetime, timezone
from typing import Any

from celery import shared_task

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
PAGE_SIZE = 200

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
# GENERIC HELPERS
# ============================================================================


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def ensure_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def ensure_string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def sanitize_ai_data(data: dict) -> dict:
    """
    Prevent oversized AI payloads from being stored.
    """
    try:
        serialized = json.dumps(data)

        if len(serialized) > MAX_AI_DATA_SIZE:
            logger.warning("AI extracted data exceeded size limit")
            serialized = serialized[:MAX_AI_DATA_SIZE]

        return json.loads(serialized)

    except Exception:
        logger.exception("Failed sanitizing AI data")
        return {}


def validate_cv_info(cv_info: dict) -> None:
    """
    Validate AI extraction response.
    """
    if not isinstance(cv_info, dict):
        raise ValueError("AI extraction must return a dictionary")

    for field in REQUIRED_CV_FIELDS:
        if field not in cv_info:
            logger.warning("Missing expected CV field: %s", field)


def extract_storage_path(cv_url: str) -> str:
    """
    Extract storage object path from Supabase public URL.
    """
    if not cv_url:
        return ""

    clean_url = cv_url.split("?")[0]
    marker = "/object/public/cvs/"

    if marker in clean_url:
        return clean_url.split(marker)[-1]

    return clean_url


def extract_text_safe(
    pdf_bytes: bytes,
    timeout: int = 30,
) -> str:
    """
    Prevent PDF extraction from freezing forever.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            extract_text_from_bytes,
            pdf_bytes,
        )
        return future.result(timeout=timeout)


# ============================================================================
# DATABASE HELPERS
# ============================================================================


def update_candidate(
    supabase,
    candidate_id: str,
    data: dict,
) -> None:
    response = (
        supabase.table("candidates")
        .update(data)
        .eq("id", candidate_id)
        .execute()
    )

    if getattr(response, "error", None):
        raise RuntimeError(
            f"Failed updating candidate {candidate_id}: "
            f"{response.error}"
        )


def mark_candidate_failed(
    supabase,
    candidate_id: str,
    error: Exception,
) -> None:
    update_candidate(
        supabase,
        candidate_id,
        {
            "processing_status": "failed",
            "processing_error": str(error),
            "updated_at": utc_now(),
        },
    )


def fetch_candidate(
    supabase,
    candidate_id: str,
) -> dict | None:
    response = (
        supabase.table("candidates")
        .select("*")
        .eq("id", candidate_id)
        .single()
        .execute()
    )

    return response.data


def fetch_job(
    supabase,
    job_id: str,
) -> dict | None:
    response = (
        supabase.table("jobs")
        .select("*")
        .eq("id", job_id)
        .single()
        .execute()
    )

    return response.data


def fetch_active_jobs(supabase) -> list[dict]:
    response = (
        supabase.table("jobs")
        .select("id, title, requirements")
        .eq("is_active", True)
        .execute()
    )

    return response.data or []


# ============================================================================
# QUEUED CANDIDATES
# ============================================================================


def trigger_pending_candidates(
    supabase=None,
) -> int:
    """
    Re-queue all candidates stuck in queued state.
    """
    client = supabase or get_supabase_admin()

    response = (
        client.table("candidates")
        .select("id, cv_file_url, job_id")
        .eq("processing_status", "queued")
        .execute()
    )

    rows = response.data or []
    dispatched = 0

    for row in rows:
        candidate_id = row.get("id")
        cv_url = row.get("cv_file_url", "")
        job_id = row.get("job_id")

        if not candidate_id or not cv_url:
            continue

        storage_path = extract_storage_path(cv_url)

        if not storage_path:
            logger.warning(
                "Could not extract storage path for candidate %s",
                candidate_id,
            )
            continue

        try:
            process_cv.delay(
                candidate_id=candidate_id,
                storage_path=storage_path,
                job_id=job_id,
            )

            dispatched += 1

            logger.info(
                "Queued processing for candidate %s",
                candidate_id,
            )

        except Exception as exc:
            logger.exception(
                "Failed dispatching candidate %s: %s",
                candidate_id,
                exc,
            )

    return dispatched


# ============================================================================
# JOB MATCHING
# ============================================================================


def score_single_job(
    supabase,
    cv_info: dict,
    job: dict,
) -> tuple[float, dict | None, str | None]:
    """
    Score candidate against a single job.
    """
    try:
        result = compute_candidate_score(
            cv_data=cv_info,
            job_title=job.get("title", ""),
            job_requirements=job.get("requirements", ""),
            supabase=supabase,
        )

        return (
            result.get("score", 0),
            result,
            job.get("id"),
        )

    except Exception as exc:
        logger.exception(
            "Failed scoring job %s: %s",
            job.get("id"),
            exc,
        )

        return (0, None, None)


def compute_best_job_match(
    *,
    supabase,
    cv_info: dict,
    jobs: list[dict],
) -> tuple[dict | None, str | None]:
    """
    Parallel job scoring.
    """
    best_score = -1
    best_result = None
    best_job_id = None

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=4,
    ) as executor:

        futures = [
            executor.submit(
                score_single_job,
                supabase,
                cv_info,
                job,
            )
            for job in jobs
        ]

        for future in concurrent.futures.as_completed(futures):
            score, result, job_id = future.result()

            if score > best_score:
                best_score = score
                best_result = result
                best_job_id = job_id

    return best_result, best_job_id


# ============================================================================
# PAYLOAD BUILDER
# ============================================================================


def build_candidate_payload(
    *,
    raw_text: str,
    cv_info: dict,
    score_result: dict | None,
    job_id: str | None,
) -> dict:
    """
    Build normalized candidate payload.
    """
    work_history = ensure_list(
        cv_info.get("work_history")
    )

    payload = {
        # Raw data
        "cv_raw_text": raw_text[:MAX_TEXT_LENGTH],
        "ai_extracted_data": sanitize_ai_data(cv_info),

        # Identity
        "full_name": ensure_string(
            cv_info.get("full_name")
        ),
        "email": ensure_string(
            cv_info.get("email")
        ),
        "phone": ensure_string(
            cv_info.get("phone")
        ),
        "current_position": ensure_string(
            cv_info.get("current_position")
        ),

        # Structured fields
        "skills": ensure_list(
            cv_info.get("skills")
        ),
        "certifications": ensure_list(
            cv_info.get("certifications")
        ),
        "education": ensure_list(
            cv_info.get("education")
        ),
        "projects": ensure_list(
            cv_info.get("projects")
        ),
        "languages": ensure_list(
            cv_info.get("languages")
        ),
        "work_history": work_history,

        # Experience summary
        "experience": [
            f"{job.get('title', '')} at "
            f"{job.get('company', '')}"
            for job in work_history
            if isinstance(job, dict)
        ],

        # Metrics
        "experience_years": (
            cv_info.get("experience_years") or 0
        ),

        # Status
        "processing_status": "completed",
        "updated_at": utc_now(),
    }

    if job_id:
        payload["job_id"] = job_id

    if score_result:
        payload["score"] = score_result.get(
            "score",
            0,
        )

        payload["score_reasoning"] = (
            score_result.get(
                "reasoning",
                "",
            )
        )

        payload["dimension_scores"] = (
            score_result.get(
                "dimension_scores",
                {},
            )
        )

        payload["matched_keywords"] = (
            score_result.get(
                "matched_keywords",
                [],
            )
        )

        payload["missing_keywords"] = (
            score_result.get(
                "missing_keywords",
                [],
            )
        )

        payload["score_confidence"] = (
            score_result.get(
                "confidence",
                0.0,
            )
        )

    return payload


# ============================================================================
# MAIN TASK
# ============================================================================


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def process_cv(
    self,
    candidate_id: str,
    storage_path: str,
    job_id: str | None = None,
):
    """
    Full CV processing pipeline.
    """
    supabase = get_supabase_admin()

    try:
        logger.info(
            "Starting CV processing for candidate %s",
            candidate_id,
        )

        # ------------------------------------------------------------------
        # IDEMPOTENCY CHECK
        # ------------------------------------------------------------------

        candidate = fetch_candidate(
            supabase,
            candidate_id,
        )

        if not candidate:
            raise ValueError("Candidate not found")

        current_status = candidate.get(
            "processing_status"
        )

        if current_status == "completed":
            logger.info(
                "Candidate %s already processed",
                candidate_id,
            )
            return {
                "success": True,
                "message": "Already processed",
            }

        # ------------------------------------------------------------------
        # MARK PROCESSING
        # ------------------------------------------------------------------

        update_candidate(
            supabase,
            candidate_id,
            {
                "processing_status": "processing",
                "processing_error": None,
                "updated_at": utc_now(),
            },
        )

        # ------------------------------------------------------------------
        # DOWNLOAD PDF
        # ------------------------------------------------------------------

        pdf_bytes = (
            supabase.storage
            .from_("cvs")
            .download(storage_path)
        )

        if not pdf_bytes:
            raise ValueError(
                "Failed downloading CV from storage"
            )

        # ------------------------------------------------------------------
        # EXTRACT TEXT
        # ------------------------------------------------------------------

        raw_text = extract_text_safe(pdf_bytes)

        if not raw_text or not raw_text.strip():
            raise ValueError(
                "No readable text extracted from CV"
            )

        # ------------------------------------------------------------------
        # AI EXTRACTION
        # ------------------------------------------------------------------

        cv_info = extract_cv_info(raw_text)

        validate_cv_info(cv_info)

        logger.info(
            "Processing metrics | candidate=%s | "
            "text_length=%d | skills=%d",
            candidate_id,
            len(raw_text),
            len(cv_info.get("skills", [])),
        )

        # ------------------------------------------------------------------
        # SCORING
        # ------------------------------------------------------------------

        score_result = None
        resolved_job_id = job_id

        if job_id:
            job = fetch_job(
                supabase,
                job_id,
            )

            if job:
                score_result = compute_candidate_score(
                    cv_data=cv_info,
                    job_title=job.get("title", ""),
                    job_requirements=job.get(
                        "requirements",
                        "",
                    ),
                    supabase=supabase,
                )

        else:
            jobs = fetch_active_jobs(supabase)

            score_result, resolved_job_id = (
                compute_best_job_match(
                    supabase=supabase,
                    cv_info=cv_info,
                    jobs=jobs,
                )
            )

        # ------------------------------------------------------------------
        # FALLBACK SCORING
        # ------------------------------------------------------------------

        if not score_result:
            score_result = compute_candidate_score(
                cv_data=cv_info,
                job_title=cv_info.get(
                    "current_position",
                    "Candidate",
                ),
                job_requirements=" ".join(
                    ensure_list(
                        cv_info.get("skills")
                    )
                ),
                supabase=supabase,
            )

        # ------------------------------------------------------------------
        # SAVE
        # ------------------------------------------------------------------

        payload = build_candidate_payload(
            raw_text=raw_text,
            cv_info=cv_info,
            score_result=score_result,
            job_id=resolved_job_id,
        )

        update_candidate(
            supabase,
            candidate_id,
            payload,
        )

        logger.info(
            "CV processing completed | "
            "candidate=%s | score=%.1f",
            candidate_id,
            payload.get("score", 0),
        )

        return {
            "success": True,
            "candidate_id": candidate_id,
            "job_id": resolved_job_id,
            "score": payload.get("score", 0),
            "dimension_scores": payload.get(
                "dimension_scores",
                {},
            ),
        }

    # ----------------------------------------------------------------------
    # PERMANENT ERRORS
    # ----------------------------------------------------------------------

    except PERMANENT_ERRORS as exc:
        logger.exception(
            "Permanent CV processing error: %s",
            exc,
        )

        mark_candidate_failed(
            supabase,
            candidate_id,
            exc,
        )

        raise

    # ----------------------------------------------------------------------
    # RETRYABLE ERRORS
    # ----------------------------------------------------------------------

    except Exception as exc:
        retry_count = self.request.retries
        countdown = 30 * (2 ** retry_count)

        logger.exception(
            "Retryable CV processing error "
            "(retry=%d/%d): %s",
            retry_count,
            self.max_retries,
            exc,
        )

        if retry_count >= self.max_retries:
            mark_candidate_failed(
                supabase,
                candidate_id,
                exc,
            )

        raise self.retry(
            exc=exc,
            countdown=countdown,
        )


# ============================================================================
# BACKFILL TASK
# ============================================================================


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def backfill_dimension_scores(
    self,
    dry_run: bool = False,
):
    """
    Rescore candidates missing dimension_scores.
    """
    supabase = get_supabase_admin()

    updated = 0
    failed = 0
    offset = 0

    while True:
        response = (
            supabase.table("candidates")
            .select(
                "id, score, job_id, cv_raw_text, "
                "ai_extracted_data, work_history, "
                "skills, certifications, education, "
                "projects, languages, current_position, "
                "experience_years, dimension_scores"
            )
            .range(
                offset,
                offset + PAGE_SIZE - 1,
            )
            .execute()
        )

        rows = response.data or []

        if not rows:
            break

        targets = [
            row
            for row in rows
            if not row.get("dimension_scores")
        ]

        for row in targets:
            candidate_id = row["id"]

            try:
                ai_data = row.get(
                    "ai_extracted_data"
                ) or {}

                if isinstance(ai_data, str):
                    try:
                        ai_data = json.loads(ai_data)
                    except Exception:
                        ai_data = {}

                cv_info = {
                    **ai_data,
                    "cv_raw_text": row.get(
                        "cv_raw_text",
                        "",
                    ),
                    "work_history": row.get(
                        "work_history",
                        [],
                    ),
                    "skills": row.get(
                        "skills",
                        [],
                    ),
                    "certifications": row.get(
                        "certifications",
                        [],
                    ),
                    "education": row.get(
                        "education",
                        [],
                    ),
                    "projects": row.get(
                        "projects",
                        [],
                    ),
                    "current_position": row.get(
                        "current_position",
                        "",
                    ),
                    "experience_years": row.get(
                        "experience_years",
                        0,
                    ),
                }

                job_title = "Candidate"

                job_requirements = " ".join(
                    ensure_list(
                        cv_info.get("skills")
                    )
                )

                if row.get("job_id"):
                    job = fetch_job(
                        supabase,
                        row["job_id"],
                    )

                    if job:
                        job_title = job.get(
                            "title",
                            job_title,
                        )

                        job_requirements = job.get(
                            "requirements",
                            job_requirements,
                        )

                score_result = compute_candidate_score(
                    cv_data=cv_info,
                    job_title=job_title,
                    job_requirements=job_requirements,
                    supabase=supabase,
                )

                if dry_run:
                    logger.info(
                        "[DRY RUN] candidate=%s "
                        "score=%.1f",
                        candidate_id,
                        score_result.get("score", 0),
                    )

                    updated += 1
                    continue

                update_candidate(
                    supabase,
                    candidate_id,
                    {
                        "score": score_result.get(
                            "score",
                            0,
                        ),
                        "dimension_scores": (
                            score_result.get(
                                "dimension_scores",
                                {},
                            )
                        ),
                        "matched_keywords": (
                            score_result.get(
                                "matched_keywords",
                                [],
                            )
                        ),
                        "missing_keywords": (
                            score_result.get(
                                "missing_keywords",
                                [],
                            )
                        ),
                        "score_confidence": (
                            score_result.get(
                                "confidence",
                                0.0,
                            )
                        ),
                        "score_reasoning": (
                            score_result.get(
                                "reasoning",
                                "",
                            )
                        ),
                        "updated_at": utc_now(),
                    },
                )

                updated += 1

                logger.info(
                    "Backfilled candidate %s",
                    candidate_id,
                )

            except Exception as exc:
                failed += 1

                logger.exception(
                    "Backfill failed for candidate %s: %s",
                    candidate_id,
                    exc,
                )

        offset += PAGE_SIZE

    logger.info(
        "Backfill complete | updated=%d | failed=%d",
        updated,
        failed,
    )

    return {
        "updated": updated,
        "failed": failed,
        "dry_run": dry_run,
    }