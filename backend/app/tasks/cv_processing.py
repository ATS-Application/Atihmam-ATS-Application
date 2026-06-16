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
import re
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
        # Si les données sont trop volumineuses, on ne tronque pas brutalement (casse le JSON)
        # On préfère supprimer les champs lourds si nécessaire, mais ici on augmente juste la limite
        if len(serialized) > MAX_AI_DATA_SIZE:
            logger.warning("Données IA trop volumineuses (%d octets)", len(serialized))
        return json.loads(serialized)
    except Exception as e:
        logger.error("Erreur lors de la sanitisation des données IA : %s", e)
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


def _sanitize_reasoning(text: str) -> str:
    """Supprime les templates JS mal formés et les textes parasites du reasoning."""
    if not text:
        return ""

    # Sécurité : s'assurer que l'IA n'a pas renvoyé un objet
    text_str = text if isinstance(text, str) else json.dumps(text)

    # Supprime les patterns type ${...}, {skills text}, backticks ou variables avec underscore (regex renforcée)
    text_str = re.sub(r'(\$\{.*?\}|\{.*?text\}|`.*?`|\{.*?_.*?\})', '', text_str)
    text_str = re.sub(r'\{[^{}]*?skills[^{}]*?\}', '', text_str)
    text_str = re.sub(r'\{[^{}]*?text[^{}]*?\}', '', text_str)
    # Supprime les textes parasites spécifiques identifiés
    parasites = ["grand logistics", "Learn more"]
    for p in parasites:
        text_str = text_str.replace(p, "")
    return text_str.strip()


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

    # Nettoyage des compétences pour éviter d'inclure des parasites dans le JD synthétique
    raw_skills = extracted.get("skills", []) or []
    skills = []
    for s in raw_skills[:25]:
        s_str = str(s)
        if s and "text}" not in s_str.lower() and "${" not in s_str:
            skills.append(s_str)
    
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
        "score_reasoning":  _sanitize_reasoning(score_result.get("reasoning", "")),
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
    
    # On s'assure que le champ 'reasoning' brut de l'IA ne pollue pas l'affichage
    # s'il est utilisé en fallback côté frontend.
    clean_info = dict(cv_info)
    if "reasoning" in clean_info:
        clean_info["reasoning"] = _sanitize_reasoning(clean_info["reasoning"])
    if "skills" in clean_info:
        clean_info["skills"] = [str(s) for s in clean_info.get("skills", []) if s]

    enriched = {
        **clean_info,
        "dimension_scores": dims,
        "matched_keywords": [_sanitize_reasoning(str(k)) for k in score_result.get("matched_keywords", []) if k],
        "missing_keywords": [_sanitize_reasoning(str(k)) for k in score_result.get("missing_keywords", []) if k],
        "score_reasoning":  _sanitize_reasoning(score_result.get("reasoning", "")),
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
    cv_data must already contain raw_text (call enrich_cv_data first).
    Retourne (meilleur_score_result, meilleur_job_id).

    FIX v2.3 — 3 corrections majeures :

    1. La détection du domaine candidat utilise maintenant le texte COMPLET du CV
       (skills + work_history + current_position), pas uniquement current_position.
       Un "Acheteur" dont current_position est vide ne tombait plus en "consulting".

    2. La détection du domaine du poste utilise titre + requirements (description),
       pas uniquement le titre. Un "Responsable Technique" avec une description
       BTP/génie civil est maintenant bien classé construction.

    3. Le score sauvegardé en base EST le score pénalisé — avant, la pénalité
       domaine était appliquée pour le classement mais le score non-pénalisé
       était sauvegardé dans best_result, créant l'incohérence visible en UI.
    """
    logger.info("compute_best_job_match: %d jobs à évaluer", len(jobs))

    # ── Domaine candidat : utilise le texte complet du CV, pas juste le titre ──
    candidate_position = cv_data.get("current_position", "")
    # On construit un texte combiné pour mieux détecter le domaine :
    # current_position + les 5 premiers titres de work_history + les skills
    wh_titles = " ".join(
        e.get("title", "") for e in cv_data.get("work_history", [])[:5]
    )
    skills_text = " ".join(str(s) for s in cv_data.get("skills", [])[:20])
    
    # FIX: On sépare le titre (poids fort) de la description (poids faible) 
    # pour que la fonction réelle l'emporte sur les compétences secondaires.
    candidate_domain = classify_domain(
        job_title=candidate_position,
        job_description=f"{wh_titles} {skills_text}"
    )

    logger.info("  Domaine candidat détecté : %s (Titre: '%s')",
                candidate_domain, candidate_position)

    best_score         = -1.0
    best_result        = None
    best_job_id        = None
    best_penalized     = False   # garde trace pour le log final

    for job in jobs:
        try:
            job_title       = job.get("title", "")
            job_requirements = job.get("requirements", "") or ""

            # Score brut candidat ↔ poste
            result = compute_candidate_score(
                cv_data=cv_data,
                job_title=job_title,
                job_requirements=job_requirements,
            )
            raw_score = float(result.get("score", 0))

            # ── Domaine du poste : titre + description ──────────────────────
            # FIX : on passe requirements en plus du titre pour éviter qu'un
            # "Responsable Technique" soit classé consulting faute de mots-clés
            # dans le titre seul.
            job_domain = classify_domain(
                f"{job_title} {job_requirements[:300]}"
            )

            # ── Pénalité domaine ────────────────────────────────────────────
            is_mismatch  = (job_domain != candidate_domain)
            penalized_score = raw_score * DOMAIN_MISMATCH_PENALTY if is_mismatch else raw_score

            logger.info(
                "  Poste '%s' [%s] → score brut=%.1f%s",
                job_title, job_domain, raw_score,
                f" → pénalisé={penalized_score:.1f} (mismatch candidat={candidate_domain})"
                if is_mismatch else "",
            )

            if penalized_score > best_score:
                best_score     = penalized_score
                best_job_id    = job.get("id")
                best_penalized = is_mismatch

                # FIX : on stocke le score PÉNALISÉ dans result pour que la
                # valeur sauvegardée en base corresponde à ce qui est affiché.
                best_result = {
                    **result,
                    "score":      round(penalized_score, 2),
                    "confidence": round(penalized_score, 2),
                    "reasoning":  result.get("reasoning", "") + (
                        f" [pénalité domaine ×{DOMAIN_MISMATCH_PENALTY} : "
                        f"candidat={candidate_domain} / poste={job_domain}]"
                        if is_mismatch else ""
                    ),
                }

        except Exception as exc:
            logger.error("Erreur scoring poste %s : %s", job.get("id"), exc)

    logger.info(
        "Meilleur match : job_id=%s score=%.1f%s",
        best_job_id, best_score,
        " [pénalisé domaine]" if best_penalized else "",
    )
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