# ============================================================================
# backend/app/api/v1/candidates.py
# ============================================================================
# Smart ATS Candidate API
#
# Features:
# - CRUD operations for candidates
# - Candidate status workflow transitions
# - Safe data sanitization
# - CV depth analysis
# - Supabase integration
# - Clean architecture
# ============================================================================

from __future__ import annotations

from uuid import UUID
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)

from app.services.scoring_service import compute_candidate_score
from app.tasks.cv_processing import fetch_job

from app.core.security import get_current_user
from app.core.state_machine import validate_transition

from app.db.supabase_client import (
    get_supabase,
)

from app.models.candidate import (
    CandidateCreate,
    CandidateResponse,
    CandidateStatusTransition,
    CandidateUpdate,
)

from app.services.ai_service import (
    analyze_cv_depth,
)

router = APIRouter(
    prefix="/candidates",
    tags=["Candidates"],
)

# ============================================================================
# HELPERS
# ============================================================================


def ensure_list(value: Any) -> list:
    """
    Ensure database fields are always returned as lists.
    Prevents null/string related crashes.
    """

    return value if isinstance(value, list) else []


def sanitize_candidate(candidate: dict) -> dict:
    """
    Normalize and sanitize candidate payloads coming from Supabase.
    """

    candidate["skills"] = ensure_list(
        candidate.get("skills")
    )

    candidate["certifications"] = ensure_list(
        candidate.get("certifications")
    )

    candidate["extracted_skills"] = ensure_list(
        candidate.get("extracted_skills")
    )

    if candidate.get("job_id"):
        candidate["job_id"] = str(
            candidate["job_id"]
        )

    return candidate


def get_candidate_or_404(
    supabase,
    candidate_id: UUID,
):
    """
    Fetch a candidate or raise 404.
    """

    response = (
        supabase
        .table("candidates")
        .select("*")
        .eq("id", str(candidate_id))
        .single()
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    return response.data


# ============================================================================
# LIST CANDIDATES
# ============================================================================


@router.get(
    "/",
    response_model=list[CandidateResponse],
)
async def list_candidates(
    job_id: UUID | None = Query(None),
    status_filter: str | None = Query(
        default=None,
        alias="status",
    ),
    user: dict = Depends(get_current_user),
):
    """
    Retrieve all candidates with optional filtering.
    """

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

    return [
        sanitize_candidate(candidate)
        for candidate in candidates
    ]


# ============================================================================
# GET SINGLE CANDIDATE
# ============================================================================


@router.get(
    "/{candidate_id}",
    response_model=CandidateResponse,
)
async def get_candidate(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    """
    Retrieve a single candidate by ID.
    """

    supabase = get_supabase()

    candidate = get_candidate_or_404(
        supabase,
        candidate_id,
    )

    return sanitize_candidate(candidate)


# ============================================================================
# CREATE CANDIDATE
# ============================================================================


@router.post(
    "/",
    response_model=CandidateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_candidate(
    payload: CandidateCreate,
    user: dict = Depends(get_current_user),
):
    """
    Create a new candidate.
    """

    supabase = get_supabase()

    data = payload.model_dump(
        exclude_none=True
    )

    # Normalize array fields
    data["skills"] = ensure_list(
        data.get("skills")
    )

    data["certifications"] = ensure_list(
        data.get("certifications")
    )

    data["extracted_skills"] = ensure_list(
        data.get("extracted_skills")
    )

    # UUID serialization
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


# ============================================================================
# UPDATE CANDIDATE
# ============================================================================


@router.patch(
    "/{candidate_id}",
    response_model=CandidateResponse,
)
async def update_candidate(
    candidate_id: UUID,
    payload: CandidateUpdate,
    user: dict = Depends(get_current_user),
):
    """
    Update an existing candidate.
    """

    supabase = get_supabase()

    data = payload.model_dump(
        exclude_none=True
    )

    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
        )

    # Normalize array fields
    list_fields = [
        "skills",
        "certifications",
        "extracted_skills",
    ]

    for field in list_fields:
        if field in data:
            data[field] = ensure_list(
                data.get(field)
            )

    # UUID serialization
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


# ============================================================================
# TRANSITION CANDIDATE STATUS
# ============================================================================


@router.post(
    "/{candidate_id}/transition",
    response_model=CandidateResponse,
)
async def transition_candidate_status(
    candidate_id: UUID,
    payload: CandidateStatusTransition,
    user: dict = Depends(get_current_user),
):
    """
    Transition candidate status using workflow validation.
    """

    supabase = get_supabase()

    candidate = (
        supabase
        .table("candidates")
        .select("id, status")
        .eq("id", str(candidate_id))
        .single()
        .execute()
    )

    if not candidate.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    current_status = candidate.data["status"]
    new_status = payload.new_status.value

    # Validate workflow transition
    validate_transition(
        current_status,
        new_status,
    )

    updated = (
        supabase
        .table("candidates")
        .update({
            "status": new_status,
        })
        .eq("id", str(candidate_id))
        .execute()
    )

    # Save transition history
    (
        supabase
        .table("candidate_status_history")
        .insert({
            "candidate_id": str(candidate_id),
            "from_status": current_status,
            "to_status": new_status,
            "changed_by": user["id"],
            "note": payload.note,
        })
        .execute()
    )

    if not updated.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update candidate status",
        )

    return sanitize_candidate(
        updated.data[0]
    )


# ============================================================================
# DELETE CANDIDATE
# ============================================================================


@router.delete(
    "/{candidate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_candidate(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    """
    Delete a candidate permanently.
    """

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
    
# ============================================================================
# DELETE ALL CANDIDATES
# ============================================================================

@router.delete(
    "/",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_all_candidates(
    user: dict = Depends(get_current_user),
):
    """
    Delete all candidates permanently.
    """

    supabase = get_supabase()

    response = (
        supabase
        .table("candidates")
        .delete()
        .neq("id", "00000000-0000-0000-0000-000000000000")
        .execute()
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )


# ============================================================================
# CV DEPTH ANALYSIS
# ============================================================================


@router.get("/{candidate_id}/depth")
async def get_candidate_cv_depth(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    """
    Analyze CV depth using AI scoring intelligence.
    """

    supabase = get_supabase()

    candidate = get_candidate_or_404(
        supabase,
        candidate_id,
    )

    report = analyze_cv_depth(
        candidate
    )

    return {
        "candidate_id": str(candidate_id),
        "analysis": report,
    }

# ============================================================================
# ON-DEMAND DOMAIN SCORE AGAINST A JOB
# ============================================================================

@router.post(
    "/{candidate_id}/score",
    summary="Score a candidate against a specific job offer",
)
async def score_candidate_against_job(
    candidate_id: UUID,
    job_id: UUID,
    user: dict = Depends(get_current_user),
):
    """
    Run the full domain-aware scoring pipeline for a candidate
    against a specific job offer and persist the result.

    Use this after upload when you want to (re)score against a chosen job,
    or when the candidate was uploaded without an active job available.
    """
    supabase = get_supabase()

    candidate = get_candidate_or_404(supabase, candidate_id)

    job_resp = (
        supabase.table("jobs")
        .select("id, title, requirements, required_experience")
        .eq("id", str(job_id))
        .single()
        .execute()
    )
    if not job_resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    job = job_resp.data

    # Build cv_data from the stored candidate row.
    # ai_extracted_data is the richest source; fall back to top-level fields.
    ai_data = candidate.get("ai_extracted_data") or {}
    if isinstance(ai_data, str):
        try:
            import json as _json
            ai_data = _json.loads(ai_data)
        except Exception:
            ai_data = {}

    cv_data = {
        **ai_data,
        # Top-level columns always win over ai_extracted_data
        "cv_raw_text":      candidate.get("cv_raw_text", ""),
        "skills":           candidate.get("skills") or ai_data.get("skills", []),
        "work_history":     candidate.get("work_history") or ai_data.get("work_history", []),
        "education":        candidate.get("education") or ai_data.get("education", []),
        "experience_years": candidate.get("experience_years") or ai_data.get("experience_years"),
        "certifications":   candidate.get("certifications") or ai_data.get("certifications", []),
        "projects":         candidate.get("projects") or ai_data.get("projects", []),
        "summary":          candidate.get("summary") or ai_data.get("summary", ""),
        "current_position": candidate.get("current_position") or ai_data.get("current_position", ""),
    }

    score_result = compute_candidate_score(
        cv_data=cv_data,
        job_title=job.get("title", ""),
        job_requirements=job.get("requirements", ""),
        required_experience=job.get("required_experience", 5),
        supabase=supabase,
    )

    # Persist the new score and associate with the job
    supabase.table("candidates").update({
        "score":            score_result["score"],
        "dimension_scores": score_result["dimension_scores"],
        "score_confidence": score_result["confidence"],
        "job_id":           str(job_id),
    }).eq("id", str(candidate_id)).execute()

    return {
        "candidate_id": str(candidate_id),
        "job_id":       str(job_id),
        **score_result,
    }
