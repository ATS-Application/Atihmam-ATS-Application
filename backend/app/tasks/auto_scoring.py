# backend/app/tasks/auto_scoring.py
import logging
from app.db.supabase_client import get_supabase_admin
from app.services.scoring_service import compute_candidate_score
from app.services.screening_engine import DOMAIN_COMPATIBILITY

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# DOMAIN MAPPING
# --------------------------------------------------------------------------- #

def map_db_domain_to_job_category(val: str) -> str:
    """
    Normalize any domain/category string to a common unified key to resolve
    mismatches between frontend values, backend enums, and database entries.
    """
    if not val:
        return ""
    val = val.lower().strip()
    
    synonyms = {
        # Tech
        "tech": "informatique_dev",
        "informatique_dev": "informatique_dev",
        
        # Cyber / Telecom
        "telecom": "reseaux_cyber",
        "reseaux_telecoms_cyber": "reseaux_cyber",
        "reseaux_cyber": "reseaux_cyber",
        
        # Finance
        "finance": "finance_comptabilite",
        "comptabilite_finance": "finance_comptabilite",
        "finance_comptabilite": "finance_comptabilite",
        
        # Logistics
        "logistics": "logistique_transport",
        "transport_logistique": "logistique_transport",
        "logistique_transport": "logistique_transport",
        
        # Purchasing
        "purchasing": "achats_supply_chain",
        "achats_supply_chain": "achats_supply_chain",
        
        # Construction
        "construction": "construction_btp",
        "construction_btp": "construction_btp",
        
        # HR
        "hr": "ressources_humaines",
        "ressources_humaines": "ressources_humaines",
        
        # Marketing
        "marketing": "marketing_communication",
        "marketing_communication": "marketing_communication",
        
        # Sales
        "sales": "commercial_vente",
        "commercial_vente": "commercial_vente",
        
        # Santé
        "sante": "sante_medical",
        "sante_medical": "sante_medical",
        
        # Education
        "education": "education",
        "education_formation": "education",
        
        # Legal
        "legal": "droit_juridique",
        "droit_juridique": "droit_juridique",
        
        # Etudiant
        "etudiant": "etudiant_stage",
        "etudiant_stage": "etudiant_stage",
        "stage_jeune_diplome": "etudiant_stage",
    }
    return synonyms.get(val, val)



def is_candidate_compatible_with_job(candidate_domain: str, job_category: str) -> bool:
    """Return True if the candidate's domain matches or is compatible with the job's category."""
    if not job_category:
        # Job has no category → accept all candidates
        return True
    if not candidate_domain:
        return False

    # Direct raw match (both stored the same way, e.g. "purchasing" == "purchasing")
    if candidate_domain == job_category:
        return True

    # Normalize both sides to the same key space
    cand_norm = map_db_domain_to_job_category(candidate_domain)
    job_norm  = map_db_domain_to_job_category(job_category)

    # Normalised match (e.g. "achats_supply_chain" == "achats_supply_chain")
    if cand_norm == job_norm:
        return True

    # Cross-domain compatibility lookup — try both raw and normalised job key
    allowed_raw  = DOMAIN_COMPATIBILITY.get(job_category, [])
    allowed_norm = DOMAIN_COMPATIBILITY.get(job_norm, [])
    return (
        cand_norm in allowed_raw
        or candidate_domain in allowed_raw
        or cand_norm in allowed_norm
        or candidate_domain in allowed_norm
    )



# --------------------------------------------------------------------------- #
# MAIN TASK
# --------------------------------------------------------------------------- #

def trigger_auto_scoring_for_new_job(job_id: str):
    """
    Background task: when a new job is created, find all candidates
    from compatible domains who are still in early-stage ATS status
    (applied / screening) and score them against the new job.

    Assignment rules
    ----------------
    - Candidate has NO current job             → assign if score >= 30
    - Candidate's current job is INACTIVE      → assign if score >= 30
    - Candidate is in 'applied'/'screening'    → assign if score >= 30
                                                 AND within 15 pts of current best
    - Candidate is in interview/offer/hired    → NEVER touch — they are engaged
    """
    logger.info("Auto-scoring triggered for new job %s", job_id)
    supabase = get_supabase_admin()

    # ── 1. Fetch the new job ────────────────────────────────────────────────
    job_resp = supabase.table("jobs").select("*").eq("id", str(job_id)).execute()
    if not job_resp.data:
        logger.error("Job %s not found — aborting auto-scoring", job_id)
        return

    job = job_resp.data[0]
    job_title       = job.get("title", "")
    job_requirements = job.get("requirements", "") or ""
    job_category    = job.get("category") or ""

    if not job_category:
        from app.services.scoring_service import classify_domain
        job_category = classify_domain(f"{job_title} {job_requirements[:300]}")
        logger.info("Job %s had no category — auto-classified as '%s'", job_id, job_category)

    # ── 2. Active job IDs (to detect inactive assignments) ─────────────────
    active_jobs_resp = supabase.table("jobs").select("id").eq("is_active", True).execute()
    active_job_ids = {j["id"] for j in active_jobs_resp.data or []}

    # ── 3. All candidates whose CV was fully processed ──────────────────────
    candidates_resp = (
        supabase.table("candidates")
        .select("*")
        .eq("processing_status", "completed")
        .execute()
    )
    candidates = candidates_resp.data or []
    logger.info("Evaluating %d completed candidates against job %s", len(candidates), job_id)

    from app.api.v1.candidates import build_cv_data

    matched_count = 0

    for cand in candidates:
        cand_domain = cand.get("domain") or ""

        # ── Domain compatibility check ──────────────────────────────────────
        if not is_candidate_compatible_with_job(cand_domain, job_category):
            continue

        current_job_id = cand.get("job_id")
        ats_status     = cand.get("status", "applied")

        # ── Availability check ──────────────────────────────────────────────
        # Do NOT touch candidates already engaged (interview / offer / hired / rejected)
        ENGAGED_STATUSES = {"interview", "offer", "hired", "rejected"}
        if ats_status in ENGAGED_STATUSES:
            continue

        # Candidate is available if:
        #   - no job assigned, OR
        #   - assigned to an inactive/deleted job, OR
        #   - still in applied / screening
        is_available = (
            not current_job_id
            or current_job_id not in active_job_ids
            or ats_status in {"applied", "screening"}
        )
        if not is_available:
            continue

        # ── Score the candidate against this job ────────────────────────────
        try:
            cv_data = build_cv_data(cand)
            score_result = compute_candidate_score(
                cv_data=cv_data,
                job_title=job_title,
                job_requirements=job_requirements,
            )
            new_score     = float(score_result.get("score", 0))
            current_score = float(cand.get("score") or 0)

            # Candidate must have a minimum qualification score to be matched
            if new_score < 30.0:
                continue

            # ── Store score in job_scores map (enables multi-job matching) ──
            dims = score_result.get("dimension_scores", {})
            
            ai_data = cand.get("ai_extracted_data") or {}
            if isinstance(ai_data, str):
                import json
                try:
                    ai_data = json.loads(ai_data)
                except Exception:
                    ai_data = {}
            
            if "job_scores" not in ai_data:
                ai_data["job_scores"] = {}
                
            ai_data["job_scores"][str(job_id)] = {
                "score": score_result.get("score"),
                "dimension_scores": dims,
                "score_confidence": score_result.get("confidence"),
                "score_reasoning": score_result.get("reasoning"),
                "matched_keywords": score_result.get("matched_keywords", []),
                "missing_keywords": score_result.get("missing_keywords", []),
            }

            from app.tasks.cv_processing import _enrich_ai_data, sanitize_ai_data
            enriched_ai = sanitize_ai_data(_enrich_ai_data(cv_data, score_result))
            
            # Keep all historical job scores
            enriched_ai["job_scores"] = ai_data["job_scores"]
            
            update_payload = {
                "ai_extracted_data": enriched_ai
            }

            # Conditionally set default/home job:
            # - If candidate has no active job assignment, OR
            # - If they match this new job strictly BETTER than their current default
            is_unassigned = not current_job_id or current_job_id not in active_job_ids
            if is_unassigned or new_score > current_score:
                update_payload.update({
                    "job_id":                   job_id,
                    "score":                    score_result.get("score"),
                    "dimension_scores":         dims,
                    "score_confidence":         score_result.get("confidence"),
                    "score_reasoning":          score_result.get("reasoning"),
                    "matched_keywords":         score_result.get("matched_keywords", []),
                    "missing_keywords":         score_result.get("missing_keywords", []),
                    # Flat dimension columns
                    "keyword_score":            dims.get("keyword_score"),
                    "semantic_score":           dims.get("semantic_score"),
                    "experience_score":         dims.get("experience_score"),
                    "project_complexity_score": dims.get("project_complexity_score"),
                    "education_score":          dims.get("education_score"),
                    "certification_score":      dims.get("certification_score"),
                    "leadership_score":         dims.get("leadership_score"),
                    "language_score":           dims.get("language_score"),
                })

            supabase.table("candidates").update(update_payload).eq("id", cand["id"]).execute()

            logger.info(
                "Scored candidate %s for job %s | score %.1f (prev %.1f)",
                cand["id"], job_id, new_score, current_score,
            )
            matched_count += 1

        except Exception as exc:
            logger.error("Failed to auto-score candidate %s: %s", cand.get("id"), exc)

    logger.info(
        "Auto-scoring done for job %s: %d candidate(s) processed.", job_id, matched_count
    )

