"""
Drive Ingestion Pipeline (Phase 1)
- Scan Google Drive folder
- Detect new PDFs/docs/images
- Download file
- Upload to Supabase storage
- Insert into DB with processing_status = 'queued'
(No AI processing here)
"""

import logging
import time
from datetime import datetime, timezone

from app.config import get_settings
from app.db.supabase_client import get_supabase_admin
from app.services.drive_service import (
    download_file_bytes,
    get_file_metadata,
    list_pdf_files,
)
from app.tasks.drive_sync import (
    _resolve_drive_folder_id,
    candidate_exists,
    sanitize_filename,
    fetch_all_drive_file_ids,
    upload_cv_to_storage,
    insert_candidate,
    record_failed_drive_candidate,
    _summarize_sync_results,
)

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 50
_INTER_FILE_DELAY = 0.5  # Faster because no AI

def process_drive_file_ingest(drive_file_id: str, supabase, job_id: str | None = None) -> dict:
    file_name = None
    try:
        if candidate_exists(supabase, drive_file_id):
            logger.info("Skipping already-processed file: %s", drive_file_id)
            return {"status": "skipped", "drive_file_id": drive_file_id}

        metadata  = get_file_metadata(drive_file_id)
        mime_type = metadata.get("mimeType")
        file_name = sanitize_filename(metadata.get("name", drive_file_id), mime_type)
        file_bytes = download_file_bytes(drive_file_id)

        cv_url = upload_cv_to_storage(
            supabase,
            drive_file_id,
            file_name,
            file_bytes,
            mime_type,
        )

        payload = {
            "status": "applied",
            "processing_status": "queued",
            "full_name": file_name,
            "drive_file_id": drive_file_id,
            "cv_file_url": cv_url,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        insert_result = insert_candidate(supabase, payload, drive_file_id)
        
        if insert_result.get("status") == "skipped":
            return insert_result

        candidate_id = insert_result.get("candidate_id")
        logger.info("Ingested drive file %s as candidate %s (status: queued)", drive_file_id, candidate_id)
        
        return {"status": "processed", "candidate_id": candidate_id}

    except Exception as exc:
        logger.exception("Error ingesting Drive file %s", drive_file_id)
        return record_failed_drive_candidate(
            supabase,
            drive_file_id=drive_file_id,
            file_name=file_name,
            error_message=str(exc),
            job_id=job_id,
        )


def ingest_drive_folder(job_id: str | None = None, batch_size: int = _DEFAULT_BATCH_SIZE) -> dict:
    settings = get_settings()
    drive_folder_id = _resolve_drive_folder_id(settings)
    supabase = get_supabase_admin()
    
    files = list_pdf_files(drive_folder_id)
    processed_ids = fetch_all_drive_file_ids(supabase)

    pending = [f for f in files if f["id"] not in processed_ids]

    logger.info(
        "ingest_drive_folder start — folder=%s drive_files=%d already_in_db=%d pending=%d batch_size=%d",
        drive_folder_id, len(files), len(processed_ids), len(pending), batch_size
    )

    batch = pending[:batch_size]
    remaining_after_batch = len(pending) - len(batch)

    results: list[dict] = []
    for idx, file_data in enumerate(batch):
        file_id = file_data["id"]
        logger.info("Ingesting file %d/%d: %s", idx + 1, len(batch), file_id)
        result = process_drive_file_ingest(file_id, supabase, job_id)
        results.append(result)
        if result.get("status") in ("processed", "failed", "skipped"):
            processed_ids.add(file_id)
        if idx < len(batch) - 1:
            time.sleep(_INTER_FILE_DELAY)

    summary = _summarize_sync_results(results, len(files), remaining=remaining_after_batch)
    logger.info("ingest_drive_folder batch complete — processed=%d failed=%d remaining=%d", 
                summary["processed"], summary["failed"], summary["remaining"])
    return summary


def _run_full_ingest_until_done(job_id: str | None = None) -> None:
    from datetime import datetime
    supabase = get_supabase_admin()

    sync_status = {
        "status": "processing",
        "started_at": datetime.utcnow().isoformat() + "Z",
        "processed": 0, "failed": 0, "skipped": 0, "errors": 0, "remaining": 0, "total_files": 0,
        "message": "L'importation Drive a commencé."
    }

    def save_status(status_dict):
        try:
            supabase.table("app_config").upsert(
                {"key": "drive_ingest_status", "value": status_dict}, on_conflict="key"
            ).execute()
        except Exception:
            logger.exception("Failed to save ingest status")

    save_status(sync_status)

    max_rounds = 50
    round_num = 0
    while round_num < max_rounds:
        round_num += 1
        try:
            summary = ingest_drive_folder(job_id=job_id)
            
            sync_status["processed"] += summary.get("processed", 0)
            sync_status["failed"] += summary.get("failed", 0)
            sync_status["skipped"] += summary.get("skipped", 0)
            sync_status["errors"] += summary.get("errors", 0)
            sync_status["remaining"] = summary.get("remaining", 0)
            sync_status["total_files"] = summary.get("total_files", 0)
            
            if summary.get("status") == "done":
                sync_status["status"] = "completed"
                sync_status["completed_at"] = datetime.utcnow().isoformat() + "Z"
                sync_status["message"] = f"Importation terminée. {sync_status['processed']} importés, {sync_status['skipped']} ignorés."
                save_status(sync_status)
                break
                
            progress = summary.get("processed", 0) + summary.get("failed", 0) + summary.get("skipped", 0)
            if progress == 0 and summary.get("remaining", 0) > 0:
                sync_status["status"] = "stopped"
                sync_status["completed_at"] = datetime.utcnow().isoformat() + "Z"
                sync_status["message"] = "Importation arrêtée (aucune progression)."
                save_status(sync_status)
                break
            else:
                sync_status["message"] = f"Importation en cours... Lot {round_num}. Restants: {sync_status['remaining']}."
                save_status(sync_status)
        except Exception as exc:
            sync_status["status"] = "failed"
            sync_status["completed_at"] = datetime.utcnow().isoformat() + "Z"
            sync_status["message"] = f"Erreur : {str(exc)}"
            save_status(sync_status)
            break

# Celery tasks
try:
    from app.core.celery_config import celery_app

    @celery_app.task(name="app.tasks.drive_ingestion.sync_drive_ingest_folder", bind=True)
    def sync_drive_ingest_folder_task(self, job_id: str | None = None) -> None:
        _run_full_ingest_until_done(job_id)
except Exception:
    sync_drive_ingest_folder_task = None
