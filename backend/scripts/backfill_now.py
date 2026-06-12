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
    compute_best_job_match,
)
from app.services.scoring_service import compute_candidate_score, classify_domain

import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def build_cv_info(row: dict) -> dict:
    """Reconstruct a scorer-ready cv_data dict from a DB row."""
    ai_data = row.get("ai_extracted_data") or {}
    return {
        **ai_data,
        "full_name":        row.get("full_name")        or ai_data.get("full_name", ""),
        "raw_text":         row.get("cv_raw_text", ""),
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

            score_result, resolved_job_id = compute_best_job_match(
                supabase, cv_info, jobs,
            )

            if not score_result:
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
                "job_id":            resolved_job_id,
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