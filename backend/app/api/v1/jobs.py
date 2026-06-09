# backend/app/api/v1/jobs.py

from __future__ import annotations

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)

from app.core.security import (
    get_current_user,
    require_role,
)
from app.db.supabase_client import get_supabase_admin
from app.models.job import (
    JobCreate,
    JobResponse,
    JobUpdate,
)
from app.utils.sanitize import safe_screening_questions

router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
    redirect_slashes=False
)


# =========================================================
# LIST JOBS
# =========================================================

@router.get(
    "/",
    response_model=list[JobResponse],
)
async def list_jobs(
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase_admin()

    response = (
        supabase
        .table("jobs")
        .select("*")
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
    )

    jobs = response.data or []

    # Ensure safe screening_questions structure
    for job in jobs:
        job["screening_questions"] = safe_screening_questions(
            job.get("screening_questions")
        )

    return jobs


# =========================================================
# GET SINGLE JOB
# =========================================================

@router.get(
    "/{job_id}",
    response_model=JobResponse,
)
async def get_job(
    job_id: UUID,
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase_admin()

    response = (
        supabase
        .table("jobs")
        .select("*")
        .eq("id", str(job_id))
        .single()
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    job = response.data

    job["screening_questions"] = safe_screening_questions(
        job.get("screening_questions")
    )

    return job


# =========================================================
# CREATE JOB
# =========================================================

@router.post(
    "/",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    payload: JobCreate,
    user: dict = Depends(
        require_role("admin", "recruiter")
    ),
):
    supabase = get_supabase_admin()

    data = payload.model_dump()

    # Ensure safe structure before insert
    data["screening_questions"] = safe_screening_questions(
        data.get("screening_questions")
    )

    data["created_by"] = user["id"]

    response = (
        supabase
        .table("jobs")
        .insert(data)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create job",
        )

    job = response.data[0]

    job["screening_questions"] = safe_screening_questions(
        job.get("screening_questions")
    )

    return job


# =========================================================
# UPDATE JOB
# =========================================================

@router.patch(
    "/{job_id}",
    response_model=JobResponse,
)
async def update_job(
    job_id: UUID,
    payload: JobUpdate,
    user: dict = Depends(
        require_role("admin", "recruiter")
    ),
):
    supabase = get_supabase_admin()

    data = payload.model_dump(
        exclude_none=True
    )

    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    # Sanitize screening questions if present
    if "screening_questions" in data:
        data["screening_questions"] = safe_screening_questions(
            data.get("screening_questions")
        )

    response = (
        supabase
        .table("jobs")
        .update(data)
        .eq("id", str(job_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    job = response.data[0]

    job["screening_questions"] = safe_screening_questions(
        job.get("screening_questions")
    )

    return job


# =========================================================
# DELETE JOB (SOFT DELETE)
# =========================================================

@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_job(
    job_id: UUID,
    user: dict = Depends(
        require_role("admin")
    ),
):
    supabase = get_supabase_admin()

    response = (
        supabase
        .table("jobs")
        .update({"is_active": False})
        .eq("id", str(job_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )