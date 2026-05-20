import httpx
from celery import shared_task  # ✨ Replaced local celery_app import to break circular reference
from app.services.cv_parser import extract_text_from_bytes
from app.services.ai_service import extract_cv_info, score_candidate
from app.db.supabase_client import get_supabase_admin
from app.core.celery_config import celery_app


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_cv(self, candidate_id: str, cv_url: str, job_id: str | None = None):
    """Pipeline for manually uploaded CVs:
    download URL → extract text → AI parse → score → update candidate row.
    """
    supabase = get_supabase_admin()
    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(cv_url)
            response.raise_for_status()
            pdf_bytes = response.content

        raw_text = extract_text_from_bytes(pdf_bytes)
        if not raw_text.strip():
            raise ValueError("PDF produced empty text — may be image-based (OCR needed)")

        extracted = extract_cv_info(raw_text)

        score = None
        if job_id:
            job_resp = (
                supabase.table("jobs")
                .select("title, requirements")
                .eq("id", job_id)
                .single()
                .execute()
            )
            if job_resp.data:
                score = score_candidate(
                    cv_data=extracted,
                    job_title=job_resp.data["title"],
                    job_requirements=job_resp.data.get("requirements", ""),
                )

        update_payload = {
            "cv_raw_text": raw_text[:50_000],
            "ai_extracted_data": extracted,
            "full_name": extracted.get("full_name"),
            "email": extracted.get("email"),
            "phone": extracted.get("phone"),
            "current_position": extracted.get("current_position"),
            "skills": extracted.get("skills", []),
            "experience_years": extracted.get("experience_years"),
        }
        if score is not None:
            update_payload["score"] = score

        supabase.table("candidates").update(update_payload).eq("id", candidate_id).execute()

    except Exception as exc:
        # Calculates exponential backoff safely using task metadata
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))