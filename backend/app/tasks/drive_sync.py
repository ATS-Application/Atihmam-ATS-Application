# backend/app/tasks/drive_sync.py

import os
import re

from celery import shared_task
from googleapiclient.errors import HttpError

from app.config import get_settings
from app.db.supabase_client import get_supabase_admin
from app.services.ai_service import extract_cv_info, score_candidate
from app.services.cv_parser import extract_text_from_bytes
from app.services.drive_service import (
    _get_drive_service,
    download_file_bytes,
    get_file_metadata,
    list_new_pdf_files_since,
    list_pdf_files,
)

_PERMANENT_ERRORS = (ValueError, PermissionError)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitize_filename(filename: str) -> str:
    name, ext = os.path.splitext(filename)
    name = re.sub(r"[^a-zA-Z0-9_.-]", "", name.replace(" ", "_"))
    return f"{name}{ext}"


def _extract_scalar_score(raw) -> float:
    """
    Normalize whatever score_candidate returns into a float.

    compute_candidate_score returns a rich dict — we extract
    the "score" key.  Also handles plain int/float for safety.
    """
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        for key in ("score", "total", "final_score", "overall", "total_score"):
            val = raw.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        for val in raw.values():
            if isinstance(val, (int, float)):
                return float(val)
    return 0.0


def _compute_score(
    supabase,
    extracted: dict,
    job_id: str | None,
) -> tuple[float, str | None]:
    """
    Score a candidate against a specific job or all active jobs (best match).

    Returns (score, resolved_job_id).
    Never raises — returns (0.0, None) on any failure so the pipeline
    can continue even if scoring is unavailable.
    """
    try:
        if job_id:
            row = (
                supabase.table("jobs")
                .select("id, title, requirements")
                .eq("id", job_id)
                .single()
                .execute()
            )
            if not row.data:
                return 0.0, None

            job = row.data
            raw = score_candidate(
                cv_data=extracted,
                job_title=job["title"],
                job_requirements=job.get("requirements", ""),
            )
            score = _extract_scalar_score(raw)
            print(f"[ATS SCORE] job={job_id} score={score}")
            return score, job_id

        # --- auto-match: score against every active job ---
        jobs_resp = (
            supabase.table("jobs")
            .select("id, title, requirements")
            .eq("is_active", True)
            .execute()
        )
        jobs: list[dict] = jobs_resp.data or []

        if not jobs:
            return 0.0, None

        best_score = 0.0
        best_job_id: str | None = None

        for job in jobs:
            try:
                raw = score_candidate(
                    cv_data=extracted,
                    job_title=job["title"],
                    job_requirements=job.get("requirements", ""),
                )
                score = _extract_scalar_score(raw)
                print(f"[JOB SCORE] {job['title']} => {score}")

                if score > best_score:
                    best_score = score
                    best_job_id = job["id"]

            except Exception as exc:  # noqa: BLE001
                print(f"[SCORING ERROR] {job['title']} => {exc}")

        return best_score, best_job_id

    except Exception as exc:  # noqa: BLE001
        print(f"[COMPUTE SCORE ERROR] {exc}")
        return 0.0, None


def _insert_failed_candidate(
    supabase,
    cv_url: str,
    drive_file_id: str,
    job_id: str | None,
) -> None:
    """Insert a stub row for files whose text could not be extracted."""
    payload: dict = {
        "full_name": "Document non lisible",
        "cv_file_url": cv_url,
        "drive_file_id": drive_file_id,
        "status": "failed",
    }
    if job_id:
        payload["job_id"] = job_id

    try:
        supabase.table("candidates").insert(payload).execute()
    except Exception:  # noqa: BLE001
        pass  # best-effort — don't mask the original ValueError


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_drive_file(self, drive_file_id: str, job_id: str | None = None):
    """
    Single-file pipeline:
      idempotency → download → Storage upload → AI parse → score → insert

    Permanent errors (ValueError, PermissionError) propagate immediately.
    Transient errors are retried with exponential back-off (60s, 120s, 240s).
    A 401 from the Drive API clears the service cache before retrying.
    """
    supabase = get_supabase_admin()

    try:
        # --- idempotency guard ---
        existing = (
            supabase.table("candidates")
            .select("id")
            .eq("drive_file_id", drive_file_id)
            .execute()
        )
        if existing.data:
            return {"status": "skipped", "drive_file_id": drive_file_id}

        # --- fetch & download ---
        metadata = get_file_metadata(drive_file_id)
        file_name = sanitize_filename(metadata.get("name", f"{drive_file_id}.pdf"))
        pdf_bytes = download_file_bytes(drive_file_id)

        # --- upload to Supabase Storage ---
        storage_path = f"cvs/drive/{drive_file_id}/{file_name}"
        supabase.storage.from_("cvs").upload(
            storage_path,
            pdf_bytes,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )
        cv_url = supabase.storage.from_("cvs").get_public_url(storage_path)

        # --- text extraction ---
        raw_text = extract_text_from_bytes(pdf_bytes)
        if not raw_text.strip():
            _insert_failed_candidate(supabase, cv_url, drive_file_id, job_id)
            raise ValueError(f"Empty text extracted from Drive file {drive_file_id}")

        # --- AI extraction + scoring ---
        extracted = extract_cv_info(raw_text)
        score, resolved_job_id = _compute_score(supabase, extracted, job_id)

        # --- build & insert candidate row ---
        payload: dict = {
            "full_name": extracted.get("full_name") or "Sans nom",
            "email": extracted.get("email"),
            "phone": extracted.get("phone"),
            "current_position": extracted.get("current_position"),
            "skills": extracted.get("skills") or [],
            "experience_years": extracted.get("experience_years"),
            "cv_file_url": cv_url,
            "cv_raw_text": raw_text[:50_000],
            "ai_extracted_data": extracted,
            "drive_file_id": drive_file_id,
            "status": "applied",
        }
        if resolved_job_id:
            payload["job_id"] = resolved_job_id
        if score is not None:
            payload["score"] = float(score)

        try:
            response = supabase.table("candidates").insert(payload).execute()
        except Exception as db_exc:
            if "uq_candidates_drive_file_id" in str(db_exc):
                return {"status": "skipped_race", "drive_file_id": drive_file_id}
            raise

        return {"status": "processed", "candidate_id": response.data[0]["id"]}

    except _PERMANENT_ERRORS:
        raise

    except HttpError as exc:
        if exc.status_code == 401:
            _get_drive_service.cache_clear()
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def sync_drive_folder(job_id: str | None = None) -> dict:
    """
    Full folder scan — safety net for missed webhooks.
    Dispatches process_drive_file for every unseen PDF.
    Runs daily via Celery Beat.
    """
    settings = get_settings()
    folder_id = settings.drive_folder_id

    if not folder_id:
        return {"status": "skipped", "reason": "DRIVE_FOLDER_ID not configured"}

    supabase = get_supabase_admin()
    files = list_pdf_files(folder_id)

    existing = supabase.table("candidates").select("drive_file_id").execute()
    processed_ids = {
        row["drive_file_id"]
        for row in existing.data
        if row.get("drive_file_id")
    }

    queued = 0
    for f in files:
        if f["id"] not in processed_ids:
            process_drive_file.delay(drive_file_id=f["id"], job_id=job_id)
            queued += 1

    return {"status": "done", "total_files": len(files), "queued": queued}


@shared_task
def sync_drive_webhook(job_id: str | None = None) -> dict:
    """
    Handle a Drive push notification.
    Reads the persisted page token, walks the changes feed,
    dispatches tasks for new PDFs, then advances the token.
    Falls back to a full sync when no token is stored.
    """
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
    page_token: str | None = config_row.data["value"] if config_row.data else None

    if not page_token:
        return sync_drive_folder(job_id=job_id)

    new_files, next_token = list_new_pdf_files_since(folder_id, page_token)

    for f in new_files:
        process_drive_file.delay(drive_file_id=f["id"], job_id=job_id)

    supabase.table("app_config").upsert(
        {"key": "drive_page_token", "value": next_token}
    ).execute()

    return {"status": "done", "new_files": len(new_files), "queued": len(new_files)}


@shared_task
def renew_drive_webhook() -> dict:
    """
    Renew the Drive push-notification channel before it expires.
    Runs every 12 h via Celery Beat.
    """
    from app.services.webhook_manager import ensure_webhook_registered  # noqa: PLC0415

    return ensure_webhook_registered()


@shared_task
def backfill_scores() -> dict:
    """
    One-shot backfill: score all candidates whose `score` column is NULL
    but whose `ai_extracted_data` is populated.
    Safe to re-run — already-scored rows are excluded by the query.
    """
    supabase = get_supabase_admin()

    rows = (
        supabase.table("candidates")
        .select("id, ai_extracted_data, job_id")
        .is_("score", "null")
        .not_.is_("ai_extracted_data", "null")
        .execute()
    )

    updated = 0
    for row in rows.data:
        score, resolved_job_id = _compute_score(
            supabase,
            row["ai_extracted_data"],
            row.get("job_id"),
        )
        if score is not None:
            supabase.table("candidates").update(
                {
                    "score": float(score),
                    "job_id": row.get("job_id") or resolved_job_id,
                }
            ).eq("id", row["id"]).execute()
            updated += 1

    return {"updated": updated, "total": len(rows.data)}