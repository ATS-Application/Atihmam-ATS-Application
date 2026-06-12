"""
Pipeline de traitement des CVs (VERSION MVP - SANS CELERY)

Ce fichier est le cœur du traitement des CVs dans l'ATS.
Quand un recruteur uploade un CV, voici ce qui se passe dans l'ordre :

    1. On télécharge le PDF depuis le stockage Supabase
    2. On extrait le texte brut du PDF
    3. L'IA analyse le texte et en extrait les infos structurées
       (nom, email, compétences, expériences, formations...)
    4. On calcule un score de correspondance avec les postes actifs
       → Si aucun poste actif : on score via JD synthétique (qualité CV)
    5. On sauvegarde tout dans la base de données

Changelog v2.2:
- build_candidate_payload: ai_extracted_data now stores enriched_cv (merged
  with dimension_scores, matched_keywords, reasoning, hierarchy_level, domain,
  full_details) instead of bare cv_info — this is what made ScorePanel blank
- _build_score_payload: added missing language_score flat column
- build_candidate_payload signature: added enriched_cv parameter (the cv_info
  dict already containing raw_text); cv_info kept for scalar field extraction
- process_cv: passes enriched_cv to build_candidate_payload

⚠️ Version simplifiée : pas de Celery, pas de Redis.
   Le traitement se fait en tâche de fond via FastAPI BackgroundTasks.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import textwrap
from datetime import datetime, timezone
from typing import Any

from app.db.supabase_client import get_supabase_admin
from app.services.ai_service import extract_cv_info
from app.services.cv_parser import extract_text_from_bytes
from app.services.scoring_service import (
    compute_candidate_score,
    classify_domain,
    Domain,
    enrich_cv_data,
)

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

MAX_TEXT_LENGTH  = 50_000
MAX_AI_DATA_SIZE = 100_000

DOMAIN_MISMATCH_PENALTY = 0.70   # multiplier applied when candidate ≠ job domain
MIN_SCORE_TO_ASSIGN_JOB = 50.0   # below this (after penalty) →

PERMANENT_ERRORS = (
    ValueError,
    PermissionError,
)

REQUIRED_CV_FIELDS = ["skills", "work_history", "education"]

# Quality-fallback dampening (mirrors scoring_service constants)
_KW_DAMPEN  = 0.85
_KW_CAP     = 85.0
_SEM_DAMPEN = 0.80
_SEM_CAP    = 75.0


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def ensure_string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def sanitize_ai_data(data: dict) -> dict:
    try:
        serialized = json.dumps(data)
        if len(serialized) > MAX_AI_DATA_SIZE:
            serialized = serialized[:MAX_AI_DATA_SIZE]
        return json.loads(serialized)
    except Exception:
        return {}


def validate_cv_info(cv_info: dict) -> None:
    if not isinstance(cv_info, dict):
        raise ValueError("L'extraction IA doit retourner un dictionnaire")
    for field_name in REQUIRED_CV_FIELDS:
        if field_name not in cv_info:
            logger.warning("Champ manquant dans les données IA : %s", field_name)


def extract_text_safe(pdf_bytes: bytes, timeout: int = 30) -> str:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(extract_text_from_bytes, pdf_bytes)
        return future.result(timeout=timeout)


# ============================================================================
# FONCTIONS D'ACCÈS À LA BASE DE DONNÉES
# ============================================================================

def update_candidate(supabase, candidate_id: str, data: dict):
    supabase.table("candidates").update(data).eq("id", candidate_id).execute()


def fetch_candidate(supabase, candidate_id: str):
    return (
        supabase.table("candidates")
        .select("*")
        .eq("id", candidate_id)
        .single()
        .execute()
        .data
    )


def fetch_job(supabase, job_id: str):
    return (
        supabase.table("jobs")
        .select("*")
        .eq("id", job_id)
        .single()
        .execute()
        .data
    )


def fetch_active_jobs(supabase):
    return (
        supabase.table("jobs")
        .select("id, title, requirements")
        .eq("is_active", True)
        .execute()
        .data
        or []
    )


# ============================================================================
# HELPERS INTERNES
# ============================================================================

def _enrich_cv_data(cv_info: dict, raw_text: str) -> dict:
    """
    Injects raw_text into cv_data so compute_candidate_score has the full CV
    body for scoring. Without this, keyword/semantic/education/certifications
    scorers receive empty text and return zero.
    """
    
    return enrich_cv_data(cv_info, raw_text)


def _quality_fallback(extracted: dict) -> dict:
    """
    Balanced autonomous scoring when no active job is available.
    Builds a synthetic JD from the CV's own content and scores against it,
    then dampens keyword/semantic scores to avoid unrealistically high values.

    NOTE: this is the single source of truth for quality-fallback scoring.
    drive_sync.py imports and calls this function; do not duplicate it there.
    """
    position = (
        extracted.get("current_position")
        or extracted.get("title")
        or "Professionnel"
    )
    domain_str = classify_domain(position)

    skills       = extracted.get("skills", [])[:25]
    work_history = extracted.get("work_history", [])
    projects     = extracted.get("projects", [])

    exp_titles = [e.get("title", "") for e in work_history if e.get("title")]
    proj_names = [p.get("name",  "") for p in projects     if p.get("name")]

    synthetic_jd = textwrap.dedent(f"""
        Nous recherchons un {position} expérimenté.

        Compétences : {", ".join(skills) if skills else ""}
        Expérience  : {", ".join(exp_titles[:10]) if exp_titles else ""}
        Projets     : {", ".join(proj_names[:5]) if proj_names else ""}
    """).strip()

    cv_data  = dict(extracted)
    raw_text = extracted.get("raw_text") or extracted.get("full_text") or ""
    if raw_text:
        cv_data["raw_text"] = raw_text

    result = compute_candidate_score(
        cv_data=cv_data,
        job_title=position,
        job_requirements=synthetic_jd,
    )

    # Dampen keyword/semantic — copy-on-write, never mutate the returned dict
    original_dims = result.get("dimension_scores", {})
    dampened_dims = {
        **original_dims,
        "keyword_score":  min(original_dims.get("keyword_score",  0) * _KW_DAMPEN,  _KW_CAP),
        "semantic_score": min(original_dims.get("semantic_score", 0) * _SEM_DAMPEN, _SEM_CAP),
    }
    return {
        **result,
        "dimension_scores": dampened_dims,
        "reasoning": f"Score qualité autonome — {domain_str}",
    }


def _build_score_payload(score_result: dict) -> dict:
    """
    Build the DB-safe scoring columns from a score_result dict.
    dimension_scores (jsonb) carries the full breakdown for the frontend.
    Flat alias columns are kept for indexed queries and ScorePanel.jsx source D.
    """
    dims = score_result.get("dimension_scores", {})
    return {
        "score":            score_result.get("score", 0),
        "dimension_scores": dims,
        "score_confidence": score_result.get("confidence", 0),
        "score_reasoning":  score_result.get("reasoning", ""),
        "matched_keywords": score_result.get("matched_keywords", []),
        "missing_keywords": score_result.get("missing_keywords", []),
        # Flat alias columns (ScorePanel source D / indexed ORDER BY)
        "keyword_score":            dims.get("keyword_score"),
        "semantic_score":           dims.get("semantic_score"),
        "experience_score":         dims.get("experience_score"),
        "project_complexity_score": dims.get("project_complexity_score"),
        "education_score":          dims.get("education_score"),
        "certification_score":      dims.get("certification_score"),
        "leadership_score":         dims.get("leadership_score"),
        "language_score":           dims.get("language_score"),   # ← was missing
    }


def _enrich_ai_data(cv_info: dict, score_result: dict) -> dict:
    dims = score_result.get("dimension_scores", {})
    full_details = score_result.get("full_details", {})
    enriched = {
        **cv_info,
        "dimension_scores": dims,
        "matched_keywords": score_result.get("matched_keywords", []),
        "missing_keywords": score_result.get("missing_keywords", []),
        "score_reasoning":  score_result.get("reasoning", ""),
        "hierarchy_level":  score_result.get("hierarchy_level"),
        "domain":           score_result.get("domain"),
        "detected_education": full_details.get("detected_education", "none"),  # ← added
        "full_details":     full_details,
    }
    enriched.pop("raw_text",  None)
    enriched.pop("full_text", None)
    return enriched


# ============================================================================
# PIPELINE PRINCIPAL DE TRAITEMENT
# ============================================================================

def process_cv(candidate_id: str, storage_path: str, job_id: str | None = None):
    supabase = get_supabase_admin()

    try:
        logger.info("Traitement CV : %s", candidate_id)

        candidate = fetch_candidate(supabase, candidate_id)
        if not candidate:
            raise ValueError("Candidat non trouvé")

        update_candidate(supabase, candidate_id, {
            "processing_status": "processing",
            "updated_at": utc_now(),
        })

        # Download + extract text
        pdf_bytes = supabase.storage.from_("cvs").download(storage_path)
        raw_text  = extract_text_safe(pdf_bytes)

        # AI extraction
        cv_info = extract_cv_info(raw_text)

        # Enrich with raw_text so all scorer dimensions have the full CV body
        enriched_cv = enrich_cv_data(cv_info, raw_text)

        # === SCORING ===
        score_result = None

        if job_id:
            job = fetch_job(supabase, job_id)
            if job:
                score_result = compute_candidate_score(
                    cv_data=enriched_cv,
                    job_title=job.get("title", ""),
                    job_requirements=job.get("requirements", ""),
                )

        if not score_result:
            jobs = fetch_active_jobs(supabase)
            if jobs:
                best_result, best_job_id = compute_best_job_match(
                    supabase, enriched_cv, jobs
                )
                if best_result:
                    score_result = best_result
                    job_id       = best_job_id

        # Fallback: no job linked and no active jobs
        if not score_result:
            logger.info("Aucun job actif → quality fallback")
            score_result = _quality_fallback(enriched_cv)

        # Persist — pass enriched_cv so build_candidate_payload can merge
        # dimension_scores into ai_extracted_data (the ScorePanel fix)
        payload = build_candidate_payload(
            raw_text=raw_text,
            cv_info=cv_info,
            enriched_cv=enriched_cv,
            score_result=score_result,
            job_id=job_id,
        )
        update_candidate(supabase, candidate_id, payload)

        logger.info("CV %s traité → Score : %s", candidate_id, score_result.get("score", 0))
        return {"success": True, "score": score_result.get("score", 0)}

    except Exception as exc:
        logger.exception("Échec CV %s", candidate_id)
        update_candidate(supabase, candidate_id, {
            "processing_status": "failed",
            "processing_error":  str(exc)[:500],
            "updated_at":        utc_now(),
        })
        return {"success": False, "error": str(exc)}


# ============================================================================
# FONCTIONS UTILISÉES PAR drive_sync.py
# ============================================================================

def compute_best_job_match(supabase, cv_data: dict, jobs: list) -> tuple:
    """
    Trouve le poste qui correspond le mieux à un CV parmi une liste de postes.
    cv_data must already contain raw_text (call _enrich_cv_data first).
    Retourne (meilleur_score_result, meilleur_job_id).
    """
    logger.info("compute_best_job_match: %d jobs to evaluate", len(jobs))

    candidate_position = cv_data.get("current_position", "")
    candidate_domain   = classify_domain(candidate_position)

    best_score  = -1
    best_result = None
    best_job_id = None

    for job in jobs:
        try:
            result = compute_candidate_score(
                cv_data=cv_data,
                job_title=job.get("title", ""),
                job_requirements=job.get("requirements", ""),
            )
            s = result.get("score", 0)

            job_domain = classify_domain(job.get("title", ""))
            if job_domain != candidate_domain:
                s *= 0.70
                logger.info(
                    "  Domain mismatch: candidate=%s job=%s → penalized score=%.1f",
                    candidate_domain, job_domain, s
                )
            else:
                logger.info(
                    "  Job '%s' [%s] → score=%.1f",
                    job.get("title"), job_domain, s
                )

            if s > best_score:
                best_score  = s
                best_result = result
                best_job_id = job.get("id")

        except Exception as exc:
            logger.error("Erreur scoring poste %s : %s", job.get("id"), exc)

    if best_job_id:
        best_job_domain = classify_domain(
            next((j.get("title","") for j in jobs if j.get("id") == best_job_id), "")
        )
        if best_job_domain != candidate_domain and best_score < 50:
            logger.info(
                "Best match is cross-domain and low score (%.1f) → falling back to quality score",
                best_score
            )
            return None, None

    logger.info("Best match: job_id=%s score=%.1f", best_job_id, best_score)
    return best_result, best_job_id


def build_candidate_payload(
    raw_text    : str,
    cv_info     : dict,
    score_result: dict,
    enriched_cv : dict | None = None,
    job_id      : str | None  = None,
) -> dict:
    """
    Construit le dictionnaire complet à insérer/mettre à jour en base.
    Utilisé par process_cv et drive_sync.py.

    enriched_cv: cv_info already merged with raw_text (from _enrich_cv_data).
    When provided, dimension_scores and scoring metadata are merged into
    ai_extracted_data so ScorePanel.jsx source A resolves correctly.
    Falls back to bare cv_info for callers that haven't been updated yet.
    """
    # Build ai_extracted_data: merge scoring metadata into the CV blob
    # so ScorePanel can find dimension_scores at aiData.dimension_scores
    base_cv = enriched_cv if enriched_cv is not None else cv_info
    ai_data = sanitize_ai_data(_enrich_ai_data(base_cv, score_result))

    payload = {
        "cv_raw_text":       raw_text[:MAX_TEXT_LENGTH],
        "ai_extracted_data": ai_data,            # ← now contains dimension_scores

        "full_name": ensure_string(cv_info.get("full_name")),
        "email":     ensure_string(cv_info.get("email")),
        "phone":     ensure_string(cv_info.get("phone")),

        "current_position": ensure_string(
            cv_info.get("current_position")
            or cv_info.get("title")
            or cv_info.get("job_title")
            or cv_info.get("headline")
            or ""
        ),
        
        "hierarchy_level": score_result.get("hierarchy_level"),
        "education_level": score_result.get("full_details", {}).get("detected_education", "none"),
        "domain":          score_result.get("domain"),

        "skills":         ensure_list(cv_info.get("skills")),
        "education":      ensure_list(cv_info.get("education")),
        "work_history":   ensure_list(cv_info.get("work_history")),
        "certifications": ensure_list(cv_info.get("certifications")),
        "languages":      ensure_list(cv_info.get("languages")),
        "projects":       ensure_list(cv_info.get("projects")),

        "experience_years": cv_info.get("experience_years", 0),

        **_build_score_payload(score_result),

        "processing_status": "completed",
        "updated_at":        utc_now(),
    }

    if job_id:
        payload["job_id"] = job_id

    return payload
