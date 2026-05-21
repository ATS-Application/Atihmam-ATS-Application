from celery import shared_task
from app.services.cv_parser import extract_text_from_bytes
from app.services.ai_service import extract_cv_info, score_candidate
from app.db.supabase_client import get_supabase_admin


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_cv(
    self,
    candidate_id: str,
    storage_path: str,
    job_id: str | None = None,
):
    """
    Pipeline for manually uploaded CVs:
    download from Supabase Storage → extract text → AI parse → score → update candidate row.
    """

    supabase = get_supabase_admin()

    try:
        # ─────────────────────────────────────────────
        # Download file from Supabase Storage
        # ─────────────────────────────────────────────

        pdf_bytes = supabase.storage.from_("cvs").download(storage_path)

        if not pdf_bytes:
            raise ValueError("Could not download CV from storage.")

        # ─────────────────────────────────────────────
        # Extract raw text
        # ─────────────────────────────────────────────

        raw_text = extract_text_from_bytes(pdf_bytes)

        if not raw_text.strip():
            raise ValueError(
                "PDF produced empty text — may be image-based (OCR needed)"
            )

        # ─────────────────────────────────────────────
        # AI extraction
        # ─────────────────────────────────────────────

        extracted = extract_cv_info(raw_text)

        # ─────────────────────────────────────────────
        # Candidate scoring
        # ─────────────────────────────────────────────

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

        # ─────────────────────────────────────────────
        # Update candidate
        # ─────────────────────────────────────────────

        update_payload = {
            "cv_raw_text": raw_text[:50000],
            "ai_extracted_data": extracted,
            "full_name": extracted.get("full_name"),
            "email": extracted.get("email"),
            "phone": extracted.get("phone"),
            "current_position": extracted.get("current_position"),
            "skills": extracted.get("skills", []),
            "experience_years": extracted.get("experience_years"),
            "updated_at": "now()",
        }

        if score is not None:
            update_payload["score"] = score

        supabase.table("candidates").update(update_payload).eq(
            "id",
            candidate_id,
        ).execute()

    except Exception as exc:
        raise self.retry(
            exc=exc,
            countdown=30 * (2 ** self.request.retries),
        )