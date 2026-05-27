# backend/app/api/v1/ingestion.py
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

from datetime import datetime
import hashlib
import re
import unicodedata
import uuid

from app.core.security import (
    get_current_user,
    require_role,
)

from app.db.supabase_client import (
    get_supabase,
    get_supabase_admin,
)

from app.services.webhook_manager import (
    ensure_webhook_registered,
)

from app.tasks.cv_processing import (
    process_cv,
)

from app.tasks.drive_sync import (
    sync_drive_folder,
)

router = APIRouter(
    prefix="/ingestion",
    tags=["CV Ingestion"],
)

ALLOWED_CONTENT_TYPES = {
    "application/pdf"
}

MAX_FILE_SIZE_MB = 10


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def sanitize_filename(filename: str) -> str:
    filename = (
        unicodedata.normalize(
            "NFKD",
            filename,
        )
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


def create_file_hash(
    content: bytes,
) -> str:
    return hashlib.sha256(
        content
    ).hexdigest()


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
    ).insert({
        "candidate_id": candidate_id,
        "from_status": from_status,
        "to_status": to_status,
        "changed_by": changed_by,
        "note": note,
        "created_at": datetime.utcnow().isoformat(),
    }).execute()


# ─────────────────────────────────────────────
# MANUAL CV UPLOAD
# ─────────────────────────────────────────────

@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_cv(
    file: UploadFile = File(...),
    job_id: str | None = Form(None),
    user: dict = Depends(
        get_current_user
    ),
):
    """
    Upload CV manually and trigger
    asynchronous AI processing.
    """

    # ─────────────────────────────────────────
    # VALIDATE CONTENT TYPE
    # ─────────────────────────────────────────

    if (
        file.content_type
        not in ALLOWED_CONTENT_TYPES
    ):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted.",
        )

    # ─────────────────────────────────────────
    # READ FILE
    # ─────────────────────────────────────────

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty.",
        )

    size_mb = len(content) / (
        1024 * 1024
    )

    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File exceeds "
                f"{MAX_FILE_SIZE_MB} MB limit."
            ),
        )

    # ─────────────────────────────────────────
    # CREATE HASH
    # ─────────────────────────────────────────

    file_hash = create_file_hash(
        content
    )

    supabase = get_supabase_admin()

    # ─────────────────────────────────────────
    # OPTIONAL DUPLICATE CHECK
    # ─────────────────────────────────────────

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
            detail=(
                "This CV was already uploaded."
            ),
        )

    # ─────────────────────────────────────────
    # CREATE CANDIDATE
    # ─────────────────────────────────────────

    candidate_insert = {
        "job_id": job_id,
        "status": "applied",
        "processing_status": "queued",
        "cv_file_hash": file_hash,
        "created_at": datetime.utcnow().isoformat(),
    }

    candidate_response = (
        supabase.table("candidates")
        .insert(candidate_insert)
        .execute()
    )

    if not candidate_response.data:
        raise HTTPException(
            status_code=500,
            detail=(
                "Could not create candidate."
            ),
        )

    candidate = (
        candidate_response.data[0]
    )

    candidate_id = candidate["id"]

    # ─────────────────────────────────────────
    # LOG INITIAL STATUS
    # ─────────────────────────────────────────

    log_candidate_status(
        candidate_id=candidate_id,
        from_status=None,
        to_status="applied",
        changed_by=user["id"],
        note="CV uploaded manually.",
    )

    # ─────────────────────────────────────────
    # CREATE SAFE FILE NAME
    # ─────────────────────────────────────────

    safe_filename = sanitize_filename(
        file.filename
    )

    unique_filename = (
        f"{uuid.uuid4()}_{safe_filename}"
    )

    storage_path = (
        f"manual/{candidate_id}/"
        f"{unique_filename}"
    )

    # ─────────────────────────────────────────
    # UPLOAD TO STORAGE
    # ─────────────────────────────────────────

    try:
        (
            supabase.storage
            .from_("cvs")
            .upload(
                storage_path,
                content,
                file_options={
                    "content-type":
                    "application/pdf",
                    "upsert": "false",
                },
            )
        )

    except Exception as e:
        # rollback candidate
        (
            supabase.table("candidates")
            .delete()
            .eq("id", candidate_id)
            .execute()
        )

        raise HTTPException(
            status_code=500,
            detail=(
                f"Storage upload failed: "
                f"{str(e)}"
            ),
        )

    # ─────────────────────────────────────────
    # SAVE STORAGE PATH
    # ─────────────────────────────────────────

    (
        supabase.table("candidates")
        .update({
            "cv_file_url": storage_path,
            "updated_at": datetime.utcnow().isoformat(),
        })
        .eq("id", candidate_id)
        .execute()
    )

    # ─────────────────────────────────────────
    # QUEUE BACKGROUND TASK
    # ─────────────────────────────────────────

    process_cv.delay(
        candidate_id=candidate_id,
        storage_path=storage_path,
        job_id=job_id,
    )

    return {
        "success": True,
        "message": (
            "CV uploaded successfully."
        ),
        "candidate_id": candidate_id,
        "processing_status": "queued",
    }


# ─────────────────────────────────────────────
# GOOGLE DRIVE WEBHOOK
# ─────────────────────────────────────────────

@router.post(
    "/drive/webhook",
    status_code=status.HTTP_200_OK,
)
async def drive_webhook(
    request: Request,
):
    headers = request.headers

    resource_state = headers.get(
        "x-goog-resource-state",
        "",
    )

    resource_id = headers.get(
        "x-goog-resource-id"
    )

    # Google handshake
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
            "reason": "missing resource_id",
        }

    # Queue async sync
    sync_drive_folder.delay()

    return {
        "status": "queued"
    }


# ─────────────────────────────────────────────
# REGISTER WEBHOOK
# ─────────────────────────────────────────────

@router.post(
    "/drive/register-webhook"
)
async def register_drive_webhook(
    user: dict = Depends(
        require_role("admin")
    ),
):
    return ensure_webhook_registered()


# ─────────────────────────────────────────────
# MANUAL DRIVE SYNC
# ─────────────────────────────────────────────

@router.post(
    "/drive/sync",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_drive_sync(
    job_id: str | None = None,
    user: dict = Depends(
        require_role(
            "admin",
            "recruiter",
        )
    ),
):
    sync_drive_folder.delay(
        job_id=job_id
    )

    return {
        "success": True,
        "message": "Drive sync queued.",
    }