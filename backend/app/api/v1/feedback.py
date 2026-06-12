from __future__ import annotations

import time
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from httpx import RemoteProtocolError

from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_admin
from app.services.scoring_service import (
    DEFAULT_WEIGHTS,
    FeedbackRecord,
    update_weights_from_feedback,
)

router = APIRouter(prefix="/feedback", tags=["Feedback"])

_MAX_RETRIES = 3
_RETRY_BASE_WAIT = 0.5


def _retry(fn, *args, **kwargs):
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except RemoteProtocolError as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_BASE_WAIT * (2 ** attempt))
    raise last_exc


def _get_candidate_or_404(candidate_id: str) -> dict:
    def _call():
        resp = (
            get_supabase_admin()
            .table("candidates")
            .select("id, score, ai_extracted_data, dimension_scores")
            .eq("id", candidate_id)
            .single()
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return resp.data
    return _retry(_call)


def _load_current_weights(supabase) -> dict:
    try:
        resp = supabase.table("app_config").select("value").eq("key", "ats_weights").single().execute()
        if resp.data:
            return resp.data["value"]
    except Exception:
        pass
    return dict(DEFAULT_WEIGHTS)


def _save_weights(supabase, weights: dict) -> None:
    supabase.table("app_config").upsert(
        {"key": "ats_weights", "value": weights},
        on_conflict="key",
    ).execute()


def _apply_feedback(candidate_id: str, liked: bool, user_id: str) -> None:
    candidate = _get_candidate_or_404(candidate_id)

    dim_scores = (
        candidate.get("dimension_scores")
        or (candidate.get("ai_extracted_data") or {}).get("dimension_scores")
        or {}
    )
    predicted_score = (candidate.get("score") or 0) / 100.0
    actual_rating = 0.85 if liked else 0.25

    feedback_record = FeedbackRecord(
        candidate_id=candidate_id,
        job_title="",
        predicted_score=predicted_score,
        actual_outcome="liked" if liked else "disliked",
        actual_rating=actual_rating,
    )

    def _call():
        supabase = get_supabase_admin()
        current_weights = _load_current_weights(supabase)
        new_weights = update_weights_from_feedback(
            current_weights=current_weights,
            feedback_records=[feedback_record],
            learning_rate=0.01,
        )
        _save_weights(supabase, new_weights)
        supabase.table("candidate_feedback").upsert(
            {
                "candidate_id": candidate_id,
                "recruiter_id": user_id,
                "feedback": "like" if liked else "dislike",
            },
            on_conflict="candidate_id,recruiter_id",
        ).execute()

    _retry(_call)


@router.post("/{candidate_id}/like", status_code=status.HTTP_200_OK)
async def like_candidate(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    _apply_feedback(str(candidate_id), liked=True, user_id=user["id"])
    return {"status": "liked", "candidate_id": str(candidate_id)}


@router.post("/{candidate_id}/dislike", status_code=status.HTTP_200_OK)
async def dislike_candidate(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    _apply_feedback(str(candidate_id), liked=False, user_id=user["id"])
    return {"status": "disliked", "candidate_id": str(candidate_id)}


@router.get("/weights", status_code=status.HTTP_200_OK)
async def get_current_weights(user: dict = Depends(get_current_user)):
    supabase = get_supabase_admin()
    return {"weights": _load_current_weights(supabase)}


@router.delete("/weights/reset", status_code=status.HTTP_200_OK)
async def reset_weights(user: dict = Depends(get_current_user)):
    supabase = get_supabase_admin()
    supabase.table("app_config").delete().eq("key", "ats_weights").execute()
    return {"status": "reset"}