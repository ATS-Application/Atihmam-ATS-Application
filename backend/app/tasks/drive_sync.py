"""
Drive Sync Pipeline — v2.2

Pipeline:
1. Scan Google Drive folder
2. Detect new PDFs
3. Download file
4. Upload to Supabase storage
5. Extract text (isolated subprocess)
6. AI parsing
7. Score candidate  (job match → best active job → synthetic quality fallback)
8. Insert into DB

Changelog v2.2:
- Fixed: dangling logger.info / raw_text references leaked into resolve_candidate_score
- Fixed: safe_extract_text was defined after its only call-site; moved to top of module
- Fixed: process_drive_file now uses safe_extract_text instead of the bare extract_text_from_bytes
- Supabase client created once per sync, passed into process_drive_file
- dimension_scores damping in _quality_fallback does not mutate in-place
- insert_candidate duplicate check uses Postgres error code 23505 as primary signal
- Removed unused DOMAIN_SKILLS import
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import textwrap

from app.config import get_settings
from app.db.supabase_client import get_supabase_admin
from app.services.ai_service import extract_cv_info
from app.services.drive_service import (
    download_file_bytes,
    get_file_metadata,
    list_new_pdf_files_since,
    list_pdf_files,
)
from app.services.scoring_service import classify_domain, compute_candidate_score
from app.tasks.cv_processing import (
    build_candidate_payload,
    compute_best_job_match,
    fetch_active_jobs,
    fetch_job,
    _enrich_cv_data
)

logger = logging.getLogger(__name__)

# Quality-fallback dampening constants
_KW_DAMPEN  = 0.85
_KW_CAP     = 85.0
_SEM_DAMPEN = 0.80
_SEM_CAP    = 75.0


# --------------------------------------------------------------------------- #
# TEXT EXTRACTION  (defined first — used by process_drive_file below)
# --------------------------------------------------------------------------- #

def safe_extract_text(pdf_bytes: bytes, file_name: str) -> str:
    """
    Extract PDF text in an isolated subprocess so a native C crash
    (SIGABRT/SIGSEGV from a malformed PDF) cannot kill the Celery worker.
    """
    script = (
        "import sys; "
        "from app.services.cv_parser import extract_text_from_bytes; "
        "sys.stdout.write(extract_text_from_bytes(sys.stdin.buffer.read()))"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            input=pdf_bytes,
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")
            raise RuntimeError(
                f"PDF extraction failed (rc={result.returncode}): {stderr}"
            )
        return result.stdout.decode(errors="replace")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"PDF extraction timed out: {file_name}")


# --------------------------------------------------------------------------- #
# HELPERS
# --------------------------------------------------------------------------- #

def sanitize_filename(filename: str) -> str:
    name, ext = os.path.splitext(filename)
    cleaned_name = re.sub(r"[^a-zA-Z0-9_.-]", "", name.replace(" ", "_"))
    cleaned_ext = re.sub(r"[^a-zA-Z0-9.]", "", ext)
    if cleaned_ext.lower() != ".pdf":
        cleaned_ext = ".pdf"
    return f"{cleaned_name}{cleaned_ext}"


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
    # Path inside the bucket — no bucket name prefix
    storage_path = f"drive/{drive_file_id}/{file_name}"
    supabase.storage.from_("cvs").upload(
        storage_path,
        pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"},
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
        exc_str = str(exc)
        # Postgres unique-violation (23505) is authoritative; constraint name
        # is a fallback for environments that surface it differently.
        if "23505" in exc_str or "uq_candidates_drive_file_id" in exc_str:
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
    Balanced autonomous scoring when no job is available.
    Applies realistic dampening without mutating the score dict in-place.
    """
    position = (
        extracted.get("current_position")
        or extracted.get("title")
        or "Professionnel"
    )
    domain_str = classify_domain(position)

    skills       = extracted.get("skills", [])[:25]
    work_history = extracted.get("work_history", [])
    projects     = extracted.get("projects", [])

    exp_titles = [e.get("title", "") for e in work_history if e.get("title")]
    proj_names = [p.get("name",  "") for p in projects     if p.get("name")]

    synthetic_jd = textwrap.dedent(f"""
        Nous recherchons un {position} expérimenté.

        Compétences : {", ".join(skills) if skills else ""}
        Expérience  : {", ".join(exp_titles[:10]) if exp_titles else ""}
        Projets     : {", ".join(proj_names[:5]) if proj_names else ""}
    """).strip()

    cv_data = dict(extracted)
    raw_text = extracted.get("raw_text") or extracted.get("full_text") or ""
    if raw_text:
        cv_data["raw_text"] = raw_text

    result = compute_candidate_score(
        cv_data=cv_data,
        job_title=position,
        job_requirements=synthetic_jd,
    )

    # Dampen keyword/semantic scores without mutating the original dict
    original_dims = result.get("dimension_scores", {})
    dampened_dims = {
        **original_dims,
        "keyword_score":  min(original_dims.get("keyword_score",  0) * _KW_DAMPEN,  _KW_CAP),
        "semantic_score": min(original_dims.get("semantic_score", 0) * _SEM_DAMPEN, _SEM_CAP),
    }
    return {
        **result,
        "dimension_scores": dampened_dims,
        "reasoning": f"Score qualité autonome — {domain_str}",
    }


def resolve_candidate_score(
    supabase,
    extracted: dict,
    job_id: str | None,
) -> tuple[dict, str | None]:
    """
    Three-tier scoring resolution:
      1. Explicit job_id → score against that job
      2. Best-matching active job
      3. Quality fallback (synthetic JD from CV content)
    """
    if job_id:
        job = fetch_job(supabase, job_id)
        if job:
            score_result = compute_candidate_score(
                cv_data=extracted,
                job_title=job.get("title", ""),
                job_requirements=job.get("requirements", ""),
                supabase=supabase,
            )
            return score_result, job_id

    jobs = fetch_active_jobs(supabase)
    if jobs:
        best_result, best_id = compute_best_job_match(supabase, extracted, jobs)
        if best_result:
            return best_result, best_id

    # Tier 3: no job available — synthetic quality score
    return _quality_fallback(extracted), None


# --------------------------------------------------------------------------- #
# MAIN PROCESSOR
# --------------------------------------------------------------------------- #

def process_drive_file(
    drive_file_id: str,
    supabase,                       # injected by caller; no new client per file
    job_id: str | None = None,
) -> dict:
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

        # 4. Extract raw text (isolated subprocess to guard against C-level crashes)
        logger.info("Extracting text: %s (%d bytes)", file_name, len(pdf_bytes))
        raw_text = safe_extract_text(pdf_bytes, file_name)
        if not raw_text.strip():
            logger.warning("Empty text extracted from file: %s", drive_file_id)
            return {
                "status":        "failed",
                "reason":        "empty_text",
                "drive_file_id": drive_file_id,
            }

        # 5. AI extraction
        extracted = _enrich_cv_data(extracted, raw_text)

        # 6. Scoring
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

    except Exception:
        logger.exception("Error processing Drive file %s", drive_file_id)
        return {"status": "error", "drive_file_id": drive_file_id}


# --------------------------------------------------------------------------- #
# FULL FOLDER SYNC
# --------------------------------------------------------------------------- #

def sync_drive_folder(job_id: str | None = None) -> dict:
    settings = get_settings()

    if not settings.drive_folder_id:
        return {"status": "skipped", "reason": "missing_drive_folder_id"}

    supabase = get_supabase_admin()  # single client for the entire sync
    files    = list_pdf_files(settings.drive_folder_id)

    existing = supabase.table("candidates").select("drive_file_id").execute()
    processed_ids = {
        row["drive_file_id"]
        for row in (existing.data or [])
        if row.get("drive_file_id")
    }

    results = [
        process_drive_file(file_data["id"], supabase, job_id)
        for file_data in files
        if file_data["id"] not in processed_ids
    ]

    errors = [r for r in results if r.get("status") == "error"]
    logger.info(
        "sync_drive_folder complete — total=%d queued=%d errors=%d",
        len(files), len(results), len(errors),
    )
    return {
        "status":      "done",
        "total_files": len(files),
        "queued":      len(results),
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

    if not page_token:
        logger.info("No page token found — falling back to full folder sync")
        return sync_drive_folder(job_id)

    new_files, next_token = list_new_pdf_files_since(
        settings.drive_folder_id,
        page_token,
    )

    results = [process_drive_file(f["id"], supabase, job_id) for f in new_files]
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