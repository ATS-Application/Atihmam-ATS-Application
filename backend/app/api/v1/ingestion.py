# backend/app/api/v1/ingestion.py

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)

from app.config import get_settings
from app.core.security import (
    get_current_user,
    require_role,
)

from app.db.drive_channels import get_active_channel
from app.db.supabase_client import (
    get_supabase_admin,
)

from app.services.webhook_manager import (
    ensure_webhook_registered,
)

from app.tasks.cv_processing import process_cv
from app.tasks.drive_sync import sync_drive_folder, sync_drive_webhook

router = APIRouter(
    prefix="/ingestion",
    tags=["CV Ingestion"],
    redirect_slashes=False,
)

# =========================================================
# CONFIG
# =========================================================

# Autorise désormais les formats PDF, Word et Images (OCR)
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/msword",  # .doc
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp"
}

MAX_FILE_SIZE_MB = 10

# =========================================================
# HELPERS
# =========================================================


def sanitize_filename(filename: str) -> str:
    filename = (
        unicodedata.normalize("NFKD", filename)
        .encode("ascii", "ignore")
        .decode("ascii")
    )

    filename = re.sub(
        r"[^a-zA-Z0-9._-]",
        "_",
        filename,
    )

    filename = re.sub(
        r"_+",
        "_",
        filename,
    )

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

    supabase.table(
        "candidate_status_history"
    ).insert(
        {
            "candidate_id": candidate_id,
            "from_status": from_status,
            "to_status": to_status,
            "changed_by": changed_by,
            "note": note,
            "created_at": datetime.utcnow().isoformat(),
        }
    ).execute()


# =========================================================
# TASK DISPATCHER
# =========================================================

def queue_cv_processing(
    background_tasks: BackgroundTasks,
    candidate_id: str,
    storage_path: str,
    job_id: str | None,
):
    """
    Try Celery first.
    Fallback to FastAPI BackgroundTasks.
    """

    try:
        process_cv.delay(
            candidate_id=candidate_id,
            storage_path=storage_path,
            job_id=job_id,
        )

        return "celery"

    except Exception:
        background_tasks.add_task(
            process_cv,
            candidate_id=candidate_id,
            storage_path=storage_path,
            job_id=job_id,
        )

        return "background"


def queue_drive_sync(
    background_tasks: BackgroundTasks,
    job_id: str | None = None,
    incremental: bool = False,
):
    """
    Try Celery first.
    Fallback to FastAPI BackgroundTasks.
    """

    sync_func = sync_drive_webhook if incremental else sync_drive_folder

    try:
        sync_func.delay(
            job_id=job_id,
        )

        return "celery"

    except Exception:
        background_tasks.add_task(
            sync_func,
            job_id=job_id,
        )

        return "background"


def verify_drive_webhook(headers) -> bool:
    settings = get_settings()

    expected_token = settings.drive_webhook_token
    if expected_token and headers.get("x-goog-channel-token") != expected_token:
        return False

    if not settings.drive_folder_id:
        return False

    active_channel = get_active_channel(settings.drive_folder_id)
    if not active_channel:
        return False

    return (
        headers.get("x-goog-channel-id") == active_channel.get("channel_id")
        and headers.get("x-goog-resource-id") == active_channel.get("resource_id")
    )


# =========================================================
# MANUAL CV UPLOAD
# =========================================================

@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_cv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    job_id: str | None = Form(None),
    user: dict = Depends(get_current_user),
):
    """
    Upload a CV and queue asynchronous processing.
    Supports Celery and FastAPI BackgroundTasks.
    Supports PDF, Word, and Image (OCR) files.
    """

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Seuls les formats PDF, Word (.docx, .doc) et Images (.png, .jpeg, .jpg, .webp) sont autorisés.",
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty.",
        )

    size_mb = len(content) / (1024 * 1024)

    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {MAX_FILE_SIZE_MB} MB limit.",
        )

    file_hash = create_file_hash(content)

    supabase = get_supabase_admin()

    existing = (
        supabase.table("candidates")
        .select("id")
        .eq("cv_file_hash", file_hash)
        .limit(1)
        .execute()
    )

    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="This CV has already been uploaded.",
        )

    candidate = (
        supabase.table("candidates")
        .insert(
            {
                "job_id": job_id,
                "status": "applied",
                "processing_status": "queued",
                "cv_file_hash": file_hash,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        .execute()
    )

    if not candidate.data:
        raise HTTPException(
            status_code=500,
            detail="Failed to create candidate.",
        )

    candidate_id = candidate.data[0]["id"]

    log_candidate_status(
        candidate_id=candidate_id,
        from_status=None,
        to_status="applied",
        changed_by=user["id"],
        note="CV uploaded manually.",
    )

    # Détermine l'extension appropriée selon le content-type si le nom de fichier est manquant
    default_ext = "pdf"
    if file.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        default_ext = "docx"
    elif file.content_type == "application/msword":
        default_ext = "doc"
    elif "image/" in (file.content_type or ""):
        default_ext = (file.content_type or "").split("/")[-1]
        if default_ext == "jpeg":
            default_ext = "jpg"

    safe_filename = sanitize_filename(
        file.filename or f"cv.{default_ext}"
    )

    unique_filename = (
        f"{uuid.uuid4()}_{safe_filename}"
    )

    storage_path = (
        f"manual/{candidate_id}/{unique_filename}"
    )

    try:
        # Upload vers Supabase avec le type MIME dynamique du fichier d'origine
        (
            supabase.storage
            .from_("cvs")
            .upload(
                storage_path,
                content,
                file_options={
                    "content-type": file.content_type,
                    "upsert": "false",
                },
            )
        )

    except Exception as exc:
        (
            supabase.table("candidates")
            .delete()
            .eq("id", candidate_id)
            .execute()
        )

        raise HTTPException(
            status_code=500,
            detail=f"Storage upload failed: {exc}",
        )

    (
        supabase.table("candidates")
        .update(
            {
                "cv_file_url": storage_path,
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
        .eq("id", candidate_id)
        .execute()
    )

    worker = queue_cv_processing(
        background_tasks=background_tasks,
        candidate_id=candidate_id,
        storage_path=storage_path,
        job_id=job_id,
    )

    return {
        "success": True,
        "candidate_id": candidate_id,
        "processing_status": "queued",
        "worker": worker,
    }


# =========================================================
# GOOGLE DRIVE WEBHOOK
# =========================================================

@router.post(
    "/drive/webhook",
    status_code=status.HTTP_200_OK,
)
async def drive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    headers = request.headers

    if not verify_drive_webhook(headers):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Drive webhook signature.",
        )

    resource_state = headers.get(
        "x-goog-resource-state",
        ""
    )

    resource_id = headers.get(
        "x-goog-resource-id"
    )

    if resource_state == "sync":
        return {
            "status": "acknowledged"
        }

    allowed_states = {
        "add",
        "update",
        "untrash",
    }

    if resource_state not in allowed_states:
        return {
            "status": "ignored",
            "state": resource_state,
        }

    if not resource_id:
        return {
            "status": "ignored",
            "reason": "missing_resource_id",
        }

    worker = queue_drive_sync(
        background_tasks=background_tasks,
        incremental=True,
    )

    return {
        "status": "queued",
        "worker": worker,
    }


# =========================================================
# REGISTER DRIVE WEBHOOK
# =========================================================

@router.post("/drive/register-webhook")
async def register_drive_webhook(
    user: dict = Depends(
        require_role("admin")
    ),
):
    return ensure_webhook_registered()


# =========================================================
# MANUAL DRIVE SYNC
# =========================================================

@router.post(
    "/drive/sync",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_drive_sync(
    background_tasks: BackgroundTasks,
    job_id: str | None = None,
    user: dict = Depends(
        require_role(
            "admin",
            "recruiter",
        )
    ),
):
    worker = queue_drive_sync(
        background_tasks=background_tasks,
        job_id=job_id,
    )

    return {
        "success": True,
        "message": "Drive sync queued.",
        "worker": worker,
    }
