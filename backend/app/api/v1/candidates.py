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

# ============================================================================
# backend/app/api/v1/candidates.py
# ============================================================================
# Smart ATS — Candidates API
# ============================================================================

from __future__ import annotations

import json
import logging
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
from fastapi_limiter.depends import RateLimiter

from app.core.security import get_current_user
from app.core.state_machine import validate_transition
from app.db.supabase_client import get_supabase, get_supabase_admin
from app.models.candidate import (
    CandidateCreate,
    CandidateResponse,
    CandidateStatusTransition,
    CandidateUpdate,
)
from app.services.ai_service import analyze_cv_depth
from app.services.scoring_service import compute_candidate_score, compute_cv_quality_score
from app.tasks.cv_processing import fetch_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/candidates", tags=["Candidates"])


# ============================================================================
# HELPERS
# ============================================================================


def ensure_list(value: Any) -> list:
    """Normalize a field to always be a list."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return [value] if value else []
    if isinstance(value, list):
        return value
    return []


def sanitize_candidate(candidate: dict) -> dict:
    """Normalize candidate fields before returning from the API."""
    for field in ("skills", "certifications", "extracted_skills"):
        candidate[field] = ensure_list(candidate.get(field))
    if candidate.get("job_id"):
        candidate["job_id"] = str(candidate["job_id"])
    return candidate


def get_candidate_or_404(supabase, candidate_id: UUID) -> dict:
    """Fetch a candidate row or raise HTTP 404."""
    resp = (
        supabase.table("candidates")
        .select("*")
        .eq("id", str(candidate_id))
        .single()
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return resp.data


def build_cv_data(candidate: dict) -> dict:
    """
    Merge top-level candidate columns with ai_extracted_data.
    Top-level columns always take precedence.
    """
    ai_data = candidate.get("ai_extracted_data") or {}
    if isinstance(ai_data, str):
        try:
            ai_data = json.loads(ai_data)
        except Exception:
            ai_data = {}

    return {
        **ai_data,
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


# ============================================================================
# LIST & RETRIEVE
# ============================================================================


@router.get("/", response_model=list[CandidateResponse])
async def list_candidates(
    job_id: UUID | None = Query(None),
    status_filter: str | None = Query(default=None, alias="status"),
    user: dict = Depends(get_current_user),
):
    """Return all candidates, optionally filtered by job or status."""
    supabase = get_supabase()
    query = supabase.table("candidates").select("*")
    if job_id:
        query = query.eq("job_id", str(job_id))
    if status_filter:
        query = query.eq("status", status_filter)

    candidates = query.order("created_at", desc=True).execute().data or []
    return [sanitize_candidate(c) for c in candidates]


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    """Retrieve a single candidate by ID."""
    supabase = get_supabase()
    return sanitize_candidate(get_candidate_or_404(supabase, candidate_id))


# ============================================================================
# CREATE & UPDATE
# ============================================================================


@router.post("/", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
async def create_candidate(
    payload: CandidateCreate,
    user: dict = Depends(get_current_user),
):
    """Create a new candidate record."""
    supabase = get_supabase()
    data = payload.model_dump(exclude_none=True)

    for field in ("skills", "certifications", "extracted_skills"):
        data[field] = ensure_list(data.get(field))
    if data.get("job_id"):
        data["job_id"] = str(data["job_id"])

    resp = supabase.table("candidates").insert(data).execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to create candidate")

    return sanitize_candidate(resp.data[0])


@router.patch("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate(
    candidate_id: UUID,
    payload: CandidateUpdate,
    user: dict = Depends(get_current_user),
):
    """Partially update a candidate record."""
    supabase = get_supabase()
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    for field in ("skills", "certifications", "extracted_skills"):
        if field in data:
            data[field] = ensure_list(data[field])
    if data.get("job_id"):
        data["job_id"] = str(data["job_id"])

    resp = (
        supabase.table("candidates")
        .update(data)
        .eq("id", str(candidate_id))
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Candidate not found")

    return sanitize_candidate(resp.data[0])


# ============================================================================
# SCORING
# ============================================================================


@router.post("/{candidate_id}/score", summary="Score a candidate against a job offer")
@RateLimiter(times=10, seconds=60)
async def score_candidate_against_job(
    candidate_id: UUID,
    job_id: UUID,
    user: dict = Depends(get_current_user),
):
    """
    Run the full domain-aware scoring pipeline for a candidate against a job,
    then persist the result.

    Rate-limited to 10 requests per minute per user.
    """
    supabase = get_supabase()

    try:
        candidate = get_candidate_or_404(supabase, candidate_id)

        job_resp = (
            supabase.table("jobs")
            .select("id, title, requirements, required_experience")
            .eq("id", str(job_id))
            .single()
            .execute()
        )
        if not job_resp.data:
            raise HTTPException(status_code=404, detail="Job not found")

        job = job_resp.data
        cv_data = build_cv_data(candidate)

        score_result = compute_candidate_score(
            cv_data=cv_data,
            job_title=job.get("title", ""),
            job_requirements=job.get("requirements", ""),
            required_experience=job.get("required_experience", 5),
            supabase=supabase,
        )

        supabase.table("candidates").update({
            "score":             score_result["score"],
            "dimension_scores":  score_result["dimension_scores"],
            "score_confidence":  score_result.get("confidence"),
            "score_reasoning":   score_result.get("reasoning"),
            "professional_level": score_result.get("professional_level"),
            "warnings":          score_result.get("warnings", []),
            "job_id":            str(job_id),
        }).eq("id", str(candidate_id)).execute()

        logger.info("Score calculated for candidate %s vs job %s", candidate_id, job_id)
        return {"candidate_id": str(candidate_id), "job_id": str(job_id), **score_result}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Scoring failed for candidate %s: %s", candidate_id, exc)
        raise HTTPException(status_code=500, detail=f"Scoring failed: {exc}")


# ============================================================================
# STATUS TRANSITION
# ============================================================================


@router.post("/{candidate_id}/transition", response_model=CandidateResponse)
async def transition_candidate_status(
    candidate_id: UUID,
    payload: CandidateStatusTransition,
    user: dict = Depends(get_current_user),
):
    """Transition a candidate's status through the configured workflow."""
    supabase = get_supabase()

    row = (
        supabase.table("candidates")
        .select("id, status")
        .eq("id", str(candidate_id))
        .single()
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    current_status = row.data["status"]
    new_status = payload.new_status.value
    validate_transition(current_status, new_status)

    updated = (
        supabase.table("candidates")
        .update({"status": new_status})
        .eq("id", str(candidate_id))
        .execute()
    )
    if not updated.data:
        raise HTTPException(status_code=500, detail="Failed to update candidate status")

    supabase.table("candidate_status_history").insert({
        "candidate_id": str(candidate_id),
        "from_status":  current_status,
        "to_status":    new_status,
        "changed_by":   user["id"],
        "note":         payload.note,
    }).execute()

    return sanitize_candidate(updated.data[0])


# ============================================================================
# CV DEPTH ANALYSIS
# ============================================================================


@router.get("/{candidate_id}/depth")
async def get_candidate_cv_depth(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    """Run an AI-powered depth analysis on a candidate's CV."""
    supabase = get_supabase()
    candidate = get_candidate_or_404(supabase, candidate_id)
    report = analyze_cv_depth(candidate)
    return {"candidate_id": str(candidate_id), "analysis": report}


# ============================================================================
# DELETE
# ============================================================================


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    """Permanently delete a single candidate."""
    supabase = get_supabase()
    resp = (
        supabase.table("candidates")
        .delete()
        .eq("id", str(candidate_id))
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_candidates(user: dict = Depends(get_current_user)):
    """Permanently delete every candidate record."""
    supabase = get_supabase()
    supabase.table("candidates").delete().neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================================
# ADMIN — BACKFILL
# ============================================================================


@router.post("/admin/backfill-dimensions")
async def backfill_dimensions(supabase=Depends(get_supabase_admin)):
    """
    Re-score all completed candidates with the latest scoring pipeline.
    Candidates linked to a job use `compute_candidate_score`;
    unlinked candidates fall back to `compute_cv_quality_score`.
    """
    candidates = (
        supabase.table("candidates")
        .select("*")
        .eq("processing_status", "completed")
        .execute()
        .data or []
    )

    updated = 0
    for c in candidates:
        try:
            if c.get("job_id"):
                job = fetch_job(supabase, c["job_id"])
                result = compute_candidate_score(
                    cv_data=build_cv_data(c),
                    job_title=job.get("title", ""),
                    job_requirements=job.get("requirements", ""),
                    supabase=supabase,
                ) if job else compute_cv_quality_score(c, supabase=supabase)
            else:
                result = compute_cv_quality_score(c, supabase=supabase)

            supabase.table("candidates").update({
                "score":             result.get("score"),
                "dimension_scores":  result.get("dimension_scores"),
                "matched_keywords":  result.get("matched_keywords", []),
                "missing_keywords":  result.get("missing_keywords", []),
                "score_reasoning":   result.get("reasoning"),
                "professional_level": result.get("professional_level"),
                "warnings":          result.get("warnings", []),
            }).eq("id", c["id"]).execute()

            updated += 1
        except Exception as exc:
            logger.error("Backfill failed for candidate %s: %s", c.get("id"), exc)

    return {"updated": updated, "total": len(candidates)}
