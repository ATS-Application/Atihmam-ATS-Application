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
       → Si aucun poste actif : on score la qualité du CV directement
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
from app.services.ai_service import extract_cv_info, analyze_cv_depth
from app.services.cv_parser import extract_text_from_bytes
from app.services.scoring_service import (
    _build_cv_text,
    compute_candidate_score,
    compute_cv_quality_score,
    classify_domain,
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

def _build_fallback_score_result(cv_info: dict, depth_report: dict) -> dict:
    """
    Fallback score for candidates with no active job posting.
    Uses compute_cv_quality_score from scoring_service v2.0.
    """
    quality = compute_cv_quality_score(_build_cv_text(cv_info))
    depth_score = float(depth_report.get("overall_depth_score") or 0)

    # Blend CV quality with depth analysis
    blended = round((quality["quality_score"] * 0.6 + depth_score * 40.0) / 100, 4)

    return {
        "score":            round(quality["quality_score"], 2),
        "confidence":       0.6,
        "domain":           classify_domain(cv_info.get("current_position") or ""),
        "hierarchy_level":  "collaborateur",
        "reasoning":        depth_report.get("summary", "Analyse qualité CV autonome"),
        "matched_keywords": [],
        "missing_keywords": [],
        "dimension_scores": {
            "keyword_score":            0.0,
            "semantic_score":           0.0,
            "experience_score":         min(float(cv_info.get("experience_years") or 0) / 10.0, 1.0),
            "education_score":          quality["details"]["language"].get("structure_score", 0.5),
            "certification_score":      0.0,
            "leadership_score":         0.0,
            "project_complexity_score": depth_score / 100.0 if depth_score > 1 else depth_score,
            "language_score":           quality["language_quality"] / 100.0,
        },
    }


def _build_score_payload(score_result: dict) -> dict:
    """
    Extrait les champs de scoring à persister.

    FIX : l'ancienne version de process_cv omettait score_reasoning,
    matched_keywords et missing_keywords — ces colonnes restaient NULL
    ce qui empêchait l'affichage des mots-clés et du raisonnement IA.
    """
    return {
        "score":            score_result.get("score", 0),
        "dimension_scores": score_result.get("dimension_scores", {}),
        "score_confidence": score_result.get("confidence", 0),
        "score_reasoning":  score_result.get("reasoning", ""),
        "matched_keywords": score_result.get("matched_keywords", []),
        "missing_keywords": score_result.get("missing_keywords", []),
    }


# ============================================================================
# PIPELINE PRINCIPAL DE TRAITEMENT
# ============================================================================

def process_cv(candidate_id: str, storage_path: str, job_id: str | None = None):
    supabase = get_supabase_admin()

    try:
        logger.info(f"🚀 Traitement CV : {candidate_id}")

        candidate = fetch_candidate(supabase, candidate_id)
        if not candidate:
            raise ValueError("Candidat non trouvé")

        update_candidate(supabase, candidate_id, {
            "processing_status": "processing",
            "updated_at": utc_now(),
        })

        # Téléchargement PDF
        pdf_bytes = supabase.storage.from_("cvs").download(storage_path)
        raw_text = extract_text_safe(pdf_bytes)

        # Extraction IA
        cv_info = extract_cv_info(raw_text)

        # === SCORING ===
        score_result = None

        if job_id:
            job = fetch_job(supabase, job_id)
            if job:
                score_result = compute_candidate_score(
                    cv_data=cv_info,
                    job_title=job.get("title", ""),
                    job_requirements=job.get("requirements", ""),
                    supabase=supabase,
                )
        else:
            jobs = fetch_active_jobs(supabase)
            if jobs:
                best_result, best_job_id = compute_best_job_match(supabase, cv_info, jobs)
                if best_result:
                    score_result = best_result
                    job_id = best_job_id

      
        if not score_result:
            cv_text = _build_cv_text(cv_info)
            score_result = compute_cv_quality_score(cv_text)
            # Wrap to match expected shape
            score_result = {
                "score":            score_result["quality_score"],
                "confidence":       0.5,
                "domain":           classify_domain(cv_info.get("current_position") or ""),
                "hierarchy_level":  "collaborateur",
                "reasoning":        score_result["overall_assessment"],
                "matched_keywords": [],
                "missing_keywords": [],
                "dimension_scores": {
                    "language_score":   score_result["language_quality"] / 100.0,
                    "complexity_score": score_result["complexity"] / 100.0,
                },
            }

        update_candidate(supabase, candidate_id, payload)

        logger.info(f"✅ CV {candidate_id} traité → Score : {score_result.get('score', 0)}")

        return {"success": True, "score": score_result.get("score", 0)}

    except Exception as e:
        logger.exception(f"Échec CV {candidate_id}")
        update_candidate(supabase, candidate_id, {
            "processing_status": "failed",
            "processing_error": str(e)[:500],
            "updated_at": utc_now(),
        })
        return {"success": False, "error": str(e)}


# ============================================================================
# FONCTIONS UTILISÉES PAR drive_sync.py
# ============================================================================

def compute_best_job_match(supabase, cv_info: dict, jobs: list) -> tuple:
    """
    Trouve le poste qui correspond le mieux à un CV parmi une liste de postes.
    Retourne (meilleur_score_result, meilleur_job_id).
    """
    best_score  = -1
    best_result = None
    best_job_id = None

    for job in jobs:
        try:
            result = compute_candidate_score(
                cv_data=cv_info,
                job_title=job.get("title", ""),
                job_requirements=job.get("requirements", ""),
                supabase=supabase,
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
    Construit le dictionnaire complet à insérer en base pour un nouveau candidat.
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
            or cv_info.get("title")        # some extractors emit "title"
            or cv_info.get("job_title")    # defensive alias
            or cv_info.get("headline")
        ),

        "skills":         ensure_list(cv_info.get("skills")),
        "education":      ensure_list(cv_info.get("education")),
        "work_history":   ensure_list(cv_info.get("work_history")),
        "certifications": ensure_list(cv_info.get("certifications")),
        "languages":      ensure_list(cv_info.get("languages")),
        "projects":       ensure_list(cv_info.get("projects")),

        "experience_years": cv_info.get("experience_years", 0),

        # Scoring complet (aligned with process_cv)
        **_build_score_payload(score_result),

        "processing_status": "completed",
        "updated_at":        utc_now(),
    }

    if job_id:
        payload["job_id"] = job_id

    return payload
