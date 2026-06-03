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
from app.services.ai_service import extract_cv_info
from app.services.cv_parser import extract_text_from_bytes
from app.services.scoring_service import compute_candidate_score

# Logger pour tracer les erreurs et les étapes importantes
logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Taille maximale du texte brut du CV qu'on stocke en base (50 000 caractères)
MAX_TEXT_LENGTH = 50_000

# Taille maximale des données extraites par l'IA (100 000 caractères en JSON)
MAX_AI_DATA_SIZE = 100_000

# Ces erreurs sont "permanentes" : inutile de réessayer si elles surviennent
PERMANENT_ERRORS = (
    ValueError,
    PermissionError,
)

# Champs obligatoires que l'IA doit retourner après analyse du CV
REQUIRED_CV_FIELDS = [
    "skills",       # liste des compétences
    "work_history", # historique professionnel
    "education",    # formations / diplômes
]


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def utc_now() -> str:
    """Retourne la date et heure actuelle en UTC au format ISO (pour la base de données)."""
    return datetime.now(timezone.utc).isoformat()


def ensure_list(value: Any) -> list:
    """
    Garantit qu'une valeur est bien une liste.
    Si la valeur est None ou autre chose, on retourne une liste vide.
    Exemple : ensure_list(None) → []
              ensure_list(["Python"]) → ["Python"]
    """
    return value if isinstance(value, list) else []


def ensure_string(value: Any) -> str:
    """
    Garantit qu'une valeur est bien une chaîne de caractères.
    Si la valeur est None ou autre chose, on retourne une chaîne vide.
    Exemple : ensure_string(None) → ""
              ensure_string("Alice") → "Alice"
    """
    return value if isinstance(value, str) else ""


def sanitize_ai_data(data: dict) -> dict:
    """
    Nettoie et limite la taille des données extraites par l'IA.

    L'IA peut parfois retourner des données très volumineuses.
    On les sérialise en JSON, on les coupe si trop grandes, puis on les reparse.
    Si quelque chose tourne mal, on retourne un dictionnaire vide.
    """
    try:
        serialized = json.dumps(data)

        # Si les données sont trop grandes, on les tronque
        if len(serialized) > MAX_AI_DATA_SIZE:
            serialized = serialized[:MAX_AI_DATA_SIZE]

        return json.loads(serialized)
    except Exception:
        return {}


def validate_cv_info(cv_info: dict) -> None:
    """
    Vérifie que l'IA a bien retourné un dictionnaire avec les champs attendus.

    Si un champ obligatoire est absent, on log un avertissement (mais on ne bloque pas).
    Si ce n'est pas un dictionnaire du tout, on lève une erreur.
    """
    if not isinstance(cv_info, dict):
        raise ValueError("L'extraction IA doit retourner un dictionnaire")

    for field in REQUIRED_CV_FIELDS:
        if field not in cv_info:
            logger.warning("Champ manquant dans les données IA : %s", field)


def extract_text_safe(pdf_bytes: bytes, timeout: int = 30) -> str:
    """
    Extrait le texte d'un PDF avec une limite de temps (timeout).

    On utilise un thread séparé pour pouvoir interrompre l'extraction
    si elle prend trop longtemps (plus de 30 secondes par défaut).
    Cela évite que le serveur reste bloqué sur un PDF corrompu ou trop lourd.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(extract_text_from_bytes, pdf_bytes)
        return future.result(timeout=timeout)


# ============================================================================
# FONCTIONS D'ACCÈS À LA BASE DE DONNÉES
# ============================================================================

def update_candidate(supabase, candidate_id: str, data: dict):
    """
    Met à jour les données d'un candidat dans Supabase.

    Paramètres :
        supabase     → le client Supabase admin
        candidate_id → l'identifiant unique du candidat (UUID)
        data         → les champs à mettre à jour (dictionnaire)
    """
    supabase.table("candidates").update(data).eq("id", candidate_id).execute()


def fetch_candidate(supabase, candidate_id: str):
    """
    Récupère toutes les données d'un candidat depuis Supabase.
    Retourne None si le candidat n'existe pas.
    """
    return (
        supabase.table("candidates")
        .select("*")
        .eq("id", candidate_id)
        .single()
        .execute()
        .data
    )


def fetch_job(supabase, job_id: str):
    """
    Récupère les données d'un poste depuis Supabase.
    Retourne None si le poste n'existe pas.
    """
    return (
        supabase.table("jobs")
        .select("*")
        .eq("id", job_id)
        .single()
        .execute()
        .data
    )


def fetch_active_jobs(supabase):
    """
    Récupère la liste de tous les postes actifs (is_active = true).
    Retourne une liste vide si aucun poste n'est actif.
    On ne récupère que l'id, le titre et les exigences (pas tout le reste).
    """
    return (
        supabase.table("jobs")
        .select("id, title, requirements")
        .eq("is_active", True)
        .execute()
        .data
        or []
    )


# ============================================================================
# PIPELINE PRINCIPAL DE TRAITEMENT
# ============================================================================

def process_cv(candidate_id: str, storage_path: str, job_id: str | None = None):
    """
    Traite un CV de A à Z : téléchargement, extraction IA, scoring, sauvegarde.

    Cette fonction est appelée :
    - En tâche de fond par FastAPI (BackgroundTasks) après un upload
    - Ou directement de façon synchrone si besoin

    Paramètres :
        candidate_id   → l'UUID du candidat déjà créé en base
        storage_path   → le chemin du PDF dans Supabase Storage
        job_id         → (optionnel) l'UUID du poste auquel le candidat postule
    """

    # On récupère le client Supabase avec les droits admin
    supabase = get_supabase_admin()

    try:
        logger.info(f"Début du traitement du CV : {candidate_id}")

        # ── Étape 0 : Vérifications préliminaires ────────────────────────────

        # On vérifie que le candidat existe bien en base
        candidate = fetch_candidate(supabase, candidate_id)
        if not candidate:
            raise ValueError("Candidat introuvable en base de données")

        # Si le CV a déjà été traité avec succès, on ne le retraite pas
        if candidate.get("processing_status") == "completed":
            return {"message": "CV déjà traité avec succès"}

        # On marque le candidat comme "en cours de traitement"
        # Cela permet au frontend d'afficher un spinner de chargement
        update_candidate(supabase, candidate_id, {
            "processing_status": "processing",
            "processing_error": None,
            "updated_at": utc_now(),
        })

        # ── Étape 1 : Téléchargement du PDF ──────────────────────────────────

        pdf_bytes = (
            supabase.storage
            .from_("cvs")
            .download(storage_path)
        )

        if not pdf_bytes:
            raise ValueError("Impossible de télécharger le PDF depuis le stockage")

        # ── Étape 2 : Extraction du texte brut ───────────────────────────────

        # On extrait le texte lisible depuis le PDF binaire
        # Un timeout de 30s évite de bloquer sur un PDF corrompu
        raw_text = extract_text_safe(pdf_bytes)

        if not raw_text.strip():
            raise ValueError("Le PDF ne contient aucun texte lisible (PDF image non OCRisé ?)")

        # ── Étape 3 : Analyse IA du CV ───────────────────────────────────────

        # L'IA lit le texte brut et extrait les infos structurées :
        # nom, email, compétences, expériences, formations, etc.
        cv_info = extract_cv_info(raw_text)

        # On vérifie que l'IA a bien retourné les champs obligatoires
        validate_cv_info(cv_info)

        # ── Étape 4 : Calcul du score ─────────────────────────────────────────

        score_result = None
        resolved_job_id = job_id  # Le poste final auquel on va associer le candidat

        if job_id:
            # CAS 1 : Un poste spécifique a été fourni lors de l'upload
            # On score le CV uniquement par rapport à ce poste
            job = fetch_job(supabase, job_id)
            if job:
                score_result = compute_candidate_score(
                    cv_data=cv_info,
                    job_title=job.get("title", ""),
                    job_requirements=job.get("requirements", ""),
                    supabase=supabase,
                )

        else:
            # CAS 2 : Pas de poste spécifié → on compare avec tous les postes actifs
            # et on garde le meilleur score (le poste qui correspond le mieux au CV)
            jobs = fetch_active_jobs(supabase)

            best_score = -1
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

                    score = result.get("score", 0)

                    # On garde uniquement le meilleur score
                    if score > best_score:
                        best_score = score
                        best_result = result
                        best_job_id = job.get("id")

                except Exception as e:
                    logger.error(f"Erreur lors du scoring pour le poste {job.get('id')} : {e}")

            score_result = best_result
            resolved_job_id = best_job_id

        # CAS 3 : Aucun poste actif disponible → on score la qualité du CV directement
        # On utilise analyze_cv_depth() qui évalue la profondeur et la qualité du CV
        # sans avoir besoin de le comparer à une offre d'emploi
        if not score_result:
            from app.services.ai_service import analyze_cv_depth

            # Analyse de la profondeur du CV (métriques, descriptions, lacunes...)
            depth_report = analyze_cv_depth(cv_info)
            depth_score = depth_report.get("overall_depth_score") or 0

            # On construit un score_result avec la même structure qu'un vrai scoring
            # pour que le frontend puisse l'afficher normalement
            score_result = {
                "score": depth_score,
                "dimension_scores": {
                    "keyword_score": 0,           # Pas de mots-clés à comparer (pas de poste)
                    "semantic_score": 0,           # Pas de similarité sémantique (pas de poste)
                    "experience_score": min(       # Score basé sur les années d'expérience
                        float(cv_info.get("experience_years") or 0) * 10, 100
                    ),
                    "certification_score": 0,      # Pas de certifications à comparer
                    "education_score": 75.0,       # Score de formation par défaut
                    "leadership_score": 0,         # Pas de leadership à comparer
                    "project_complexity_score": depth_score,  # Basé sur la qualité du CV
                },
                "confidence": 0.5,
                "reasoning": "Scoré sur la qualité du CV (aucun poste actif disponible)",
                "matched_keywords": [],
                "missing_keywords": [],
            }

        # ── Étape 5 : Sauvegarde en base de données ───────────────────────────

        # On prépare toutes les données à sauvegarder pour ce candidat
        payload = {
            # Texte brut du CV (limité à MAX_TEXT_LENGTH caractères)
            "cv_raw_text": raw_text[:MAX_TEXT_LENGTH],

            # Données structurées extraites par l'IA
            "ai_extracted_data": sanitize_ai_data(cv_info),

            # Informations personnelles
            "full_name": ensure_string(cv_info.get("full_name")),
            "email":     ensure_string(cv_info.get("email")),
            "phone":     ensure_string(cv_info.get("phone")),

            # Compétences et parcours
            "skills":       ensure_list(cv_info.get("skills")),
            "education":    ensure_list(cv_info.get("education")),
            "work_history": ensure_list(cv_info.get("work_history")),

            # Années d'expérience (0 si non détecté)
            "experience_years": cv_info.get("experience_years", 0),

            # Résultats du scoring
            "score":            score_result.get("score", 0),
            "dimension_scores": score_result.get("dimension_scores", {}),
            "score_confidence": score_result.get("confidence", 0),

            # Statut final : traitement terminé avec succès
            "processing_status": "completed",
            "updated_at": utc_now(),
        }

        # On associe le candidat au poste trouvé (si applicable)
        if resolved_job_id:
            payload["job_id"] = resolved_job_id

        # On sauvegarde tout en base
        update_candidate(supabase, candidate_id, payload)

        logger.info(f"CV traité avec succès : {candidate_id} — Score : {payload['score']}")

        return {
            "success": True,
            "candidate_id": candidate_id,
            "score": payload["score"],
        }

    except Exception as e:
        # ── Gestion des erreurs ───────────────────────────────────────────────
        # Si quelque chose tourne mal à n'importe quelle étape,
        # on marque le candidat comme "échoué" avec le message d'erreur.
        # Cela permet au frontend d'afficher un message d'erreur clair
        # au lieu de rester bloqué sur "Analyse en cours..."
        logger.exception(f"Échec du traitement du CV {candidate_id} : {e}")

        update_candidate(supabase, candidate_id, {
            "processing_status": "failed",
            "processing_error": str(e),
            "updated_at": utc_now(),
        })

        return {
            "success": False,
            "error": str(e),
        }


# ============================================================================
# FONCTIONS UTILISÉES PAR drive_sync.py
# ============================================================================

def compute_best_job_match(supabase, cv_info: dict, jobs: list) -> tuple:
    """
    Trouve le poste qui correspond le mieux à un CV parmi une liste de postes.

    Pour chaque poste, on calcule un score de correspondance.
    On retourne le meilleur résultat et l'UUID du poste correspondant.

    Retourne un tuple : (meilleur_score_result, meilleur_job_id)
    Si aucun poste ne peut être scoré, retourne (None, None).
    """
    best_score = -1
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
            score = result.get("score", 0)

            if score > best_score:
                best_score = score
                best_result = result
                best_job_id = job.get("id")

        except Exception as e:
            logger.error(f"Erreur de scoring pour le poste {job.get('id')} : {e}")

    return best_result, best_job_id


def build_candidate_payload(
    raw_text: str,
    cv_info: dict,
    score_result: dict,
    job_id: str | None = None,
) -> dict:
    """
    Construit le dictionnaire complet à insérer en base pour un nouveau candidat.

    Utilisé par drive_sync.py lors de la synchronisation Google Drive.
    Contrairement à process_cv() qui met à jour un candidat existant,
    cette fonction crée le payload pour une insertion initiale.

    Paramètres :
        raw_text     → texte brut extrait du PDF
        cv_info      → données structurées extraites par l'IA
        score_result → résultat du scoring (score, dimensions, etc.)
        job_id       → UUID du poste associé (optionnel)
    """
    payload = {
        # Texte brut et données IA
        "cv_raw_text":       raw_text[:MAX_TEXT_LENGTH],
        "ai_extracted_data": sanitize_ai_data(cv_info),

        # Informations personnelles
        "full_name": ensure_string(cv_info.get("full_name")),
        "email":     ensure_string(cv_info.get("email")),
        "phone":     ensure_string(cv_info.get("phone")),

        # Compétences et parcours (toujours des listes, jamais null)
        "skills":         ensure_list(cv_info.get("skills")),
        "education":      ensure_list(cv_info.get("education")),
        "work_history":   ensure_list(cv_info.get("work_history")),
        "certifications": ensure_list(cv_info.get("certifications")),
        "languages":      ensure_list(cv_info.get("languages")),
        "projects":       ensure_list(cv_info.get("projects")),

        # Expérience
        "experience_years": cv_info.get("experience_years", 0),

        # Scoring
        "score":            score_result.get("score", 0),
        "dimension_scores": score_result.get("dimension_scores", {}),
        "score_confidence": score_result.get("confidence", 0),

        # Statut : traitement terminé
        "processing_status": "completed",
        "updated_at": utc_now(),
    }

    # On associe le poste seulement si un job_id a été fourni
    if job_id:
        payload["job_id"] = job_id

    return payload
