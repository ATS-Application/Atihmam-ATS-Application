"""
AI Processing Pipeline (Phase 2)
- Fetch candidates with processing_status = 'queued'
- Run AI extraction and scoring (process_cv)
- Update processing_status to 'completed' or 'failed'
"""

import logging
import time
from datetime import datetime, timezone

from app.db.supabase_client import get_supabase_admin
from app.tasks.cv_processing import process_cv

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 10

def _fetch_queued_candidates(supabase, limit: int = _DEFAULT_BATCH_SIZE) -> list[dict]:
    response = (
        supabase.table("candidates")
        .select("id, cv_file_url, job_id")
        .eq("processing_status", "queued")
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return response.data or []

def _get_storage_path(cv_file_url: str) -> str:
    """Extract storage path from full URL or return as is if it's already a path."""
    if not cv_file_url:
        return ""
    if "/public/cvs/" in cv_file_url:
        return cv_file_url.split("/public/cvs/")[-1]
    return cv_file_url

def process_queued_candidates(job_id: str | None = None, batch_size: int = _DEFAULT_BATCH_SIZE) -> dict:
    supabase = get_supabase_admin()
    
    # Init or update status
    sync_status = {
        "status": "processing",
        "started_at": datetime.utcnow().isoformat() + "Z",
        "processed": 0, "failed": 0,
        "message": "Traitement IA en cours."
    }
    
    def save_status(status_dict):
        try:
            supabase.table("app_config").upsert(
                {"key": "ai_processing_status", "value": status_dict}, on_conflict="key"
            ).execute()
        except Exception:
            logger.exception("Failed to save ai processing status")

    save_status(sync_status)
    
    candidates = _fetch_queued_candidates(supabase, limit=batch_size)
    
    if not candidates:
        logger.info("No queued candidates found for AI processing.")
        sync_status["status"] = "completed"
        sync_status["completed_at"] = datetime.utcnow().isoformat() + "Z"
        sync_status["message"] = "Aucun candidat en attente de traitement."
        save_status(sync_status)
        return {"status": "done", "processed": 0, "failed": 0}
        
    logger.info("Starting AI processing for %d queued candidates", len(candidates))
    
    for idx, candidate in enumerate(candidates):
        candidate_id = candidate["id"]
        cv_file_url = candidate.get("cv_file_url", "")
        storage_path = _get_storage_path(cv_file_url)
        cand_job_id = job_id or candidate.get("job_id")
        
        if not storage_path:
            logger.error("No storage path found for candidate %s", candidate_id)
            sync_status["failed"] += 1
            supabase.table("candidates").update({
                "processing_status": "failed",
                "processing_error": "No cv_file_url or storage_path found."
            }).eq("id", candidate_id).execute()
            continue
            
        try:
            # Synchronous processing of each CV
            logger.info("Processing candidate %d/%d: %s", idx + 1, len(candidates), candidate_id)
            result = process_cv(
                candidate_id=candidate_id,
                storage_path=storage_path,
                job_id=cand_job_id
            )
            if result.get("success"):
                sync_status["processed"] += 1
            else:
                sync_status["failed"] += 1
        except Exception as e:
            logger.exception("Error processing candidate %s", candidate_id)
            sync_status["failed"] += 1
            
        # Update progress
        save_status(sync_status)
            
    sync_status["status"] = "completed"
    sync_status["completed_at"] = datetime.utcnow().isoformat() + "Z"
    sync_status["message"] = f"Traitement IA terminé. {sync_status['processed']} réussis, {sync_status['failed']} échoués."
    save_status(sync_status)
    
    return {"status": "done", "processed": sync_status["processed"], "failed": sync_status["failed"]}

# Celery task
try:
    from app.core.celery_config import celery_app

    @celery_app.task(name="app.tasks.ai_processing.process_queued_candidates_task", bind=True)
    def process_queued_candidates_task(self, job_id: str | None = None, batch_size: int = _DEFAULT_BATCH_SIZE) -> dict:
        return process_queued_candidates(job_id=job_id, batch_size=batch_size)
except Exception:
    process_queued_candidates_task = None
