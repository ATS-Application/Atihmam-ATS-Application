# backend/app/api/v1/feedback.py
"""
Recruiter Feedback API
======================
POST /api/v1/feedback/{candidate_id}/like   → liked=True
POST /api/v1/feedback/{candidate_id}/dislike → liked=False

Adjusts adaptive weights so the scoring engine learns from recruiter choices.
Also stores feedback history for analytics.
"""
from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_admin
from app.services.scoring_service import update_weights_from_feedback

router = APIRouter(prefix="/feedback", tags=["Feedback"], redirect_slashes=False)


def _get_candidate_or_404(candidate_id: str, supabase):
    resp = (
        supabase.table("candidates")
        .select("id, score, ai_extracted_data, dimension_scores")
        .eq("id", candidate_id)
        .single()
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return resp.data


@router.post("/{candidate_id}/like", status_code=status.HTTP_200_OK)
async def like_candidate(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    """Mark candidate as a good match → reinforce current weight distribution."""
    supabase = get_supabase_admin()
    candidate = _get_candidate_or_404(str(candidate_id), supabase)

    dim_scores = (candidate.get("dimension_scores") or
                  (candidate.get("ai_extracted_data") or {}).get("dimension_scores") or {})

    update_weights_from_feedback(
        supabase=supabase,
        candidate_id=str(candidate_id),
        liked=True,
        dimension_scores=dim_scores,
    )

    # Store feedback record
    supabase.table("candidate_feedback").upsert(
        {
            "candidate_id": str(candidate_id),
            "recruiter_id": user["id"],
            "feedback": "like",
        },
        on_conflict="candidate_id,recruiter_id",
    ).execute()

    return {"status": "liked", "candidate_id": str(candidate_id)}


@router.post("/{candidate_id}/dislike", status_code=status.HTTP_200_OK)
async def dislike_candidate(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    """Mark candidate as a poor match → down-weight contributing dimensions."""
    supabase = get_supabase_admin()
    candidate = _get_candidate_or_404(str(candidate_id), supabase)

    dim_scores = (candidate.get("dimension_scores") or
                  (candidate.get("ai_extracted_data") or {}).get("dimension_scores") or {})

    update_weights_from_feedback(
        supabase=supabase,
        candidate_id=str(candidate_id),
        liked=False,
        dimension_scores=dim_scores,
    )

    supabase.table("candidate_feedback").upsert(
        {
            "candidate_id": str(candidate_id),
            "recruiter_id": user["id"],
            "feedback": "dislike",
        },
        on_conflict="candidate_id,recruiter_id",
    ).execute()

    return {"status": "disliked", "candidate_id": str(candidate_id)}


@router.get("/weights", status_code=status.HTTP_200_OK)
async def get_current_weights(
    user: dict = Depends(get_current_user),
):
    """Return the current adaptive scoring weights."""
    from app.services.scoring_service import _load_adaptive_weights
    supabase = get_supabase_admin()
    weights = _load_adaptive_weights(supabase)
    return {"weights": weights}


@router.delete("/weights/reset", status_code=status.HTTP_200_OK)
async def reset_weights(
    user: dict = Depends(get_current_user),
):
    """Reset adaptive weights to defaults."""
    supabase = get_supabase_admin()
    supabase.table("app_config").delete().eq("key", "ats_weights").execute()
    return {"status": "reset"}