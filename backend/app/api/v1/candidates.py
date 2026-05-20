from fastapi import APIRouter, Depends, HTTPException, status, Query
from uuid import UUID
from app.models.candidate import (
    CandidateCreate, CandidateUpdate, CandidateResponse, CandidateStatusTransition
)
from app.core.security import get_current_user
from app.core.state_machine import validate_transition
from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/candidates", tags=["Candidates"])


@router.get("/", response_model=list[CandidateResponse])
async def list_candidates(
    job_id: UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    query = supabase.table("candidates").select("*")

    if job_id:
        query = query.eq("job_id", str(job_id))
    if status_filter:
        query = query.eq("status", status_filter)

    response = query.order("created_at", desc=True).execute()
    return response.data


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    response = (
        supabase.table("candidates")
        .select("*")
        .eq("id", str(candidate_id))
        .single()
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return response.data


@router.post("/", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
async def create_candidate(
    payload: CandidateCreate,
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    data = payload.model_dump(exclude_none=True)
    if "job_id" in data:
        data["job_id"] = str(data["job_id"])
    response = supabase.table("candidates").insert(data).execute()
    return response.data[0]


@router.patch("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate(
    candidate_id: UUID,
    payload: CandidateUpdate,
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "job_id" in data:
        data["job_id"] = str(data["job_id"])

    response = (
        supabase.table("candidates")
        .update(data)
        .eq("id", str(candidate_id))
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return response.data[0]


@router.post("/{candidate_id}/transition", response_model=CandidateResponse)
async def transition_status(
    candidate_id: UUID,
    payload: CandidateStatusTransition,
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase()

    current = (
        supabase.table("candidates")
        .select("id, status")
        .eq("id", str(candidate_id))
        .single()
        .execute()
    )
    if not current.data:
        raise HTTPException(status_code=404, detail="Candidate not found")

    validate_transition(current.data["status"], payload.new_status.value)

    updated = (
        supabase.table("candidates")
        .update({"status": payload.new_status.value})
        .eq("id", str(candidate_id))
        .execute()
    )

    supabase.table("candidate_status_history").insert({
        "candidate_id": str(candidate_id),
        "from_status": current.data["status"],
        "to_status": payload.new_status.value,
        "changed_by": user["id"],
        "note": payload.note,
    }).execute()

    return updated.data[0]


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    supabase.table("candidates").delete().eq("id", str(candidate_id)).execute()