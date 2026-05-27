# backend/app/tasks/candidate_task.py
from app.services.cv_parser import (
    extract_text_from_bytes,
)

from app.services.ai_service import (
    extract_cv_info,
)

from app.services.scoring_service import (
    score_candidate,
)

from app.db.supabase import supabase


def process_candidate(
    candidate_id: str,
    pdf_bytes: bytes,
    job,
):
    try:
        # -----------------------------------------
        # EXTRACT RAW TEXT
        # -----------------------------------------
        raw_text = extract_text_from_bytes(
            pdf_bytes
        )

        # -----------------------------------------
        # EXTRACT CV DATA
        # -----------------------------------------
        cv_data = extract_cv_info(
            raw_text
        )

        # -----------------------------------------
        # SCORE
        # -----------------------------------------
        score_result = score_candidate(
            cv_data=cv_data,
            job_title=job["title"],
            job_requirements=job[
                "requirements"
            ]
            or "",
        )

        # -----------------------------------------
        # UPDATE DATABASE
        # -----------------------------------------
        supabase.table(
            "candidates"
        ).update(
            {
                "full_name": cv_data.get(
                    "full_name"
                ),
                "email": cv_data.get(
                    "email"
                ),
                "phone": cv_data.get(
                    "phone"
                ),
                "current_position": cv_data.get(
                    "current_position"
                ),
                "skills": cv_data.get(
                    "skills",
                    [],
                ),
                "experience_years": cv_data.get(
                    "experience_years"
                ),
                "cv_raw_text": raw_text,
                "ai_extracted_data": cv_data,
                "score": score_result[
                    "score"
                ],
                "score_reasoning": score_result[
                    "reasoning"
                ],
                "matched_keywords": score_result[
                    "matched_keywords"
                ],
                "keyword_score": score_result[
                    "keyword_score"
                ],
                "experience_score": score_result[
                    "experience_score"
                ],
                "semantic_score": score_result[
                    "semantic_score"
                ],
                "processing_status": "completed",
            }
        ).eq(
            "id",
            candidate_id,
        ).execute()

        print(
            "[SUCCESS] Candidate processed:",
            candidate_id,
        )

    except Exception as e:
        print(
            "[PROCESS ERROR]",
            e,
        )

        supabase.table(
            "candidates"
        ).update(
            {
                "processing_status": "failed",
                "processing_error": str(e),
            }
        ).eq(
            "id",
            candidate_id,
        ).execute()