from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID
from app.models.job import JobCreate, JobUpdate, JobResponse
from app.core.security import get_current_user, require_role
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/", response_model=list[JobResponse])
async def list_jobs(user: dict = Depends(get_current_user)):
    supabase = get_supabase_admin()
    response = supabase.table("jobs").select("*").eq("is_active", True).execute()
    return response.data


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: UUID, user: dict = Depends(get_current_user)):
    supabase = get_supabase_admin()
    response = (
        supabase.table("jobs").select("*").eq("id", str(job_id)).single().execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Job not found")
    return response.data


@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    user: dict = Depends(require_role("admin", "recruiter")),
):
    supabase = get_supabase_admin()
    data = payload.model_dump()
    data["created_by"] = user["id"]
    response = supabase.table("jobs").insert(data).execute()
    return response.data[0]


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: UUID,
    payload: JobUpdate,
    user: dict = Depends(require_role("admin", "recruiter")),
):
    supabase = get_supabase_admin()
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    response = supabase.table("jobs").update(data).eq("id", str(job_id)).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Job not found")
    return response.data[0]


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: UUID,
    user: dict = Depends(require_role("admin")),
):
    supabase = get_supabase_admin()
    supabase.table("jobs").update({"is_active": False}).eq("id", str(job_id)).execute()