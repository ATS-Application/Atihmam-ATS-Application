from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request, status
from app.core.security import get_current_user, require_role
from app.db.supabase_client import get_supabase
from app.tasks.cv_processing import process_cv
from app.tasks.drive_sync import process_drive_file, sync_drive_folder
from app.services.webhook_manager import ensure_webhook_registered

router = APIRouter(prefix="/ingestion", tags=["CV Ingestion"])

ALLOWED_CONTENT_TYPES = {"application/pdf"}
MAX_FILE_SIZE_MB = 10


# ─── Manual upload ────────────────────────────────────────────────────────────

@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_cv(
    file: UploadFile = File(...),
    job_id: str | None = Form(None),
    user: dict = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Only PDF files are accepted. Got: {file.content_type}",
        )

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size_mb:.1f} MB). Max: {MAX_FILE_SIZE_MB} MB",
        )

    supabase = get_supabase()
    storage_path = f"cvs/manual/{file.filename}"
    supabase.storage.from_("cvs").upload(
        storage_path,
        content,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )
    cv_url = supabase.storage.from_("cvs").get_public_url(storage_path)

    candidate_data: dict = {"cv_file_url": cv_url, "status": "applied"}
    if job_id:
        candidate_data["job_id"] = job_id

    response = supabase.table("candidates").insert(candidate_data).execute()
    candidate_id = response.data[0]["id"]

    process_cv.delay(candidate_id=candidate_id, cv_url=cv_url, job_id=job_id)

    return {"message": "CV uploaded. Processing in background.", "candidate_id": candidate_id}


# ─── Google Drive webhook ─────────────────────────────────────────────────────

@router.post("/drive/webhook", status_code=status.HTTP_200_OK)
async def drive_webhook(request: Request):
    """Receives Drive push notifications (metadata in headers, no body).
    Must return 200 fast — Drive retries on non-2xx.
    """
    headers = request.headers
    resource_state = headers.get("x-goog-resource-state", "")
    resource_id = headers.get("x-goog-resource-id")

    if resource_state == "sync":
        return {"status": "acknowledged"}

    if resource_state not in {"add", "update", "untrash"}:
        return {"status": "ignored", "state": resource_state}

    if not resource_id:
        return {"status": "ignored", "reason": "no resource_id"}

    sync_drive_folder.delay()
    return {"status": "queued"}


@router.post("/drive/register-webhook", status_code=status.HTTP_200_OK)
async def register_drive_webhook(
    user: dict = Depends(require_role("admin")),
):
    result = ensure_webhook_registered()
    return result


@router.post("/drive/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_drive_sync(
    job_id: str | None = None,
    user: dict = Depends(require_role("admin", "recruiter")),
):
    sync_drive_folder.delay(job_id=job_id)
    return {"message": "Drive sync queued."}