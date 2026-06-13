# backend/app/api/v1/feedback.py
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
            # Also fetch job_id so we can resolve job_title for context-aware learning
            .select("id, score, ai_extracted_data, dimension_scores, job_id")
            .eq("id", candidate_id)
            .single()
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return resp.data

    return _retry(_call)


def _get_job_title(supabase, job_id: str | None) -> str:
    """Resolve a job title from job_id. Returns '' if unavailable."""
    if not job_id:
        return ""
    try:
        resp = (
            supabase.table("jobs")
            .select("title")
            .eq("id", job_id)
            .single()
            .execute()
        )
        return (resp.data or {}).get("title", "") if resp.data else ""
    except Exception:
        return ""


def load_weights(supabase) -> dict:
    """
    Load recruiter-trained weights from app_config.
    Single DB call — callers must not call this twice for the same request.
    Falls back to DEFAULT_WEIGHTS if nothing has been saved yet.
    """
    try:
        resp = (
            supabase.table("app_config")
            .select("value")
            .eq("key", "ats_weights")
            .single()
            .execute()
        )
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
    """
    Core feedback logic shared by the /feedback router and the /analytics proxy.

    Fixes vs. previous version
    ─────────────────────────
    1. job_title is resolved from the candidate's job_id so weight updates are
       context-aware (finance likes don't drift tech weights).
    2. update_weights_from_feedback now receives the candidate's actual
       dimension_scores so the gradient is computed against real per-dimension
       contributions rather than the weight values themselves.
    3. load_weights is called exactly once per _apply_feedback invocation
       (single DB round-trip).

    dimension_scores resolution order
    ──────────────────────────────────
    1. Top-level ``dimension_scores`` column  (written by analytics rescore)
    2. ``ai_extracted_data.dimension_scores`` (legacy location)
    3. Empty dict — weight update still runs but with zero per-dimension signal
    """
    candidate = _get_candidate_or_404(candidate_id)

    dim_scores: dict = candidate.get("dimension_scores") or {}
    if not dim_scores:
        dim_scores = (candidate.get("ai_extracted_data") or {}).get(
            "dimension_scores", {}
        )

    predicted_score = (candidate.get("score") or 0) / 100.0
    actual_rating   = 0.85 if liked else 0.25

    def _call():
        supabase      = get_supabase_admin()
        job_title     = _get_job_title(supabase, candidate.get("job_id"))
        current_weights = load_weights(supabase)   # single call

        feedback_record = FeedbackRecord(
            candidate_id    = candidate_id,
            job_title       = job_title,            # now context-aware
            predicted_score = predicted_score,
            actual_outcome  = "liked" if liked else "disliked",
            actual_rating   = actual_rating,
        )

        new_weights = update_weights_from_feedback(
            current_weights   = current_weights,
            feedback_records  = [feedback_record],
            learning_rate     = 0.01,
            dimension_scores  = dim_scores,         # pass real scores for correct gradient
        )
        _save_weights(supabase, new_weights)

        supabase.table("candidate_feedback").upsert(
            {
                "candidate_id": candidate_id,
                "recruiter_id": user_id,
                "feedback":     "like" if liked else "dislike",
            },
            on_conflict="candidate_id,recruiter_id",
        ).execute()

    _retry(_call)


# ============================================================
# ROUTES
# ============================================================


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
    weights  = load_weights(supabase)          # single call
    return {
        "weights":       weights,
        "defaults":      DEFAULT_WEIGHTS,
        "is_customized": weights != DEFAULT_WEIGHTS,
    }


@router.delete("/weights/reset", status_code=status.HTTP_200_OK)
async def reset_weights(user: dict = Depends(get_current_user)):
    supabase = get_supabase_admin()
    supabase.table("app_config").delete().eq("key", "ats_weights").execute()
    return {"status": "reset"}