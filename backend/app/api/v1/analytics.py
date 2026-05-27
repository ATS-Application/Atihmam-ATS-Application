# backend/app/api/v1/analytics.py

"""
Advanced Analytics API for ATS Platform
"""

import time
from collections import Counter
from statistics import mean
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
)
from httpx import RemoteProtocolError
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_admin
from app.services.intelligent_scoring_service import (
    compute_intelligent_score,
    generate_smart_recommendations,
    load_recruiter_preferences,
    normalize_text,
)
from app.services.keyword_matching_service import KeywordMatchingService

router = APIRouter(prefix="/analytics", tags=["Analytics"])

_MAX_RETRIES = 3
_RETRY_BASE_WAIT = 0.5  # seconds; doubles each attempt


# ============================================================
# REQUEST MODELS
# ============================================================


class RescoreAllRequest(BaseModel):
    candidates: list[dict[str, Any]] | None = Field(default=None)
    keywords: list[str] | None = Field(default=None)


# ============================================================
# DATABASE HELPERS
# ============================================================


def _retry_on_disconnect(fn, *args, **kwargs):
    """
    Call fn(*args, **kwargs), recreating the Supabase client and
    retrying up to _MAX_RETRIES times on RemoteProtocolError.

    Returns (result, fresh_client_or_None).
    The caller is responsible for threading a fresh client back if needed.
    """
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except RemoteProtocolError as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BASE_WAIT * (2 ** attempt)
                print(
                    f"[analytics] RemoteProtocolError on attempt {attempt + 1}, "
                    f"retrying in {wait:.1f}s — {exc}"
                )
                time.sleep(wait)
    raise last_exc


class CandidateRepository:
    """
    Thin DB wrapper. Creates a fresh Supabase client per public method call
    to avoid sharing a sync httpx client across threads or after an
    HTTP/2 idle-timeout disconnect.
    """

    # ----------------------------------------------------------
    # Internal: always get a live client
    # ----------------------------------------------------------
    @staticmethod
    def _client():
        return get_supabase_admin()

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------
    def get_candidate(self, candidate_id: UUID) -> dict:
        def _call():
            response = (
                self._client()
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

        return _retry_on_disconnect(_call)

    def get_job(self, job_id: str | None) -> dict | None:
        if not job_id:
            return None

        def _call():
            response = (
                self._client()
                .table("jobs")
                .select("id, title, requirements")
                .eq("id", str(job_id))
                .single()
                .execute()
            )
            return response.data

        return _retry_on_disconnect(_call)

    def get_candidates(
        self,
        statuses: list[str] | None = None,
        job_id: UUID | None = None,
    ) -> list[dict]:
        def _call():
            query = self._client().table("candidates").select("*")
            if statuses:
                query = query.in_("status", statuses)
            if job_id:
                query = query.eq("job_id", str(job_id))
            return query.execute().data or []

        return _retry_on_disconnect(_call)

    def update_candidate_score(self, candidate_id: str, score_data: dict) -> None:
        def _call():
            (
                self._client()
                .table("candidates")
                .update(
                    {
                        "score": score_data["score"],
                        "score_reasoning": score_data["reasoning"],
                        "matched_keywords": score_data["matched_keywords"],
                    }
                )
                .eq("id", candidate_id)
                .execute()
            )

        _retry_on_disconnect(_call)

    def load_preferences(self) -> dict:
        """Thin wrapper so AnalyticsService doesn't hold a raw client reference."""
        return load_recruiter_preferences(self._client())


# ============================================================
# ANALYTICS SERVICE
# ============================================================


class AnalyticsService:
    def __init__(self):
        self.repo = CandidateRepository()
        # Preferences loaded via repo so it uses a fresh client too.
        try:
            self.preferences = self.repo.load_preferences()
        except Exception as exc:
            print(f"[PREFERENCES] Could not load recruiter preferences: {exc}")
            self.preferences = {}

    # --------------------------------------------------------
    # SCORE ENGINE
    # --------------------------------------------------------

    @staticmethod
    def build_cv_payload(candidate: dict) -> dict:
        return {
            "skills": candidate.get("skills", []),
            "experience_years": candidate.get("experience_years"),
            "current_position": candidate.get("current_position"),
        }

    def calculate_score(self, candidate: dict, job: dict | None = None) -> dict:
        return compute_intelligent_score(
            cv_data=self.build_cv_payload(candidate),
            cv_raw_text=candidate.get("cv_raw_text") or "",
            recruiter_preferences=self.preferences,
            job_title=job["title"] if job else "",
            job_requirements=job.get("requirements", "") if job else "",
        )

    # --------------------------------------------------------
    # INSIGHTS
    # --------------------------------------------------------

    def recruiter_insights(self) -> list[str]:
        hired_count = self.preferences.get("hired_count", 0)

        if hired_count == 0:
            return [
                "No hiring history yet. Insights improve after successful hires."
            ]

        insights: list[str] = []
        top_skills = list(self.preferences.get("preferred_skills", {}).keys())[:5]
        domains = self.preferences.get("common_domains", [])
        avg_experience = self.preferences.get("avg_experience")

        if top_skills:
            insights.append(f"Top hired skills: {', '.join(top_skills)}")
        if domains:
            insights.append(f"Most active hiring domains: {', '.join(domains[:3])}")
        if avg_experience:
            insights.append(f"Average hired experience: {avg_experience:.1f} years")
        insights.append(f"Model trained on {hired_count} hires")

        return insights

    # --------------------------------------------------------
    # PIPELINE ANALYTICS
    # --------------------------------------------------------

    @staticmethod
    def score_distribution(scores: list[int | float]) -> dict:
        return {
            "excellent": len([s for s in scores if s >= 80]),
            "good":      len([s for s in scores if 60 <= s < 80]),
            "average":   len([s for s in scores if 40 <= s < 60]),
            "low":       len([s for s in scores if s < 40]),
        }

    @staticmethod
    def top_skills(candidates: list[dict], limit: int = 10) -> list[dict]:
        skills: list[str] = []
        for candidate in candidates:
            skills.extend(candidate.get("skills") or [])
        counter = Counter(normalize_text(skill) for skill in skills)
        return [{"skill": s, "count": c} for s, c in counter.most_common(limit)]


# ============================================================
# ROUTES — unchanged signatures, fixed service construction
# ============================================================


@router.get("/recruiter-profile")
async def recruiter_profile(user: dict = Depends(get_current_user)):
    service = AnalyticsService()
    return {
        "preferred_skills": service.preferences.get("preferred_skills", {}),
        "avg_experience":   service.preferences.get("avg_experience"),
        "common_domains":   service.preferences.get("common_domains", []),
        "hired_count":      service.preferences.get("hired_count", 0),
        "insights":         service.recruiter_insights(),
    }


@router.get("/smart-recommendations")
async def smart_recommendations(
    job_id: UUID | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    service = AnalyticsService()
    candidates = service.repo.get_candidates(statuses=["applied", "screening"], job_id=job_id)
    recommendations = generate_smart_recommendations(candidates, service.preferences)
    return {
        "recommendations": recommendations,
        "based_on_hires":  service.preferences.get("hired_count", 0),
    }


@router.get("/score-breakdown/{candidate_id}")
async def score_breakdown(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    service   = AnalyticsService()
    candidate = service.repo.get_candidate(candidate_id)
    job       = service.repo.get_job(candidate.get("job_id"))
    result    = service.calculate_score(candidate, job)
    return {
        "candidate_id":    str(candidate_id),
        "candidate_name":  candidate.get("full_name"),
        "score":           result["score"],
        "score_breakdown": result["score_breakdown"],
        "matched_keywords": result["matched_keywords"],
        "missing_keywords": result["missing_keywords"],
        "insights":        result["insights"],
        "reasoning":       result["reasoning"],
    }


@router.get("/pipeline-stats")
async def pipeline_stats(user: dict = Depends(get_current_user)):
    service    = AnalyticsService()
    candidates = service.repo.get_candidates()

    if not candidates:
        return {"message": "No candidates found"}

    status_breakdown = Counter(c.get("status", "unknown") for c in candidates)
    scores           = [c["score"] for c in candidates if c.get("score") is not None]
    avg_score        = round(mean(scores), 1) if scores else 0
    hired_count      = status_breakdown.get("hired", 0)
    total            = len(candidates)

    return {
        "total_candidates":   total,
        "average_score":      avg_score,
        "conversion_rate":    round((hired_count / total) * 100, 1) if total else 0,
        "status_breakdown":   dict(status_breakdown),
        "top_skills":         service.top_skills(candidates),
        "score_distribution": service.score_distribution(scores),
    }


@router.get("/recruiter-suggestions")
async def recruiter_suggestions(user: dict = Depends(get_current_user)):
    service    = AnalyticsService()
    candidates = service.repo.get_candidates()

    if not candidates:
        return {"suggestions": ["Add candidates to start receiving AI suggestions."]}

    scores         = [c["score"] for c in candidates if c.get("score") is not None]
    avg_score      = round(mean(scores), 1) if scores else 0
    status_counter = Counter(c.get("status") for c in candidates)
    suggestions: list[str] = []

    if avg_score < 50:
        suggestions.append("Average ATS score is low. Improve sourcing quality or job descriptions.")
    if status_counter.get("screening", 0) > 10:
        suggestions.append("Too many candidates remain in screening stage.")
    if status_counter.get("hired", 0) == 0:
        suggestions.append("No hires detected yet. Prioritize high-score candidates.")

    return {
        "average_score": avg_score,
        "top_skills":    service.top_skills(candidates, limit=5),
        "suggestions":   suggestions,
    }


@router.post("/rescore-candidate/{candidate_id}")
async def rescore_candidate(
    candidate_id: UUID,
    user: dict = Depends(get_current_user),
):
    service   = AnalyticsService()
    candidate = service.repo.get_candidate(candidate_id)
    job       = service.repo.get_job(candidate.get("job_id"))
    result    = service.calculate_score(candidate, job)
    service.repo.update_candidate_score(str(candidate_id), result)
    return {
        "success":         True,
        "candidate_id":    str(candidate_id),
        "new_score":       result["score"],
        "score_breakdown": result["score_breakdown"],
        "insights":        result["insights"],
    }


# ============================================================
# BULK RESCORING
# ============================================================


def run_bulk_rescore(job_id: UUID | None = None) -> dict:
    """
    Runs in a Starlette BackgroundTask (threadpool).

    CRITICAL: AnalyticsService is constructed HERE, inside the thread,
    not in the request handler. This gives the task its own fresh
    Supabase client and avoids sharing a sync httpx connection across threads.
    """
    service = AnalyticsService()  # constructed inside the thread — intentional

    candidates = service.repo.get_candidates(job_id=job_id)
    updated = failed = 0

    for candidate in candidates:
        candidate_id = candidate.get("id")
        try:
            job    = service.repo.get_job(candidate.get("job_id"))
            result = service.calculate_score(candidate, job)
            service.repo.update_candidate_score(candidate_id, result)
            updated += 1
        except Exception as exc:
            print(f"[RESCORE ERROR] {candidate_id} {exc}")
            failed += 1

    return {"updated": updated, "failed": failed, "total": len(candidates)}


@router.post("/rescore-all")
async def rescore_all(
    background_tasks: BackgroundTasks,
    payload: RescoreAllRequest | None = None,
    job_id: UUID | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    background_tasks.add_task(run_bulk_rescore, job_id)

    keyword_results = []
    if payload and payload.candidates and payload.keywords:
        keyword_results = KeywordMatchingService.batch_score_candidates(
            payload.candidates, payload.keywords
        )

    return {
        "success":         True,
        "message":         "Bulk rescoring started",
        "keyword_results": keyword_results,
    }