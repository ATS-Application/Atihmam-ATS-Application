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
import mimetypes
import os
import re
import subprocess
import sys
import textwrap
import time

from app.config import get_settings
from app.db.supabase_client import get_supabase_admin
from app.services.ai_service import extract_cv_info
from app.services.drive_service import (
    download_file_bytes,
    get_file_metadata,
    get_start_page_token,
    list_pdf_files,
)
from app.services.scoring_service import classify_domain, compute_candidate_score, enrich_cv_data
from app.tasks.cv_processing import (
    build_candidate_payload,
    compute_best_job_match,
    fetch_active_jobs,
    fetch_job,
    _enrich_cv_data
)

logger = logging.getLogger(__name__)


def _resolve_drive_folder_id(settings) -> str:
    folder_id = (getattr(settings, "drive_folder_id", "") or "").strip()
    if not folder_id or folder_id.lower() == "root":
        return "root"
    return folder_id


# Quality-fallback dampening constants
_KW_DAMPEN  = 0.85
_KW_CAP     = 85.0
_SEM_DAMPEN = 0.80
_SEM_CAP    = 75.0


# --------------------------------------------------------------------------- #
# TEXT EXTRACTION  (defined first — used by process_drive_file below)
# --------------------------------------------------------------------------- #

def safe_extract_text(file_bytes: bytes, file_name: str) -> str:
    """
    Extract text from CV bytes. Tries in-process first (supports PDF/DOCX/images),
    then falls back to an isolated subprocess for malformed PDFs.
    """
    from app.services.cv_parser import extract_text_from_bytes

    try:
        text = extract_text_from_bytes(file_bytes)
        if text and text.strip():
            return text
    except Exception as exc:
        logger.warning("In-process extraction failed for %s: %s", file_name, exc)

    script = (
        "import sys; "
        "from app.services.cv_parser import extract_text_from_bytes; "
        "sys.stdout.write(extract_text_from_bytes(sys.stdin.buffer.read()))"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            input=file_bytes,
            capture_output=True,
            timeout=120,
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

def _extension_for_mime(mime_type: str | None) -> str:
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return ".docx"
    if mime_type == "application/msword":
        return ".doc"
    if mime_type == "image/jpeg":
        return ".jpg"
    return mimetypes.guess_extension(mime_type or "") or ".pdf"


def sanitize_filename(filename: str, mime_type: str | None = None) -> str:
    name, ext = os.path.splitext(filename)
    cleaned_name = re.sub(r"[^a-zA-Z0-9_.-]", "", name.replace(" ", "_"))
    cleaned_ext = re.sub(r"[^a-zA-Z0-9.]", "", ext)
    if not cleaned_ext:
        cleaned_ext = _extension_for_mime(mime_type)
    return f"{cleaned_name}{cleaned_ext}"


def fetch_all_drive_file_ids(supabase) -> set[str]:
    """Load every drive_file_id from candidates (paginated — PostgREST default is 1000)."""
    ids: set[str] = set()
    page_size = 1000
    offset = 0

    while True:
        response = (
            supabase.table("candidates")
            .select("drive_file_id")
            .not_.is_("drive_file_id", "null")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = response.data or []
        for row in rows:
            if row.get("drive_file_id"):
                ids.add(row["drive_file_id"])
        if len(rows) < page_size:
            break
        offset += page_size

    return ids


def _summarize_sync_results(results: list[dict], total_files: int, remaining: int = 0) -> dict:
    processed = [r for r in results if r.get("status") == "processed"]
    skipped   = [r for r in results if r.get("status") == "skipped"]
    failed    = [r for r in results if r.get("status") == "failed"]
    errors    = [r for r in results if r.get("status") == "error"]
    already_in_db = total_files - len(results) - remaining

    return {
        "status":           "partial" if remaining > 0 else "done",
        "total_files":      total_files,
        "already_in_db":    already_in_db,
        "attempted":        len(results),
        "processed":        len(processed),
        "skipped":          len(skipped),
        "failed":           len(failed),
        "errors":           len(errors),
        "empty_text":       len([r for r in failed if r.get("reason") == "empty_text"]),
        "remaining":        remaining,
        # backwards-compatible keys
        "queued":           len(results),
    }


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
    file_bytes: bytes,
    mime_type: str | None = None,
) -> str:
    # Path inside the bucket — no bucket name prefix
    storage_path = f"drive/{drive_file_id}/{file_name}"
    supabase.storage.from_("cvs").upload(
        storage_path,
        file_bytes,
        file_options={
            "content-type": mime_type or "application/octet-stream",
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

        # 2. Fetch metadata + download file
        metadata  = get_file_metadata(drive_file_id)
        mime_type = metadata.get("mimeType")
        file_name = sanitize_filename(metadata.get("name", drive_file_id), mime_type)
        file_bytes = download_file_bytes(drive_file_id)

        # 3. Upload to Supabase storage
        cv_url = upload_cv_to_storage(
            supabase,
            drive_file_id,
            file_name,
            file_bytes,
            mime_type,
        )

        # 4. Extract raw text (isolated subprocess to guard against C-level crashes)
        logger.info("Extracting text: %s (%d bytes)", file_name, len(file_bytes))
        raw_text = safe_extract_text(file_bytes, file_name)
        if not raw_text.strip():
            logger.warning("Empty text extracted from file: %s", drive_file_id)
            return {
                "status":        "failed",
                "reason":        "empty_text",
                "drive_file_id": drive_file_id,
            }

        # 5. AI extraction
        extracted = extract_cv_info(raw_text)

        # Enrich with raw_text so keyword/semantic/education/cert scorers see
        # the full CV body, not the sparse _build_cv_text reconstruction.
        enriched = enrich_cv_data(extracted, raw_text)

        # 6. Scoring
        score_result, resolved_job_id = resolve_candidate_score(
            supabase, enriched, job_id
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
            enriched_cv=enriched,
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

# Maximum number of files processed per sync call.
# Keep low enough that the total runtime stays well under Render's 25-minute
# background-worker limit (≈ 1-2 min/CV × batch_size).
_DEFAULT_BATCH_SIZE = 20
# Seconds to wait between files to avoid AI provider rate limiting.
_INTER_FILE_DELAY = 1.5


def sync_drive_folder(job_id: str | None = None, batch_size: int = _DEFAULT_BATCH_SIZE) -> dict:
    settings = get_settings()
    drive_folder_id = _resolve_drive_folder_id(settings)

    supabase = get_supabase_admin()
    files = list_pdf_files(drive_folder_id)
    processed_ids = fetch_all_drive_file_ids(supabase)

    # Files that still need processing
    pending = [f for f in files if f["id"] not in processed_ids]

    logger.info(
        "sync_drive_folder start — folder=%s drive_files=%d already_in_db=%d pending=%d batch_size=%d",
        drive_folder_id,
        len(files),
        len(processed_ids),
        len(pending),
        batch_size,
    )

    # Only process up to `batch_size` files per call so the process isn't killed
    # mid-way by Render's worker timeout. The sync is idempotent: re-running it
    # will continue from where it left off.
    batch = pending[:batch_size]
    remaining_after_batch = len(pending) - len(batch)

    results: list[dict] = []
    for idx, file_data in enumerate(batch):
        file_id = file_data["id"]
        logger.info(
            "Processing file %d/%d: %s",
            idx + 1,
            len(batch),
            file_id,
        )
        result = process_drive_file(file_id, supabase, job_id)
        results.append(result)
        if result.get("status") == "processed":
            processed_ids.add(file_id)
        # Throttle AI API calls to stay within rate limits
        if idx < len(batch) - 1:
            time.sleep(_INTER_FILE_DELAY)

    summary = _summarize_sync_results(results, len(files), remaining=remaining_after_batch)
    logger.info(
        "sync_drive_folder batch complete — total=%d processed=%d failed=%d errors=%d remaining=%d",
        summary["total_files"],
        summary["processed"],
        summary["failed"],
        summary["errors"],
        summary["remaining"],
    )
    return summary


# --------------------------------------------------------------------------- #
# WEBHOOK-BASED INCREMENTAL SYNC
# --------------------------------------------------------------------------- #

def sync_drive_webhook(job_id: str | None = None) -> dict:
    """
    Webhook handler: run a full folder reconcile so files missed by prior
    partial syncs are imported, not only Drive changes since page_token.
    """
    settings = get_settings()
    drive_folder_id = _resolve_drive_folder_id(settings)
    supabase = get_supabase_admin()

    summary = sync_drive_folder(job_id)

    # Advance the changes token so future diagnostics stay aligned with Drive.
    try:
        next_token = get_start_page_token()
        supabase.table("app_config").upsert(
            {"key": "drive_page_token", "value": next_token},
            on_conflict="key",
        ).execute()
    except Exception:
        logger.exception("Failed to refresh drive_page_token after webhook sync")

    logger.info(
        "sync_drive_webhook complete — folder=%s processed=%d",
        drive_folder_id,
        summary.get("processed", 0),
    )
    return {**summary, "mode": "full_reconcile"}


# --------------------------------------------------------------------------- #
# WEBHOOK RENEWAL
# --------------------------------------------------------------------------- #

def renew_drive_webhook() -> dict:
    from app.services.webhook_manager import ensure_webhook_registered
    return ensure_webhook_registered()


# --------------------------------------------------------------------------- #
# CELERY TASK WRAPPERS
# --------------------------------------------------------------------------- #

try:
    from app.core.celery_config import celery_app

    @celery_app.task(name="app.tasks.drive_sync.sync_drive_folder", bind=True)
    def sync_drive_folder_task(self, job_id: str | None = None) -> dict:
        return sync_drive_folder(job_id)

    @celery_app.task(name="app.tasks.drive_sync.sync_drive_webhook", bind=True)
    def sync_drive_webhook_task(self, job_id: str | None = None) -> dict:
        return sync_drive_webhook(job_id)

except Exception:  # Celery optional in local dev / API-only deploys
    sync_drive_folder_task = None
    sync_drive_webhook_task = None
