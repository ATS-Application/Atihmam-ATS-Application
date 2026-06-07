# app/tasks/drive_sync.py

"""
Drive Sync Pipeline 

Pipeline:
1. Scan Google Drive folder
2. Detect new PDFs
3. Download file
4. Upload to Supabase storage
5. Extract text
6. AI parsing
7. Score candidate  (job match → best active job → synthetic quality fallback)
8. Insert into DB
"""

from __future__ import annotations

import logging
import os
import re

from app.config import get_settings
from app.db.supabase_client import get_supabase_admin
from app.services.ai_service import extract_cv_info
from app.services.cv_parser import extract_text_from_bytes
from app.services.drive_service import (
    download_file_bytes,
    get_file_metadata,
    list_new_pdf_files_since,
    list_pdf_files,
)
from app.services.scoring_service import (
    compute_candidate_score,
    classify_domain,
    Domain,
    DOMAIN_SKILLS,
)
from app.tasks.cv_processing import (
    build_candidate_payload,
    compute_best_job_match,
    fetch_active_jobs,
    fetch_job,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# HELPERS
# --------------------------------------------------------------------------- #

def sanitize_filename(filename: str) -> str:
    name, ext = os.path.splitext(filename)
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "", name.replace(" ", "_"))
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


def insert_candidate(supabase, payload: dict, drive_file_id: str) -> dict:
    try:
        response = supabase.table("candidates").insert(payload).execute()
        return {
            "status":       "processed",
            "candidate_id": response.data[0]["id"],
        }
    except Exception as exc:
        if "uq_candidates_drive_file_id" in str(exc):
            return {
                "status":        "skipped",
                "reason":        "duplicate",
                "drive_file_id": drive_file_id,
            }
        raise


# --------------------------------------------------------------------------- #
# SCORING
# --------------------------------------------------------------------------- #

def _quality_fallback(extracted: dict) -> dict:
    """
    Strong autonomous quality scoring.
    Uses the FULL raw CV text + real extracted content to generate a high-quality synthetic JD.
    This dramatically improves keyword_score and semantic_score.
    """
    position = extracted.get("current_position") or extracted.get("title", "") or "Professionnel"
    domain_str = classify_domain(position)

    # === Build rich synthetic JD from REAL CV content ===
    skills = extracted.get("skills", [])[:25]
    work_history = extracted.get("work_history", [])
    projects = extracted.get("projects", [])

    exp_titles = [exp.get("title", "") for exp in work_history if exp.get("title")]
    proj_names = [p.get("name", "") for p in projects if p.get("name")]

    skills_str = ", ".join(skills) if skills else "compétences professionnelles"
    exp_str = ", ".join(exp_titles[:12]) if exp_titles else ""
    proj_str = ", ".join(proj_names[:8]) if proj_names else ""

    synthetic_title = position

    synthetic_jd = f"""
    Nous recherchons un {synthetic_title} expérimenté dans le domaine {domain_str}.
    
    Compétences requises : {skills_str}.
    """

    if exp_str:
        synthetic_jd += f"Expériences attendues : {exp_str}. "
    if proj_str:
        synthetic_jd += f"Projets réalisés : {proj_str}. "

    synthetic_jd += """
    Le candidat idéal doit démontrer une forte capacité d'analyse, de gestion de projets, 
    de leadership et une excellente qualité rédactionnelle.
    """

    # Critical: Use full raw text
    cv_data = dict(extracted)
    raw_text = extracted.get("raw_text") or extracted.get("full_text") or ""
    if raw_text:
        cv_data["raw_text"] = raw_text

    result = compute_candidate_score(
        cv_data=cv_data,
        job_title=synthetic_title,
        job_requirements=synthetic_jd,
    )

    result["reasoning"] = (
        f"Score qualité autonome — domaine détecté : {domain_str}. "
        "Scoring basé sur la richesse et la cohérence interne du CV."
    )
    result["matched_job"] = None

    return result


def resolve_candidate_score(
    supabase,
    extracted: dict,
    job_id: str | None,
) -> tuple[dict, str | None]:
    """
    Scoring strategy (mirrors process_cv exactly):
      1. Explicit job_id  → score against that job
      2. No job_id        → find best match among active jobs
      3. No active jobs   → synthetic JD quality score (all 8 dimensions)

    Returns (score_result, resolved_job_id).
    """
    resolved_job_id = job_id

    if job_id:
        job = fetch_job(supabase, job_id)
        if job:
            score_result = compute_candidate_score(
                cv_data=extracted,
                job_title=job.get("title", ""),
                job_requirements=job.get("requirements", ""),
            )
            return score_result, resolved_job_id
    else:
        jobs = fetch_active_jobs(supabase)
        if jobs:
            score_result, resolved_job_id = compute_best_job_match(
                supabase=supabase,
                cv_info=extracted,
                jobs=jobs,
            )
            if score_result:
                return score_result, resolved_job_id

    # Fallback: no job linked and no active jobs
    logger.info("No active jobs — computing synthetic quality score")
    return _quality_fallback(extracted), resolved_job_id


# --------------------------------------------------------------------------- #
# MAIN PROCESSOR
# --------------------------------------------------------------------------- #

def process_drive_file(drive_file_id: str, job_id: str | None = None) -> dict:
    supabase = get_supabase_admin()

    try:
        # 1. Idempotency check
        if candidate_exists(supabase, drive_file_id):
            logger.info("Skipping already-processed file: %s", drive_file_id)
            return {"status": "skipped", "drive_file_id": drive_file_id}

        # 2. Fetch metadata + download PDF
        metadata  = get_file_metadata(drive_file_id)
        file_name = sanitize_filename(metadata.get("name", f"{drive_file_id}.pdf"))
        pdf_bytes = download_file_bytes(drive_file_id)

        # 3. Upload to Supabase storage
        cv_url = upload_cv_to_storage(supabase, drive_file_id, file_name, pdf_bytes)

        # 4. Extract raw text
        raw_text = extract_text_from_bytes(pdf_bytes)
        if not raw_text.strip():
            logger.warning("Empty text extracted from file: %s", drive_file_id)
            return {
                "status":        "failed",
                "reason":        "empty_text",
                "drive_file_id": drive_file_id,
            }

        # 5. AI extraction
        extracted = extract_cv_info(raw_text)

        # 6. Scoring (job match → best active job → synthetic quality fallback)
        score_result, resolved_job_id = resolve_candidate_score(
            supabase, extracted, job_id
        )
        logger.info(
            "Scored file %s → %.1f (job_id=%s)",
            drive_file_id,
            score_result.get("score", 0),
            resolved_job_id,
        )

        # 7. Build DB payload
        payload = build_candidate_payload(
            raw_text=raw_text,
            cv_info=extracted,
            score_result=score_result,
            job_id=resolved_job_id,
        )
        payload.update({
            "cv_file_url":   cv_url,
            "drive_file_id": drive_file_id,
            "status":        "applied",
        })

        # 8. Insert
        return insert_candidate(supabase, payload, drive_file_id)

    except Exception as exc:
        logger.exception("Error processing Drive file %s", drive_file_id)
        return {
            "status":        "error",
            "error":         str(exc),
            "drive_file_id": drive_file_id,
        }


# --------------------------------------------------------------------------- #
# FULL FOLDER SYNC
# --------------------------------------------------------------------------- #

def sync_drive_folder(job_id: str | None = None) -> dict:
    settings = get_settings()

    if not settings.drive_folder_id:
        return {"status": "skipped", "reason": "missing_drive_folder_id"}

    supabase = get_supabase_admin()
    files    = list_pdf_files(settings.drive_folder_id)

    existing = supabase.table("candidates").select("drive_file_id").execute()
    processed_ids = {
        row["drive_file_id"]
        for row in (existing.data or [])
        if row.get("drive_file_id")
    }

    results = []
    queued  = 0

    for file_data in files:
        file_id = file_data["id"]
        if file_id in processed_ids:
            continue
        result = process_drive_file(file_id, job_id)
        results.append(result)
        queued += 1

    errors = [r for r in results if r.get("status") == "error"]
    logger.info(
        "sync_drive_folder complete — total=%d queued=%d errors=%d",
        len(files), queued, len(errors),
    )

    return {
        "status":      "done",
        "total_files": len(files),
        "queued":      queued,
        "errors":      len(errors),
    }


# --------------------------------------------------------------------------- #
# WEBHOOK-BASED INCREMENTAL SYNC
# --------------------------------------------------------------------------- #

def sync_drive_webhook(job_id: str | None = None) -> dict:
    settings = get_settings()

    if not settings.drive_folder_id:
        return {"status": "skipped", "reason": "missing_drive_folder_id"}

    supabase = get_supabase_admin()

    config_row = (
        supabase.table("app_config")
        .select("value")
        .eq("key", "drive_page_token")
        .single()
        .execute()
    )
    page_token = config_row.data["value"] if config_row.data else None

    # No stored token → fall back to full folder scan
    if not page_token:
        logger.info("No page token found — falling back to full folder sync")
        return sync_drive_folder(job_id)

    new_files, next_token = list_new_pdf_files_since(
        settings.drive_folder_id,
        page_token,
    )

    results = [process_drive_file(f["id"], job_id) for f in new_files]
    errors  = [r for r in results if r.get("status") == "error"]

    supabase.table("app_config").upsert(
        {"key": "drive_page_token", "value": next_token}
    ).execute()

    logger.info(
        "sync_drive_webhook complete — new=%d errors=%d",
        len(new_files), len(errors),
    )

    return {
        "status":    "done",
        "new_files": len(new_files),
        "errors":    len(errors),
    }


# --------------------------------------------------------------------------- #
# WEBHOOK RENEWAL
# --------------------------------------------------------------------------- #

def renew_drive_webhook() -> dict:
    from app.services.webhook_manager import ensure_webhook_registered
    return ensure_webhook_registered()
