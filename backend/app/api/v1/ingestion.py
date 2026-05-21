from app.models import user
from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    Form,
    HTTPException,
    Request,
    status,
)

from app.core.security import get_current_user, require_role
from app.db.supabase_client import get_supabase
from app.tasks.cv_processing import process_cv
from app.tasks.drive_sync import sync_drive_folder
from app.services.webhook_manager import ensure_webhook_registered

import hashlib
import uuid
import re
import unicodedata
from datetime import datetime

from app.db.supabase_client import get_supabase, get_supabase_admin

router = APIRouter(prefix="/ingestion", tags=["CV Ingestion"])

ALLOWED_CONTENT_TYPES = {"application/pdf"}
MAX_FILE_SIZE_MB = 10


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def sanitize_filename(filename: str) -> str:
    filename = (
        unicodedata.normalize("NFKD", filename)
        .encode("ascii", "ignore")
        .decode("ascii")
    )

    filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    filename = re.sub(r"_+", "_", filename)

    return filename.lower()


def create_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()



def log_candidate_status(
    candidate_id: str,
    from_status: str | None,
    to_status: str,
    changed_by: str,
    note: str | None = None,
):
    supabase = get_supabase_admin()

    supabase.table("candidate_status_history").insert({
        "candidate_id": candidate_id,
        "from_status": from_status,
        "to_status": to_status,
        "changed_by": changed_by,
        "note": note,
        "created_at": datetime.utcnow().isoformat(),
    }).execute()


# ─────────────────────────────────────────────────────────────
# Manual Upload
# ─────────────────────────────────────────────────────────────

@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_cv(
    file: UploadFile = File(...),
    job_id: str | None = Form(None),
    user: dict = Depends(get_current_user),
):
    # ─── Validate content type ───────────────────────────────

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted.",
        )

    # ─── Read file ───────────────────────────────────────────

    content = await file.read()

    size_mb = len(content) / (1024 * 1024)

    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {MAX_FILE_SIZE_MB} MB limit.",
        )

    # ─── Generate hash for deduplication ─────────────────────

    file_hash = create_file_hash(content)

    supabase = get_supabase()

    # Optional future improvement:
    # store file_hash column in candidates table

    # ─── Create candidate FIRST ──────────────────────────────

    candidate_insert = {
        "job_id": job_id,
        "status": "applied",
        "created_at": datetime.utcnow().isoformat(),
    }

    candidate_response = (
        supabase.table("candidates")
        .insert(candidate_insert)
        .execute()
    )

    candidate = candidate_response.data[0]
    candidate_id = candidate["id"]

    # ─── Log initial status ──────────────────────────────────

    log_candidate_status(
        candidate_id=candidate_id,
        from_status=None,
        to_status="applied",
        changed_by=user["id"],
        note="Candidate uploaded CV manually.",
    )

    # ─── Safe filename generation ────────────────────────────

    safe_filename = sanitize_filename(file.filename)

    unique_filename = f"{uuid.uuid4()}_{safe_filename}"

    storage_path = f"manual/{candidate_id}/{unique_filename}"

    # ─── Upload to Supabase Storage ──────────────────────────

    try:
        supabase.storage.from_("cvs").upload(
            storage_path,
            content,
            file_options={
                "content-type": "application/pdf",
                "upsert": "false",
            },
        )

    except Exception as e:
        # rollback candidate if upload fails

        supabase.table("candidates").delete().eq(
            "id",
            candidate_id
        ).execute()

        raise HTTPException(
            status_code=500,
            detail=f"Storage upload failed: {str(e)}",
        )

    # ─── Store STORAGE PATH (NOT PUBLIC URL) ────────────────

    supabase.table("candidates").update({
        "cv_file_url": storage_path,
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", candidate_id).execute()

    # ─── Queue background processing ─────────────────────────

    process_cv.delay(
        candidate_id=candidate_id,
        storage_path=storage_path,
        job_id=job_id,
    )

    return {
        "message": "CV uploaded successfully. Processing started.",
        "candidate_id": candidate_id,
    }


# ─────────────────────────────────────────────────────────────
# Google Drive Webhook
# ─────────────────────────────────────────────────────────────

@router.post("/drive/webhook", status_code=status.HTTP_200_OK)
async def drive_webhook(request: Request):
    headers = request.headers

    resource_state = headers.get("x-goog-resource-state", "")
    resource_id = headers.get("x-goog-resource-id")

    if resource_state == "sync":
        return {"status": "acknowledged"}

    if resource_state not in {"add", "update", "untrash"}:
        return {
            "status": "ignored",
            "state": resource_state,
        }

    if not resource_id:
        return {
            "status": "ignored",
            "reason": "missing resource_id",
        }

    sync_drive_folder.delay()

    return {"status": "queued"}


# ─────────────────────────────────────────────────────────────
# Register Webhook
# ─────────────────────────────────────────────────────────────

@router.post("/drive/register-webhook")
async def register_drive_webhook(
    user: dict = Depends(require_role("admin")),
):
    return ensure_webhook_registered()


# ─────────────────────────────────────────────────────────────
# Manual Trigger Drive Sync
# ─────────────────────────────────────────────────────────────

@router.post("/drive/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_drive_sync(
    job_id: str | None = None,
    user: dict = Depends(require_role("admin", "recruiter")),
):
    sync_drive_folder.delay(job_id=job_id)

    return {"message": "Drive sync queued."}