"""
AI Processing Pipeline (Phase 2)
- Fetch candidates with processing_status = 'queued'
- Run AI extraction and scoring (process_cv)
- Update processing_status to 'completed' or 'failed'
"""

import logging
import time
from datetime import datetime, timezone, timedelta

from app.db.supabase_client import get_supabase_admin
from app.tasks.cv_processing import process_cv

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 10

def unlock_stuck_candidates(supabase, timeout_minutes: int = 10):
    """Resets candidates stuck in 'processing' status back to 'queued'."""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
    threshold_iso = threshold.isoformat()
    
    try:
        resp = (
            supabase.table("candidates")
            .select("id, locked_at")
            .eq("processing_status", "processing")
            .lt("locked_at", threshold_iso)
            .execute()
        )
        stuck_candidates = resp.data or []
        if stuck_candidates:
            logger.info("Found %d candidates stuck in processing, unlocking them...", len(stuck_candidates))
            stuck_ids = [c["id"] for c in stuck_candidates]
            
            for i in range(0, len(stuck_ids), 50):
                batch = stuck_ids[i:i+50]
                supabase.table("candidates").update({
                    "processing_status": "queued",
                    "locked_at": None,
                    "processing_error": "Processing timed out (stuck in processing)."
                }).in_("id", batch).execute()
            logger.info("Successfully unlocked %d stuck candidates.", len(stuck_ids))
    except Exception as e:
        logger.error("Error unlocking stuck candidates: %s", e)

def schedule_quota_retries(supabase, cooldown_minutes: int = 5):
    """Transitions candidates in 'failed_quota' to 'retry_scheduled' after cooldown."""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
    threshold_iso = threshold.isoformat()
    
    try:
        resp = (
            supabase.table("candidates")
            .select("id, updated_at")
            .eq("processing_status", "failed_quota")
            .lt("updated_at", threshold_iso)
            .execute()
        )
        quota_candidates = resp.data or []
        if quota_candidates:
            logger.info("Found %d candidates in failed_quota ready for retry scheduling...", len(quota_candidates))
            candidate_ids = [c["id"] for c in quota_candidates]
            
            for i in range(0, len(candidate_ids), 50):
                batch = candidate_ids[i:i+50]
                supabase.table("candidates").update({
                    "processing_status": "retry_scheduled",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }).in_("id", batch).execute()
            logger.info("Scheduled %d candidates for retry.", len(candidate_ids))
    except Exception as e:
        logger.error("Error scheduling quota retries: %s", e)

def _fetch_queued_candidates(supabase, limit: int = _DEFAULT_BATCH_SIZE) -> list[dict]:
    response = (
        supabase.table("candidates")
        .select("id, cv_file_url, job_id, extracted, ai_extracted_data, processing_status")
        .in_("processing_status", ["queued", "pending", "retry_scheduled"])
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
    
    # Auto-recovery: unlock stuck candidates and schedule quota retries
    unlock_stuck_candidates(supabase)
    schedule_quota_retries(supabase)
    
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
        already_extracted = bool(candidate.get("extracted", False))
        
        if not storage_path:
            logger.error("No storage path found for candidate %s", candidate_id)
            sync_status["failed"] += 1
            supabase.table("candidates").update({
                "processing_status": "failed",
                "processing_error": "No cv_file_url or storage_path found."
            }).eq("id", candidate_id).execute()
            continue
            
        try:
            logger.info(
                "Processing candidate %d/%d: %s (extracted=%s)",
                idx + 1, len(candidates), candidate_id, already_extracted
            )
            result = process_cv(
                candidate_id=candidate_id,
                storage_path=storage_path,
                job_id=cand_job_id,
                skip_extraction=already_extracted,
                cached_cv_info=candidate.get("ai_extracted_data") if already_extracted else None,
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
