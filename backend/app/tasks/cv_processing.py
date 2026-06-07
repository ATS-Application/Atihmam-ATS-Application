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

Changelog v2.1:
- Removed _make_quality_score_result (dead code; used 'extracted' instead of param 'cv_info' → NameError)
- _quality_fallback moved to top of helpers, above first call site
- _quality_fallback no longer mutates dimension_scores in-place (copy-on-write)
- process_cv fallback now passes enriched_cv (with raw_text) instead of bare cv_info
- Removed unused DOMAIN_SKILLS import
- _quality_fallback is the single source of truth; drive_sync.py delegates here

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
)

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

MAX_TEXT_LENGTH  = 50_000
MAX_AI_DATA_SIZE = 100_000

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
    enriched = dict(cv_info)
    enriched["raw_text"] = raw_text
    return enriched


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

    # Ensure the full CV text is available to the scorer
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
    dimension_scores (jsonb) carries the full breakdown.
    Flat columns are kept for indexed queries and the ScorePanel frontend aliases.
    """
    dims = score_result.get("dimension_scores", {})
    return {
        "score":            score_result.get("score", 0),
        "dimension_scores": dims,
        "score_confidence": score_result.get("confidence", 0),
        "score_reasoning":  score_result.get("reasoning", ""),
        "matched_keywords": score_result.get("matched_keywords", []),
        "missing_keywords": score_result.get("missing_keywords", []),
        # Flat columns for indexed queries / ScorePanel.jsx
        "keyword_score":            dims.get("keyword_score"),
        "experience_score":         dims.get("experience_score"),
        "semantic_score":           dims.get("semantic_score"),
        "project_complexity_score": dims.get("project_complexity_score"),
        "education_score":          dims.get("education_score"),
        "certification_score":      dims.get("certification_score"),
        "leadership_score":         dims.get("leadership_score"),
    }


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
        enriched_cv = _enrich_cv_data(cv_info, raw_text)

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
            # Pass enriched_cv so the fallback scorer has raw_text available
            score_result = _quality_fallback(enriched_cv)

        # Persist
        payload = build_candidate_payload(
            raw_text=raw_text,
            cv_info=cv_info,
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
            if s > best_score:
                best_score  = s
                best_result = result
                best_job_id = job.get("id")
        except Exception as exc:
            logger.error("Erreur de scoring pour le poste %s : %s", job.get("id"), exc)

    return best_result, best_job_id


def build_candidate_payload(
    raw_text    : str,
    cv_info     : dict,
    score_result: dict,
    job_id      : str | None = None,
) -> dict:
    """
    Construit le dictionnaire complet à insérer/mettre à jour en base.
    Utilisé par process_cv et drive_sync.py.
    """
    payload = {
        "cv_raw_text":       raw_text[:MAX_TEXT_LENGTH],
        "ai_extracted_data": sanitize_ai_data(cv_info),

        "full_name": ensure_string(cv_info.get("full_name")),
        "email":     ensure_string(cv_info.get("email")),
        "phone":     ensure_string(cv_info.get("phone")),

        "current_position": ensure_string(
            cv_info.get("current_position")
            or cv_info.get("title")
            or cv_info.get("job_title")
            or cv_info.get("headline")
        ),

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
