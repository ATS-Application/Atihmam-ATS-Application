# backend/scripts/backfill_now.py
# Run with: python -m scripts.backfill_now

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.supabase_client import get_supabase_admin
from app.tasks.cv_processing import (
    fetch_active_jobs,
    ensure_list,
    update_candidate,
    utc_now,
    _quality_fallback,
    _build_score_payload,
)
from app.services.scoring_service import compute_candidate_score, classify_domain

import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# ── Tunable constants ────────────────────────────────────────────────────────
DOMAIN_MISMATCH_PENALTY = 0.70   # multiplier applied when candidate ≠ job domain
MIN_SCORE_TO_ASSIGN_JOB = 50.0   # below this (after penalty) → quality fallback


def compute_best_job_match_with_domain(
    supabase, cv_data: dict, jobs: list
) -> tuple[dict | None, str | None]:
    """
    Same as cv_processing.compute_best_job_match but with domain-penalty logic
    so cross-domain mismatches (e.g. IT Buyer → HR job) are deprioritized.
    Returns (score_result, job_id) or (None, None) if no good match found.
    """
    candidate_position = cv_data.get("current_position", "")
    candidate_domain   = classify_domain(candidate_position)
    logger.info("  Candidate domain : %s (%s)", candidate_domain, candidate_position)

    best_score  = -1
    best_result = None
    best_job_id = None
    best_domain = None

    for job in jobs:
        try:
            result = compute_candidate_score(
                cv_data=cv_data,
                job_title=job.get("title", ""),
                job_requirements=job.get("requirements", ""),
            )
            raw_score  = result.get("score", 0)
            job_domain = classify_domain(job.get("title", ""))

            if job_domain != candidate_domain:
                penalized = raw_score * DOMAIN_MISMATCH_PENALTY
                logger.info(
                    "    %-40s [%s] raw=%.1f → penalized=%.1f (domain mismatch)",
                    job.get("title"), job_domain, raw_score, penalized
                )
                effective_score = penalized
            else:
                logger.info(
                    "    %-40s [%s] score=%.1f ✓",
                    job.get("title"), job_domain, raw_score
                )
                effective_score = raw_score

            if effective_score > best_score:
                best_score  = effective_score
                best_result = result
                best_job_id = job.get("id")
                best_domain = job_domain

        except Exception as exc:
            logger.error("    Scoring error for job %s: %s", job.get("id"), exc)

    # If even the best match is cross-domain and weak → don't assign
    if best_job_id and best_domain != candidate_domain and best_score < MIN_SCORE_TO_ASSIGN_JOB:
        logger.info(
            "  Best match is cross-domain + low score (%.1f) → quality fallback",
            best_score
        )
        return None, None

    return best_result, best_job_id


def build_cv_info(row: dict) -> dict:
    """Reconstruct a scorer-ready cv_data dict from a DB row."""
    ai_data = row.get("ai_extracted_data") or {}
    return {
        **ai_data,
        # Top-level DB columns override ai_extracted_data
        "full_name":        row.get("full_name")        or ai_data.get("full_name", ""),
        "raw_text":         row.get("cv_raw_text", ""), # scorers expect raw_text
        "work_history":     row.get("work_history")     or ai_data.get("work_history", []),
        "skills":           row.get("skills")           or ai_data.get("skills", []),
        "certifications":   row.get("certifications")   or ai_data.get("certifications", []),
        "education":        row.get("education")        or ai_data.get("education", []),
        "projects":         row.get("projects")         or ai_data.get("projects", []),
        "current_position": row.get("current_position") or ai_data.get("current_position", ""),
        "experience_years": row.get("experience_years") or ai_data.get("experience_years", 0),
    }


def run():
    supabase = get_supabase_admin()

    # Fetch all Drive-synced candidates
    rows = (
        supabase.table("candidates")
        .select(
            "id, full_name, ai_extracted_data, job_id, "
            "cv_raw_text, skills, work_history, education, "
            "projects, certifications, current_position, experience_years"
        )
        .not_.is_("drive_file_id", "null")
        .execute()
    ).data or []

    jobs = fetch_active_jobs(supabase)

    print(f"\n{'='*60}")
    print(f"  Backfill — {len(rows)} Drive candidates / {len(jobs)} active jobs")
    print(f"  Jobs: {[j.get('title') for j in jobs]}")
    print(f"{'='*60}\n")

    updated  = 0
    fallback = 0
    failed   = 0

    for row in rows:
        candidate_id = row["id"]
        full_name    = row.get("full_name") or "Sans nom"
        print(f"→ {full_name}")

        try:
            cv_info = build_cv_info(row)

            score_result, resolved_job_id = compute_best_job_match_with_domain(
                supabase=supabase,
                cv_data=cv_info,
                jobs=jobs,
            )

            if not score_result:
                # No good domain match → autonomous quality score, no job assigned
                score_result    = _quality_fallback(cv_info)
                resolved_job_id = None
                fallback        += 1
                print(f"  ⚠  No domain match → quality fallback  score={score_result.get('score', 0):.1f}")
            else:
                matched_title = next(
                    (j.get("title") for j in jobs if j.get("id") == resolved_job_id), "?"
                )
                print(f"  ✓  Matched → '{matched_title}'  score={score_result.get('score', 0):.1f}")

            update_candidate(supabase, candidate_id, {
                "full_name":         full_name,
                "job_id":            resolved_job_id,   # None clears wrong assignments
                "processing_status": "completed",
                "updated_at":        utc_now(),
                **_build_score_payload(score_result),
            })
            updated += 1

        except Exception as exc:
            failed += 1
            print(f"  ✗  FAILED: {exc}")

    print(f"\n{'='*60}")
    print(f"  Done — {updated} updated ({fallback} quality fallback), {failed} failed")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run()