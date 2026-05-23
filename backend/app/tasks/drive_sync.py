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


_PERMANENT_ERRORS = (
    ValueError,
    PermissionError,
)


def sanitize_filename(filename: str) -> str:
    name, ext = os.path.splitext(filename)
    name = name.replace(" ", "_")
    name = re.sub(r"[^a-zA-Z0-9_.-]", "", name)
    return f"{name}{ext}"


def _compute_score(
    supabase,
    extracted: dict,
    job_id: str | None,
) -> tuple[float, str | None]:

    resolved_job_id = job_id

    try:
        # ------------------------------------------------
        # SPECIFIC JOB
        # ------------------------------------------------
        if resolved_job_id:
            job_resp = (
                supabase.table("jobs")
                .select("id, title, requirements")
                .eq("id", resolved_job_id)
                .single()
                .execute()
            )

            if not job_resp.data:
                return 0.0, None

            job = job_resp.data

            raw_score = score_candidate(
                cv_data=extracted,
                job_title=job["title"],
                job_requirements=job.get(
                    "requirements",
                    "",
                ),
            )

            score = float(raw_score or 0)

            print(f"[ATS SCORE] {score}")

            return score, resolved_job_id

        # ------------------------------------------------
        # AUTO MATCH BEST JOB
        # ------------------------------------------------
        jobs_resp = (
            supabase.table("jobs")
            .select("id, title, requirements")
            .eq("is_active", True)
            .execute()
        )

        jobs = jobs_resp.data or []

        if not jobs:
            return 0.0, None

        best_score = 0.0
        best_job_id = None

        for job in jobs:

            try:
                raw_score = score_candidate(
                    cv_data=extracted,
                    job_title=job["title"],
                    job_requirements=job.get(
                        "requirements",
                        "",
                    ),
                )

                score = float(raw_score or 0)

                print(
                    f"[JOB SCORE] "
                    f"{job['title']} => {score}"
                )

                if score > best_score:
                    best_score = score
                    best_job_id = job["id"]

            except Exception as e:
                print(
                    f"[SCORING ERROR] "
                    f"{job['title']} => {e}"
                )

        return best_score, best_job_id

    except Exception as e:
        print(f"[COMPUTE SCORE ERROR] {e}")
        return 0.0, None


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_drive_file(self, drive_file_id: str, job_id: str | None = None):
    """
    Pipeline for a single Drive file:
    idempotency check → download → upload to Storage → AI parse → score → insert candidate.
    """
    supabase = get_supabase_admin()
    try:
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

        extracted = extract_cv_info(raw_text)

        # Always attempt scoring — falls back to best active job when job_id is None
        score, resolved_job_id = _compute_score(supabase, extracted, job_id)

        candidate_payload = {
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
            candidate_payload["job_id"] = resolved_job_id
        if score is not None:
            candidate_payload["score"] = float(score or 0)

        try:
            response = supabase.table("candidates").insert(candidate_payload).execute()
        except Exception as db_exc:
            if "uq_candidates_drive_file_id" in str(db_exc):
                return {"status": "skipped_race", "drive_file_id": drive_file_id}
            raise

        return {"status": "processed", "candidate_id": response.data[0]["id"]}

    except _PERMANENT_ERRORS:
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


@shared_task
def backfill_scores():
    """One-shot backfill: scores existing candidates that have NULL score."""
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
                    "score": score,
                    "job_id": row.get("job_id") or resolved_job_id,
                }
            ).eq("id", row["id"]).execute()
            updated += 1

    return {"updated": updated, "total": len(rows.data)}