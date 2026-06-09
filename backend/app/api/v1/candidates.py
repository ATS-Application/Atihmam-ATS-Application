# ============================================================================
# backend/app/api/v1/candidates.py
# ============================================================================
# Smart ATS — Candidates API
#
# Changelog v2.1:
# - Removed compute_cv_quality_score import (function deleted from scoring_service)
# - backfill_dimensions now uses _quality_fallback from cv_processing (single source)
# - compute_candidate_score call in score_candidate_against_job: removed
#   required_experience kwarg (not part of the scorer's public interface;
#   scoring_service now absorbs unknown kwargs gracefully via **_ignored_kwargs)
# - build_cv_data injects cv_raw_text as raw_text so scorer has full CV body
# ============================================================================

from __future__ import annotations

import json
import logging
from uuid import UUID
from typing import Any

import time
from collections import defaultdict, deque

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

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
from app.services.scoring_service import compute_candidate_score
from app.tasks.cv_processing import fetch_job, _quality_fallback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/candidates", tags=["Candidates"], redirect_slashes=False)


# ============================================================================
# IN-MEMORY RATE LIMITER  (no Redis required)
# ============================================================================

_rate_limit_buckets: dict[str, deque] = defaultdict(deque)


def check_rate_limit(key: str, max_calls: int = 10, window_seconds: int = 60) -> None:
    """
    Sliding-window rate limiter stored in process memory.
    Raises HTTP 429 when the caller exceeds `max_calls` within `window_seconds`.
    `key` should uniquely identify the caller (e.g. user_id + endpoint).
    """
    now = time.monotonic()
    bucket = _rate_limit_buckets[key]

    while bucket and bucket[0] <= now - window_seconds:
        bucket.popleft()

    if len(bucket) >= max_calls:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: max {max_calls} requests per {window_seconds}s.",
        )
    bucket.append(now)


# ============================================================================
# HELPERS
# ============================================================================

def ensure_list(value: Any) -> list:
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
    for field in ("skills", "certifications", "extracted_skills"):
        candidate[field] = ensure_list(candidate.get(field))
    if candidate.get("job_id"):
        candidate["job_id"] = str(candidate["job_id"])
    return candidate


def get_candidate_or_404(supabase, candidate_id: UUID) -> dict:
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
    Top-level columns take precedence. raw_text is injected from cv_raw_text
    so the scorer always has the full CV body available.
    """
    ai_data = candidate.get("ai_extracted_data") or {}
    if isinstance(ai_data, str):
        try:
            ai_data = json.loads(ai_data)
        except Exception:
            ai_data = {}

    return {
        **ai_data,
        # raw_text is the key the scorer reads first
        "raw_text":         candidate.get("cv_raw_text", ""),
        "cv_raw_text":      candidate.get("cv_raw_text", ""),
        "skills":           candidate.get("skills")           or ai_data.get("skills", []),
        "work_history":     candidate.get("work_history")     or ai_data.get("work_history", []),
        "education":        candidate.get("education")        or ai_data.get("education", []),
        "experience_years": candidate.get("experience_years") or ai_data.get("experience_years"),
        "certifications":   candidate.get("certifications")   or ai_data.get("certifications", []),
        "projects":         candidate.get("projects")         or ai_data.get("projects", []),
        "summary":          candidate.get("summary")          or ai_data.get("summary", ""),
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
async def score_candidate_against_job(
    candidate_id: UUID,
    job_id: UUID,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Run the full domain-aware scoring pipeline for a candidate against a job,
    then persist the result. Rate-limited to 10 requests per minute per user.
    """
    check_rate_limit(key=f"score:{user['id']}", max_calls=10, window_seconds=60)
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
        )

        supabase.table("candidates").update({
            "score":            score_result["score"],
            "dimension_scores": score_result["dimension_scores"],
            "score_confidence": score_result.get("confidence"),
            "score_reasoning":  score_result.get("reasoning"),
            "job_id":           str(job_id),
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
    Candidates linked to a job use compute_candidate_score;
    unlinked candidates (or those whose job was deleted) use _quality_fallback.
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
            cv_data = build_cv_data(c)
            result = None

            if c.get("job_id"):
                job = fetch_job(supabase, c["job_id"])
                if job:
                    result = compute_candidate_score(
                        cv_data=cv_data,
                        job_title=job.get("title", ""),
                        job_requirements=job.get("requirements", ""),
                    )

            if not result:
                # No job, or job was deleted — quality fallback
                result = _quality_fallback(cv_data)

            supabase.table("candidates").update({
                "score":            result.get("score"),
                "dimension_scores": result.get("dimension_scores"),
                "matched_keywords": result.get("matched_keywords", []),
                "missing_keywords": result.get("missing_keywords", []),
                "score_reasoning":  result.get("reasoning"),
            }).eq("id", c["id"]).execute()

            updated += 1
        except Exception as exc:
            logger.error("Backfill failed for candidate %s: %s", c.get("id"), exc)

    return {"updated": updated, "total": len(candidates)}
