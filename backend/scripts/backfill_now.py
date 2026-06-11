# backend/scripts/backfill_now.py
# Run with: python -m scripts.backfill_now

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.supabase_client import get_supabase_admin
from app.tasks.cv_processing import (
    compute_best_job_match,
    fetch_active_jobs,
    ensure_list,
    update_candidate,
    utc_now,
    _quality_fallback,
    _build_score_payload,
)


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
    print(f"Active jobs: {[j.get('title') for j in jobs]}")

    updated = 0
    failed  = 0

    for row in rows:
        candidate_id = row["id"]
        full_name    = row.get("full_name") or "Sans nom"

        try:
            ai_data = row.get("ai_extracted_data") or {}

            cv_info = {
                **ai_data,
                "full_name":        full_name,
                "raw_text":         row.get("cv_raw_text", ""),   # scorers expect raw_text
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
                cv_data=cv_info,
                jobs=jobs,
            )

            if not score_result:
                print(f"  ⚠ No job match for {full_name}, using quality fallback")
                score_result   = _quality_fallback(cv_info)
                resolved_job_id = None

            update_candidate(supabase, candidate_id, {
                "full_name":         full_name,
                "job_id":            resolved_job_id or row.get("job_id"),
                "processing_status": "completed",
                "updated_at":        utc_now(),
                **_build_score_payload(score_result),
            })

            updated += 1
            print(f"  ✓ {full_name} — score={score_result.get('score', 0):.1f}  job={resolved_job_id}")

        except Exception as exc:
            failed += 1
            print(f"  ✗ {candidate_id} ({full_name}): {exc}")

    print(f"\nDone: {updated} updated, {failed} failed")


if __name__ == "__main__":
    run()