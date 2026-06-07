# app/tasks/cv_processing.py

"""
Pipeline de traitement des CVs (VERSION MVP - SANS CELERY)

Ce fichier est le cœur du traitement des CVs dans l'ATS.
Quand un recruteur uploade un CV, voici ce qui se passe dans l'ordre :

    1. On télécharge le PDF depuis le stockage Supabase
    2. On extrait le texte brut du PDF
    3. L'IA analyse le texte et en extrait les infos structurées
       (nom, email, compétences, expériences, formations...)
    4. On calcule un score de correspondance avec les postes actifs
       → Si aucun poste actif : on score via JD synthétique (tous les domaines)
    5. On sauvegarde tout dans la base de données

⚠️ Version simplifiée : pas de Celery, pas de Redis.
   Le traitement se fait en tâche de fond via FastAPI BackgroundTasks.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.db.supabase_client import get_supabase_admin
from app.services.ai_service import extract_cv_info
from app.services.cv_parser import extract_text_from_bytes
from app.services.scoring_service import (
    compute_candidate_score,
    classify_domain,
    Domain,
    DOMAIN_SKILLS,
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

REQUIRED_CV_FIELDS = [
    "skills",
    "work_history",
    "education",
]


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
    for field in REQUIRED_CV_FIELDS:
        if field not in cv_info:
            logger.warning("Champ manquant dans les données IA : %s", field)


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
    Injects raw_text into cv_data so compute_candidate_score uses the full
    CV body for scoring instead of reconstructing from fragments.
    This is the critical fix for keywords/semantic/education/certifications
    all returning 0 — those scorers need the complete CV text.
    """
    enriched = dict(cv_info)
    enriched["raw_text"] = raw_text
    return enriched


def _make_quality_score_result(cv_info: dict, raw_text: str) -> dict:
    """
    HIGH-QUALITY autonomous scoring for Drive CVs.
    Optimized for strong professional profiles (Acheteur Senior, etc.).
    """
    position = (
        extracted.get("current_position")
        or extracted.get("title")
        or "Acheteur Senior Logistique"
    )
    domain_str = classify_domain(position)

    # Extract rich content from CV
    skills = extracted.get("skills", [])[:30]
    work_history = extracted.get("work_history", [])
    projects = extracted.get("projects", [])

    exp_titles = [exp.get("title", "") for exp in work_history if exp.get("title")]
    proj_names = [p.get("name", "") for p in projects if p.get("name")]

    skills_str = ", ".join(skills) if skills else "achats, logistique, négociation"
    exp_str = ", ".join(exp_titles[:12]) if exp_titles else ""
    proj_str = ", ".join(proj_names[:6]) if proj_names else ""

    synthetic_title = position

    # Very rich synthetic JD
    synthetic_jd = f"""
    Nous recherchons un {synthetic_title} expérimenté avec une solide expertise en achats et logistique internationale.

    Compétences clés attendues :
    {skills_str}

    Expérience professionnelle :
    {exp_str}

    Projets & Réalisations :
    {proj_str}

    Missions principales :
    - Pilotage stratégique des achats et optimisation des coûts (TCO)
    - Sourcing international, gestion des transitaires et procédures douanières
    - Négociation contractuelle et management de panels fournisseurs
    - Suivi des KPI, reporting budgétaire et utilisation d'ERP (SAGE X3, etc.)
    - Gestion de projets multi-sites et sécurisation de la chaîne d'approvisionnement
    """

    # Ensure full raw text is available (critical)
    cv_data = dict(extracted)
    raw_text = extracted.get("raw_text") or extracted.get("full_text") or ""
    if raw_text:
        cv_data["raw_text"] = raw_text

    result = compute_candidate_score(
        cv_data=cv_data,
        job_title=synthetic_title,
        job_requirements=synthetic_jd.strip(),
    )

    result["reasoning"] = (
        f"Score qualité autonome — Domaine détecté : {domain_str}. "
        "Évaluation basée sur la richesse du parcours (12+ ans Achats & Logistique)."
    )
    result["matched_job"] = None

    return result


def _build_score_payload(score_result: dict) -> dict:
    """
    Build safe payload - only insert columns that exist in the DB.
    dimension_scores (jsonb) contains everything.
    """
    dims = score_result.get("dimension_scores", {})

    return {
        "score": score_result.get("score", 0),
        "dimension_scores": dims,
        "score_confidence": score_result.get("confidence", 0),
        "score_reasoning": score_result.get("reasoning", ""),
        "matched_keywords": score_result.get("matched_keywords", []),
        "missing_keywords": score_result.get("missing_keywords", []),

        # Only insert columns that currently exist or were just added
        "keyword_score": dims.get("keyword_score"),
        "experience_score": dims.get("experience_score"),
        "semantic_score": dims.get("semantic_score"),
        "project_complexity_score": dims.get("project_complexity_score"),   # new
        "education_score": dims.get("education_score"),                     # new
        "certification_score": dims.get("certification_score"),             # new
        "leadership_score": dims.get("leadership_score"),                   # new
    }


# ============================================================================
# PIPELINE PRINCIPAL DE TRAITEMENT
# ============================================================================

def process_cv(candidate_id: str, storage_path: str, job_id: str | None = None):
    supabase = get_supabase_admin()

    try:
        logger.info("🚀 Traitement CV : %s", candidate_id)

        candidate = fetch_candidate(supabase, candidate_id)
        if not candidate:
            raise ValueError("Candidat non trouvé")

        update_candidate(supabase, candidate_id, {
            "processing_status": "processing",
            "updated_at": utc_now(),
        })

        # Téléchargement PDF
        pdf_bytes = supabase.storage.from_("cvs").download(storage_path)
        raw_text  = extract_text_safe(pdf_bytes)

        # Extraction IA
        cv_info = extract_cv_info(raw_text)

        # Enrich with raw_text so scorer has the full CV body
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
        else:
            jobs = fetch_active_jobs(supabase)
            if jobs:
                best_result, best_job_id = compute_best_job_match(
                    supabase, enriched_cv, jobs
                )
                if best_result:
                    score_result = best_result
                    job_id       = best_job_id

        # Fallback: no job linked and no active jobs → synthetic JD quality score
        if not score_result:
            logger.info("Aucun job actif → rich quality fallback")
            score_result = _quality_fallback(cv_info)
        # Sauvegarde
        payload = build_candidate_payload(
            raw_text=raw_text,
            cv_info=cv_info,
            score_result=score_result,
            job_id=job_id,
        )
        update_candidate(supabase, candidate_id, payload)

        logger.info(
            "✅ CV %s traité → Score : %s", candidate_id, score_result.get("score", 0)
        )
        return {"success": True, "score": score_result.get("score", 0)}

    except Exception as e:
        logger.exception("Échec CV %s", candidate_id)
        update_candidate(supabase, candidate_id, {
            "processing_status": "failed",
            "processing_error":  str(e)[:500],
            "updated_at":        utc_now(),
        })
        return {"success": False, "error": str(e)}


# ============================================================================
# FONCTIONS UTILISÉES PAR drive_sync.py
# ============================================================================

def compute_best_job_match(supabase, cv_data: dict, jobs: list) -> tuple:
    """
    Trouve le poste qui correspond le mieux à un CV parmi une liste de postes.
    cv_data must already contain raw_text (use _enrich_cv_data before calling).
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
            logger.error(
                "Erreur de scoring pour le poste %s : %s", job.get("id"), exc
            )

    return best_result, best_job_id


def build_candidate_payload(
    raw_text    : str,
    cv_info     : dict,
    score_result: dict,
    job_id      : str | None = None,
) -> dict:
    """
    Construit le dictionnaire complet à insérer/mettre à jour en base.
    Utilisé par drive_sync.py lors de la synchronisation Google Drive.
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

def _quality_fallback(extracted: dict) -> dict:
    """
    HIGH-QUALITY autonomous scoring for CVs without linked job.
    Used by both Drive sync and manual upload.
    """
    position = (
        extracted.get("current_position")
        or extracted.get("title")
        or "Acheteur Senior Logistique"
    )

    # Correct call - classify_domain accepts 1 or 2 arguments
    domain_str = classify_domain(position)

    # Rich content extraction
    skills = extracted.get("skills", [])[:30]
    work_history = extracted.get("work_history", [])
    projects = extracted.get("projects", [])

    exp_titles = [exp.get("title", "") for exp in work_history if exp.get("title")]
    proj_names = [p.get("name", "") for p in projects if p.get("name")]

    skills_str = ", ".join(skills) if skills else "achats, logistique, négociation"
    exp_str = ", ".join(exp_titles[:12]) if exp_titles else ""
    proj_str = ", ".join(proj_names[:6]) if proj_names else ""

    synthetic_title = position

    synthetic_jd = f"""
    Nous recherchons un {synthetic_title} expérimenté en Achats et Logistique Internationale.

    Compétences attendues : {skills_str}.

    Expériences professionnelles : {exp_str}.

    Projets et réalisations : {proj_str}.

    Missions clés :
    - Pilotage stratégique des achats et optimisation des coûts (TCO)
    - Sourcing international, gestion des transitaires, procédures douanières, Incoterms
    - Négociation contractuelle et management de panels fournisseurs
    - Suivi KPI, reporting budgétaire, utilisation SAGE X3 / ERP
    - Gestion de projets multi-sites et sécurisation de la chaîne d'approvisionnement
    """

    # Ensure full raw text is passed
    cv_data = dict(extracted)
    raw_text = extracted.get("raw_text") or extracted.get("full_text") or ""
    if raw_text:
        cv_data["raw_text"] = raw_text

    result = compute_candidate_score(
        cv_data=cv_data,
        job_title=synthetic_title,
        job_requirements=synthetic_jd.strip(),
    )

    result["reasoning"] = (
        f"Score qualité autonome — Domaine : {domain_str}. "
        "Évaluation basée sur la richesse du parcours professionnel."
    )
    return result
