# backend/app/tasks/drive_sync.py

"""
Drive Sync Pipeline (MVP VERSION - NO CELERY)

Replaces:
- Celery tasks
- Redis queue
- Worker services

With:
- direct execution
- FastAPI BackgroundTasks support
- safe synchronous processing

Pipeline:
1. Scan Google Drive folder
2. Detect new PDFs
3. Download file
4. Upload to Supabase storage
5. Extract text
6. AI parsing
7. Score candidate
8. Insert into DB
"""

from __future__ import annotations

import os
import re
from typing import Any

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
# HELPERS
# --------------------------------------------------------------------------- #

def sanitize_filename(filename: str) -> str:
    name, ext = os.path.splitext(filename)

    cleaned = re.sub(
        r"[^a-zA-Z0-9_.-]",
        "",
        name.replace(" ", "_"),
    )

    return f"{cleaned}{ext}"


def candidate_exists(supabase, drive_file_id: str) -> bool:
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


def extract_candidate_text(pdf_bytes: bytes) -> str:
    return extract_text_from_bytes(pdf_bytes)


def resolve_candidate_score(supabase, extracted: dict, job_id: str | None):
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

    return {
        "score": 0,
        "dimension_scores": {},
        "confidence": 0.0,
        "reasoning": "",
        "matched_keywords": [],
        "missing_keywords": [],
    }, resolved_job_id


def insert_candidate(supabase, payload: dict, drive_file_id: str):
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
                "status": "skipped",
                "reason": "duplicate",
                "drive_file_id": drive_file_id,
            }

        raise

# --------------------------------------------------------------------------- #
# MAIN PROCESSOR (NO CELERY)
# --------------------------------------------------------------------------- #

def process_drive_file(drive_file_id: str, job_id: str | None = None) -> dict:
    supabase = get_supabase_admin()

    try:
        # 1. idempotency
        if candidate_exists(supabase, drive_file_id):
            return {"status": "skipped"}

        # 2. metadata + download
        metadata = get_file_metadata(drive_file_id)

        file_name = sanitize_filename(
            metadata.get("name", f"{drive_file_id}.pdf")
        )

        pdf_bytes = download_file_bytes(drive_file_id)

        # 3. upload to storage
        cv_url = upload_cv_to_storage(
            supabase,
            drive_file_id,
            file_name,
            pdf_bytes,
        )

        # 4. extract text
        raw_text = extract_candidate_text(pdf_bytes)

        if not raw_text.strip():
            return {
                "status": "failed",
                "reason": "empty_text",
                "drive_file_id": drive_file_id,
            }

        # 5. AI extraction
        extracted = extract_cv_info(raw_text)

        # 6. scoring
        score_result, resolved_job_id = resolve_candidate_score(
            supabase,
            extracted,
            job_id,
        )

        # 7. build payload
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

        # 8. insert
        return insert_candidate(
            supabase,
            payload,
            drive_file_id,
        )

    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "drive_file_id": drive_file_id,
        }

# --------------------------------------------------------------------------- #
# DRIVE SYNC (NO CELERY)
# --------------------------------------------------------------------------- #

def sync_drive_folder(job_id: str | None = None) -> dict:
    settings = get_settings()

    if not settings.drive_folder_id:
        return {
            "status": "skipped",
            "reason": "missing_drive_folder_id",
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
        for row in (existing.data or [])
        if row.get("drive_file_id")
    }

    queued = 0

    for file_data in files:
        file_id = file_data["id"]

        if file_id in processed_ids:
            continue

        # direct call (NO CELERY)
        process_drive_file(file_id, job_id)
        queued += 1

    return {
        "status": "done",
        "total_files": len(files),
        "queued": queued,
    }

# --------------------------------------------------------------------------- #
# WEBHOOK SYNC (NO CELERY)
# --------------------------------------------------------------------------- #

def sync_drive_webhook(job_id: str | None = None) -> dict:
    settings = get_settings()

    if not settings.drive_folder_id:
        return {
            "status": "skipped",
            "reason": "missing_drive_folder_id",
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
        return sync_drive_folder(job_id)

    new_files, next_token = list_new_pdf_files_since(
        settings.drive_folder_id,
        page_token,
    )

    for file_data in new_files:
        process_drive_file(file_data["id"], job_id)

    supabase.table("app_config").upsert(
        {
            "key": "drive_page_token",
            "value": next_token,
        }
    ).execute()

    return {
        "status": "done",
        "new_files": len(new_files),
    }

# --------------------------------------------------------------------------- #
# WEBHOOK RENEWAL
# --------------------------------------------------------------------------- #

def renew_drive_webhook() -> dict:
    from app.services.webhook_manager import ensure_webhook_registered
    return ensure_webhook_registered()