# tasks/drive_sync.py
import re
import os
from celery import shared_task
from app.services.drive_service import (
    download_file_bytes,
    list_pdf_files,
    list_new_pdf_files_since,
    get_file_metadata,
)
from app.services.cv_parser import extract_text_from_bytes
from app.services.ai_service import extract_cv_info, score_candidate
from app.db.supabase_client import get_supabase_admin
from app.config import get_settings


# Exceptions that signal a permanent failure — retrying will never help.
_PERMANENT_ERRORS = (
    ValueError,       # e.g. empty CV text, malformed data
    PermissionError,  # service account lost access to the file
)


def sanitize_filename(filename: str) -> str:
    """Removes non-ASCII characters, spaces, and special symbols 
    to prevent Supabase Storage 400 InvalidKey errors.
    """
    name, ext = os.path.splitext(filename)
    # Replace spaces with underscores
    name = name.replace(" ", "_")
    # Strip out any remaining characters outside alphanumeric, underscores, dots, or hyphens
    name = re.sub(r"[^a-zA-Z0-9_.-]", "", name)
    return f"{name}{ext}"


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_drive_file(self, drive_file_id: str, job_id: str | None = None):
    """Pipeline for a single Drive file:
    idempotency check → download → upload to Storage → AI parse → score → insert candidate.
    """
    supabase = get_supabase_admin()
    try:
        # Fast-path: skip download entirely if already processed.
        existing = (
            supabase.table("candidates")
            .select("id")
            .eq("drive_file_id", drive_file_id)
            .execute()
        )
        if existing.data:
            return {"status": "skipped", "drive_file_id": drive_file_id}

        metadata = get_file_metadata(drive_file_id)
        raw_file_name = metadata.get("name", f"{drive_file_id}.pdf")
        
        # FIX: Sanitize the filename to eliminate spaces and special symbols
        file_name = sanitize_filename(raw_file_name)
        pdf_bytes = download_file_bytes(drive_file_id)

        storage_path = f"cvs/drive/{drive_file_id}/{file_name}"
        supabase.storage.from_("cvs").upload(
            storage_path,
            pdf_bytes,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )
        cv_url = supabase.storage.from_("cvs").get_public_url(storage_path)

        raw_text = extract_text_from_bytes(pdf_bytes)
        if not raw_text.strip():
            # If the PDF is completely blank or an unreadable image scan, update status
            # to let the UI know why it has no name, then raise ValueError to halt cleanly.
            try:
                fallback_payload = {
                    "full_name": "Document non lisible",
                    "cv_file_url": cv_url,
                    "drive_file_id": drive_file_id,
                    "status": "failed",
                }
                if job_id:
                    fallback_payload["job_id"] = job_id
                supabase.table("candidates").insert(fallback_payload).execute()
            except Exception:
                pass
            raise ValueError(f"Empty text extracted from Drive file {drive_file_id}")

        # AI extraction receives the full text.
        extracted = extract_cv_info(raw_text)

        score = None
        if job_id:
            job_resp = (
                supabase.table("jobs")
                .select("title, requirements")
                .eq("id", job_id)
                .single()
                .execute()
            )
            if job_resp.data:
                score = score_candidate(
                    cv_data=extracted,
                    job_title=job_resp.data["title"],
                    job_requirements=job_resp.data.get("requirements", ""),
                )

        candidate_payload = {
            "full_name": extracted.get("full_name") or "Sans nom",
            "email": extracted.get("email"),
            "phone": extracted.get("phone"),
            "current_position": extracted.get("current_position"),
            "skills": extracted.get("skills", []),
            "experience_years": extracted.get("experience_years"),
            "cv_file_url": cv_url,
            "cv_raw_text": raw_text[:50_000],
            "ai_extracted_data": extracted,
            "drive_file_id": drive_file_id,
            "status": "applied",
        }
        if job_id:
            candidate_payload["job_id"] = job_id
        if score is not None:
            candidate_payload["score"] = score

        try:
            response = supabase.table("candidates").insert(candidate_payload).execute()
        except Exception as db_exc:
            if "uq_candidates_drive_file_id" in str(db_exc):
                return {"status": "skipped_race", "drive_file_id": drive_file_id}
            raise

        return {"status": "processed", "candidate_id": response.data[0]["id"]}

    except _PERMANENT_ERRORS as exc:
        raise

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def sync_drive_folder(job_id: str | None = None):
    """Full folder scan — safety net for missed webhooks. Runs daily via Beat."""
    settings = get_settings()
    folder_id = settings.drive_folder_id

    if not folder_id:
        return {"status": "skipped", "reason": "DRIVE_FOLDER_ID not configured"}

    supabase = get_supabase_admin()
    files = list_pdf_files(folder_id)

    existing = supabase.table("candidates").select("drive_file_id").execute()
    processed_ids = {r["drive_file_id"] for r in existing.data if r.get("drive_file_id")}

    queued = 0
    for f in files:
        if f["id"] not in processed_ids:
            process_drive_file.delay(drive_file_id=f["id"], job_id=job_id)
            queued += 1

    return {"status": "done", "total_files": len(files), "queued": queued}


@shared_task
def sync_drive_webhook(job_id: str | None = None):
    """Handle a Drive push notification."""
    settings = get_settings()
    folder_id = settings.drive_folder_id
    if not folder_id:
        return {"status": "skipped", "reason": "DRIVE_FOLDER_ID not configured"}

    supabase = get_supabase_admin()
    config_row = (
        supabase.table("app_config")
        .select("value")
        .eq("key", "drive_page_token")
        .single()
        .execute()
    )
    page_token = config_row.data["value"] if config_row.data else None
    if not page_token:
        return sync_drive_folder(job_id=job_id)

    new_files, next_token = list_new_pdf_files_since(folder_id, page_token)

    queued = 0
    for f in new_files:
        process_drive_file.delay(drive_file_id=f["id"], job_id=job_id)
        queued += 1

    supabase.table("app_config").upsert(
        {"key": "drive_page_token", "value": next_token}
    ).execute()

    return {"status": "done", "new_files": len(new_files), "queued": queued}


@shared_task
def renew_drive_webhook():
    """Renews the Drive webhook channel before expiration. Runs every 12h via Beat."""
    from app.services.webhook_manager import ensure_webhook_registered
    return ensure_webhook_registered()