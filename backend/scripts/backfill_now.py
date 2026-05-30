# backend/scripts/backfill_now.py
# Run with: python -m scripts.backfill_now

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.supabase_client import get_supabase_admin
from app.tasks.cv_processing import (
    compute_best_job_match,
    fetch_active_jobs,
    fetch_job,
    ensure_list,
    update_candidate,
    utc_now,
)
from app.services.scoring_service import compute_candidate_score


def run():
    supabase = get_supabase_admin()

    rows = (
        supabase.table("candidates")
        .select(
            "id, full_name, ai_extracted_data, job_id, cv_file_url, "
            "drive_file_id, cv_raw_text, skills, work_history, education, "
            "projects, certifications, current_position, experience_years"
        )
        .not_.is_("drive_file_id", "null")
        .execute()
    ).data or []

    print(f"Found {len(rows)} Drive candidates to backfill")

    jobs = fetch_active_jobs(supabase)
    updated = 0
    failed = 0

    for row in rows:
        candidate_id = row["id"]
        # full_name lives as a top-level DB column, not inside ai_extracted_data
        full_name = row.get("full_name") or "Sans nom"

        try:
            ai_data = row.get("ai_extracted_data") or {}

            cv_info = {
                **ai_data,
                # Preserve top-level DB columns — these override anything in ai_data
                "full_name":        full_name,
                "cv_raw_text":      row.get("cv_raw_text", ""),
                "work_history":     row.get("work_history")     or ai_data.get("work_history", []),
                "skills":           row.get("skills")           or ai_data.get("skills", []),
                "certifications":   row.get("certifications")   or ai_data.get("certifications", []),
                "education":        row.get("education")        or ai_data.get("education", []),
                "projects":         row.get("projects")         or ai_data.get("projects", []),
                "current_position": row.get("current_position") or ai_data.get("current_position", ""),
                "experience_years": row.get("experience_years") or ai_data.get("experience_years", 0),
            }

            score_result, resolved_job_id = compute_best_job_match(
                supabase=supabase,
                cv_info=cv_info,
                jobs=jobs,
            )

            if not score_result:
                score_result = compute_candidate_score(
                    cv_data=cv_info,
                    job_title=cv_info.get("current_position", "Candidate"),
                    job_requirements=" ".join(ensure_list(cv_info.get("skills"))),
                    supabase=supabase,
                )

            update_candidate(supabase, candidate_id, {
                "full_name":         full_name,  # never overwrite with None
                "score":             score_result.get("score", 0),
                "dimension_scores":  score_result.get("dimension_scores", {}),
                "matched_keywords":  score_result.get("matched_keywords", []),
                "missing_keywords":  score_result.get("missing_keywords", []),
                "score_confidence":  score_result.get("confidence", 0.0),
                "score_reasoning":   score_result.get("reasoning", ""),
                "processing_status": "completed",
                "job_id":            row.get("job_id") or resolved_job_id,
                "updated_at":        utc_now(),
            })

            updated += 1
            print(f"  ✓ {full_name} — score={score_result.get('score', 0):.1f}")

        except Exception as exc:
            failed += 1
            print(f"  ✗ {candidate_id} ({full_name}): {exc}")

    print(f"\nDone: {updated} updated, {failed} failed")


if __name__ == "__main__":
    run()