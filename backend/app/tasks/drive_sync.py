# backend/app/tasks/drive_sync.py

from __future__ import annotations

import os
import re
from typing import Any

from celery import shared_task
from googleapiclient.errors import HttpError

from app.config import get_settings
from app.db.supabase_client import get_supabase_admin
from app.services.ai_service import extract_cv_info
from app.services.cv_parser import extract_text_from_bytes
from app.services.drive_service import (
    _get_drive_service,
    download_file_bytes,
    get_file_metadata,
    list_new_pdf_files_since,
    list_pdf_files,
)
from app.services.scoring_service import compute_candidate_score

from app.services.screening_engine import passes_screening
from app.tasks.cv_processing import (
    build_candidate_payload,
    compute_best_job_match,
    ensure_list,
    fetch_active_jobs,
    fetch_job,
)

PERMANENT_ERRORS = (ValueError, PermissionError)
RETRY_BASE_DELAY = 60


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def sanitize_filename(filename: str) -> str:
    """Sanitize uploaded filenames for storage safety."""
    name, ext = os.path.splitext(filename)

    cleaned = re.sub(
        r"[^a-zA-Z0-9_.-]",
        "",
        name.replace(" ", "_"),
    )

    return f"{cleaned}{ext}"


def retry_delay(retries: int) -> int:
    """Exponential retry backoff."""
    return RETRY_BASE_DELAY * (2**retries)


def candidate_exists(supabase, drive_file_id: str) -> bool:
    """Check whether a Drive file was already processed."""
    response = (
        supabase.table("candidates")
        .select("id")
        .eq("drive_file_id", drive_file_id)
        .limit(1)
        .execute()
    )

    return bool(response.data)


def upload_cv_to_storage(
    supabase,
    drive_file_id: str,
    file_name: str,
    pdf_bytes: bytes,
) -> str:
    """Upload CV to Supabase storage and return public URL."""
    storage_path = f"cvs/drive/{drive_file_id}/{file_name}"

    supabase.storage.from_("cvs").upload(
        storage_path,
        pdf_bytes,
        file_options={
            "content-type": "application/pdf",
            "upsert": "true",
        },
    )

    return supabase.storage.from_("cvs").get_public_url(storage_path)


def insert_failed_candidate(
    supabase,
    cv_url: str,
    drive_file_id: str,
    job_id: str | None = None,
) -> None:
    """Insert placeholder row for unreadable CVs."""
    payload: dict[str, Any] = {
        "full_name": "Document non lisible",
        "cv_file_url": cv_url,
        "drive_file_id": drive_file_id,
        "processing_status": "failed",
        "status": "failed",
    }

    if job_id:
        payload["job_id"] = job_id

    try:
        supabase.table("candidates").insert(payload).execute()
    except Exception:
        # Best effort only
        pass


def extract_candidate_text(
    pdf_bytes: bytes,
    supabase,
    cv_url: str,
    drive_file_id: str,
    job_id: str | None,
) -> str:
    """Extract raw text from PDF bytes."""
    raw_text = extract_text_from_bytes(pdf_bytes)

    if raw_text.strip():
        return raw_text

    insert_failed_candidate(
        supabase=supabase,
        cv_url=cv_url,
        drive_file_id=drive_file_id,
        job_id=job_id,
    )

    raise ValueError(
        f"Empty text extracted from Drive file '{drive_file_id}'"
    )


def resolve_candidate_score(
    supabase,
    extracted: dict,
    job_id: str | None,
) -> tuple[dict, str | None]:
    """
    Resolve best score result and matching job.
    Mirrors process_cv scoring logic.
    """
    score_result = None
    resolved_job_id = job_id

    if job_id:
        job = fetch_job(supabase, job_id)

        if job:
            score_result = compute_candidate_score(
                cv_data=extracted,
                job_title=job.get("title", ""),
                job_requirements=job.get("requirements", ""),
                supabase=supabase,
            )

    else:
        jobs = fetch_active_jobs(supabase)

        score_result, resolved_job_id = compute_best_job_match(
            supabase=supabase,
            cv_info=extracted,
            jobs=jobs,
        )

    if score_result:
        return score_result, resolved_job_id

    # Fallback scoring
    fallback_score = compute_candidate_score(
        cv_data=extracted,
        job_title=extracted.get("current_position", "Candidate"),
        job_requirements=" ".join(
            ensure_list(extracted.get("skills"))
        ),
        supabase=supabase,
    )

    return fallback_score, resolved_job_id


def insert_candidate(
    supabase,
    payload: dict,
    drive_file_id: str,
) -> dict:
    """Insert candidate safely with race-condition protection."""
    try:
        response = (
            supabase.table("candidates")
            .insert(payload)
            .execute()
        )

        return {
            "status": "processed",
            "candidate_id": response.data[0]["id"],
        }

    except Exception as exc:
        if "uq_candidates_drive_file_id" in str(exc):
            return {
                "status": "skipped_race",
                "drive_file_id": drive_file_id,
            }

        raise


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=RETRY_BASE_DELAY,
)
def process_drive_file(
    self,
    drive_file_id: str,
    job_id: str | None = None,
) -> dict:
    """
    Process a single Drive CV file.

    Pipeline:
        - Idempotency check
        - Download PDF
        - Upload to storage
        - Extract text
        - AI parsing
        - Scoring
        - Candidate insertion
    """
    supabase = get_supabase_admin()

    try:
        # ------------------------------------------------------------------ #
        # Idempotency
        # ------------------------------------------------------------------ #

        if candidate_exists(supabase, drive_file_id):
            return {
                "status": "skipped",
                "drive_file_id": drive_file_id,
            }

        # ------------------------------------------------------------------ #
        # Download file
        # ------------------------------------------------------------------ #

        metadata = get_file_metadata(drive_file_id)

        file_name = sanitize_filename(
            metadata.get("name", f"{drive_file_id}.pdf")
        )

        pdf_bytes = download_file_bytes(drive_file_id)

        # ------------------------------------------------------------------ #
        # Upload CV
        # ------------------------------------------------------------------ #

        cv_url = upload_cv_to_storage(
            supabase=supabase,
            drive_file_id=drive_file_id,
            file_name=file_name,
            pdf_bytes=pdf_bytes,
        )

        # ------------------------------------------------------------------ #
        # Text extraction
        # ------------------------------------------------------------------ #

        raw_text = extract_candidate_text(
            pdf_bytes=pdf_bytes,
            supabase=supabase,
            cv_url=cv_url,
            drive_file_id=drive_file_id,
            job_id=job_id,
        )

        # ------------------------------------------------------------------ #
        # AI extraction
        # ------------------------------------------------------------------ #

        extracted = extract_cv_info(raw_text)

        # ------------------------------------------------------------------ #
        # Scoring
        # ------------------------------------------------------------------ #

        score_result, resolved_job_id = resolve_candidate_score(
            supabase=supabase,
            extracted=extracted,
            job_id=job_id,
        )

        # ------------------------------------------------------------------ #
        # Build payload
        # ------------------------------------------------------------------ #

        payload = build_candidate_payload(
            raw_text=raw_text,
            cv_info=extracted,
            score_result=score_result,
            job_id=resolved_job_id,
        )

        payload.update(
            {
                "cv_file_url": cv_url,
                "drive_file_id": drive_file_id,
                "status": "applied",
            }
        )

        # ------------------------------------------------------------------ #
        # Insert candidate
        # ------------------------------------------------------------------ #

        return insert_candidate(
            supabase=supabase,
            payload=payload,
            drive_file_id=drive_file_id,
        )

    except PERMANENT_ERRORS:
        raise

    except HttpError as exc:
        if exc.status_code == 401:
            _get_drive_service.cache_clear()

        raise self.retry(
            exc=exc,
            countdown=retry_delay(self.request.retries),
        )

    except Exception as exc:
        raise self.retry(
            exc=exc,
            countdown=retry_delay(self.request.retries),
        )


@shared_task
def sync_drive_folder(job_id: str | None = None) -> dict:
    """
    Full Drive folder synchronization.

    Safety net for missed webhook events.
    """
    settings = get_settings()

    if not settings.drive_folder_id:
        return {
            "status": "skipped",
            "reason": "DRIVE_FOLDER_ID not configured",
        }

    supabase = get_supabase_admin()

    files = list_pdf_files(settings.drive_folder_id)

    existing = (
        supabase.table("candidates")
        .select("drive_file_id")
        .execute()
    )

    processed_ids = {
        row["drive_file_id"]
        for row in existing.data
        if row.get("drive_file_id")
    }

    queued = 0

    for file_data in files:
        file_id = file_data["id"]

        if file_id in processed_ids:
            continue

        process_drive_file.delay(
            drive_file_id=file_id,
            job_id=job_id,
        )

        queued += 1

    return {
        "status": "done",
        "total_files": len(files),
        "queued": queued,
    }


@shared_task
def sync_drive_webhook(job_id: str | None = None) -> dict:
    """
    Process Drive webhook notifications using page tokens.
    """
    settings = get_settings()

    if not settings.drive_folder_id:
        return {
            "status": "skipped",
            "reason": "DRIVE_FOLDER_ID not configured",
        }

    supabase = get_supabase_admin()

    config_row = (
        supabase.table("app_config")
        .select("value")
        .eq("key", "drive_page_token")
        .single()
        .execute()
    )

    page_token = (
        config_row.data["value"]
        if config_row.data
        else None
    )

    if not page_token:
        return sync_drive_folder(job_id=job_id)

    new_files, next_token = list_new_pdf_files_since(
        settings.drive_folder_id,
        page_token,
    )

    for file_data in new_files:
        process_drive_file.delay(
            drive_file_id=file_data["id"],
            job_id=job_id,
        )

    (
        supabase.table("app_config")
        .upsert(
            {
                "key": "drive_page_token",
                "value": next_token,
            }
        )
        .execute()
    )

    return {
        "status": "done",
        "new_files": len(new_files),
        "queued": len(new_files),
    }


@shared_task
def renew_drive_webhook() -> dict:
    """
    Renew Google Drive webhook subscription.
    Runs periodically via Celery Beat.
    """
    from app.services.webhook_manager import (
        ensure_webhook_registered,
    )

    return ensure_webhook_registered()


# --------------------------------------------------------------------------- #
# Candidate Screening
# --------------------------------------------------------------------------- #

def process_candidate(candidate, job) -> dict:
    """
    Apply hard screening gates before scoring a candidate.
    """

    if not passes_screening(candidate, job):
        return {
            "status": "rejected",
            "score": 0,
        }

    cv_data = extract_cv_info(candidate.raw_text)

    score_result = compute_candidate_score(
        cv_data=cv_data,
        job_title=job.title,
        job_requirements=job.requirements,
        supabase=get_supabase_admin(),
    )

    return {
        "status": "accepted",
        "score": score_result.get("final_score", 0),
        "details": score_result,
    }