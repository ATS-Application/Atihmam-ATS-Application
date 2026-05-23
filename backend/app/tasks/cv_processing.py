# app/tasks/cv_processing.py

from celery import shared_task
from datetime import datetime, timezone

from app.services.cv_parser import (
    extract_text_from_bytes,
)

from app.services.ai_service import (
    extract_cv_info,
)

from app.services.scoring_service import (
    compute_candidate_score,
)

from app.db.supabase_client import (
    get_supabase_admin,
)

from app.services.ai_service import extract_cv_info  # Importing AI function
from app.services.scoring_service import compute_candidate_score  # Importing Scoring function
# ...


_PERMANENT_ERRORS = (
    ValueError,
    PermissionError,
)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def process_cv(
    self,
    candidate_id: str,
    storage_path: str,
    job_id: str | None = None,
):
    """
    CV pipeline:
    1. Download CV
    2. Extract PDF text
    3. Extract AI data
    4. Compute ATS score
    5. Save candidate
    """

    supabase = get_supabase_admin()

    try:

        # ====================================
        # DOWNLOAD PDF
        # ====================================
        pdf_bytes = (
            supabase.storage
            .from_("cvs")
            .download(storage_path)
        )

        if not pdf_bytes:
            raise ValueError(
                "Failed to download CV"
            )

        # ====================================
        # EXTRACT TEXT
        # ====================================
        raw_text = extract_text_from_bytes(
            pdf_bytes
        )

        if not raw_text.strip():
            raise ValueError(
                "No readable text in PDF"
            )

        # ====================================
        # AI EXTRACTION
        # ====================================
        cv_info = extract_cv_info(raw_text)

        # ====================================
        # FETCH JOB
        # ====================================
        score_data = None

        if job_id:

            job_response = (
                supabase.table("jobs")
                .select("*")
                .eq("id", job_id)
                .single()
                .execute()
            )

            job = job_response.data

            if job:

                score_data = (
                    compute_candidate_score(
                        cv_data=cv_info,
                        job_title=job["title"],
                        job_requirements=job.get(
                            "requirements",
                            "",
                        ),
                    )
                )

        # ====================================
        # UPDATE PAYLOAD
        # ====================================
        payload = {
            "cv_raw_text": raw_text[:50000],
            "ai_extracted_data": cv_info,
            "full_name": cv_info.get(
                "full_name"
            ),
            "email": cv_info.get(
                "email"
            ),
            "phone": cv_info.get(
                "phone"
            ),
            "current_position": cv_info.get(
                "current_position"
            ),
            "skills": cv_info.get(
                "skills",
                [],
            ),
            "experience_years": cv_info.get(
                "experience_years"
            ),
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        # ====================================
        # SCORE
        # ====================================
        if score_data:
            payload["score"] = score_data[
                "score"
            ]

            payload[
                "score_reasoning"
            ] = score_data[
                "reasoning"
            ]

        # ====================================
        # SAVE
        # ====================================
        (
            supabase.table("candidates")
            .update(payload)
            .eq("id", candidate_id)
            .execute()
        )

        return {
            "success": True,
            "candidate_id": candidate_id,
            "score": payload.get(
                "score"
            ),
        }

    except _PERMANENT_ERRORS:
        raise

    except Exception as exc:

        print(
            "[CV PROCESSING ERROR]",
            exc,
        )

        raise self.retry(
            exc=exc,
            countdown=30
            * (2 ** self.request.retries),
        )