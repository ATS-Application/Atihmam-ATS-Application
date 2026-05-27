# backend/app/api/v1/candidates.py

from __future__ import annotations

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)

from app.core.security import get_current_user
from app.core.state_machine import validate_transition
from app.db.supabase_client import get_supabase

from app.models.candidate import (
    CandidateCreate,
    CandidateResponse,
    CandidateStatusTransition,
    CandidateUpdate,
)

router = APIRouter(
    prefix="/candidates",
    tags=["Candidates"],
)


# =========================================================
# HELPERS
# =========================================================

def safe_list(value):
    """
    Ensures value is always a list.
    Prevents crashes when DB returns null/string.
    """
    return value if isinstance(value, list) else []


def sanitize_candidate(candidate: dict) -> dict:
    """
    Sanitizes candidate payload coming from Supabase.
    """

    candidate["skills"] = safe_list(
        candidate.get("skills")
    )

    candidate["certifications"] = safe_list(
        candidate.get("certifications")
    )

    candidate["extracted_skills"] = safe_list(
        candidate.get("extracted_skills")
    )

    if candidate.get("job_id"):
        candidate["job_id"] = str(
            candidate["job_id"]
        )

    return candidate


# =========================================================
# LIST CANDIDATES
# =========================================================

@router.get(
    "/",
    response_model=list[CandidateResponse],
)
async def list_candidates(
    job_id: UUID | None = Query(None),
    status_filter: str | None = Query(
        None,
        alias="status",
    ),
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase()

    query = (
        supabase
        .table("candidates")
        .select("*")
    )

    if job_id:
        query = query.eq(
            "job_id",
            str(job_id),
        )

    if status_filter:
        query = query.eq(
            "status",
            status_filter,
        )

    response = (
        query
        .order("created_at", desc=True)
        .execute()
    )

    candidates = response.data or []

    sanitized = [
        sanitize_candidate(c)
        for c in candidates
    ]

    return sanitized


# =========================================================
# GET SINGLE CANDIDATE
# =========================================================

@router.get(
    "/{candidate_id}",
    response_model=CandidateResponse,
)
async def get_candidate(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase()

    response = (
        supabase
        .table("candidates")
        .select("*")
        .eq("id", str(candidate_id))
        .single()
        .execute()
    )
    
    candidate = response.data or []

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )
        
    candidate["skills"] = candidate.get("skills") or []
    candidate["certifications"] = (
        candidate.get("certifications") or []
    )
    candidate["extracted_skills"] = (
        candidate.get("extracted_skills") or []
    )

    return sanitize_candidate(
        response.data
    )


# =========================================================
# CREATE CANDIDATE
# =========================================================

@router.post(
    "/",
    response_model=CandidateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_candidate(
    payload: CandidateCreate,
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase()

    data = payload.model_dump(
        exclude_none=True
    )

    # Ensure safe arrays
    data["skills"] = safe_list(
        data.get("skills")
    )

    data["certifications"] = safe_list(
        data.get("certifications")
    )

    data["extracted_skills"] = safe_list(
        data.get("extracted_skills")
    )

    if data.get("job_id"):
        data["job_id"] = str(
            data["job_id"]
        )

    response = (
        supabase
        .table("candidates")
        .insert(data)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create candidate",
        )

    return sanitize_candidate(
        response.data[0]
    )


# =========================================================
# UPDATE CANDIDATE
# =========================================================

@router.patch(
    "/{candidate_id}",
    response_model=CandidateResponse,
)
async def update_candidate(
    candidate_id: UUID,
    payload: CandidateUpdate,
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase()

    data = payload.model_dump(
        exclude_none=True
    )

    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    if "skills" in data:
        data["skills"] = safe_list(
            data.get("skills")
        )

    if "certifications" in data:
        data["certifications"] = safe_list(
            data.get("certifications")
        )

    if "extracted_skills" in data:
        data["extracted_skills"] = safe_list(
            data.get("extracted_skills")
        )

    if data.get("job_id"):
        data["job_id"] = str(
            data["job_id"]
        )

    response = (
        supabase
        .table("candidates")
        .update(data)
        .eq("id", str(candidate_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    return sanitize_candidate(
        response.data[0]
    )


# =========================================================
# TRANSITION STATUS
# =========================================================

@router.post(
    "/{candidate_id}/transition",
    response_model=CandidateResponse,
)
async def transition_status(
    candidate_id: UUID,
    payload: CandidateStatusTransition,
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase()

    current = (
        supabase
        .table("candidates")
        .select("id, status")
        .eq("id", str(candidate_id))
        .single()
        .execute()
    )

    if not current.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    validate_transition(
        current.data["status"],
        payload.new_status.value,
    )

    updated = (
        supabase
        .table("candidates")
        .update({
            "status": payload.new_status.value
        })
        .eq("id", str(candidate_id))
        .execute()
    )

    # Save history
    supabase.table(
        "candidate_status_history"
    ).insert({
        "candidate_id": str(candidate_id),
        "from_status": current.data["status"],
        "to_status": payload.new_status.value,
        "changed_by": user["id"],
        "note": payload.note,
    }).execute()

    if not updated.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update candidate status",
        )

    return sanitize_candidate(
        updated.data[0]
    )


# =========================================================
# DELETE CANDIDATE
# =========================================================

@router.delete(
    "/{candidate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_candidate(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase()

    response = (
        supabase
        .table("candidates")
        .delete()
        .eq("id", str(candidate_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )