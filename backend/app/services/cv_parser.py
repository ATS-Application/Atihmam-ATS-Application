# backend/app/services/cv_parser.py
"""
Orchestrateur Principal du Pipeline - Atihmam ATS
Coordonne : CV → Lecture & Extraction → Classification domaine → Évaluation.
"""

from __future__ import annotations

import logging

from app.services.cv_extractor import CVExtractor, extract_text_from_bytes, extract_text_from_path
from app.services.cv_router import CVRouter

logger = logging.getLogger(__name__)

FOLDER_LABELS: dict[str, str] = {
    "informatique_dev": "📁 Informatique",
    "reseaux_cyber": "📁 Réseaux & Cybersécurité",
    "construction_btp": "📁 Construction & BTP",
    "ingenierie": "📁 Ingénierie",
    "finance_comptabilite": "📁 Finance",
    "banque_assurance": "📁 Banque & Assurance",
    "ressources_humaines": "📁 Ressources Humaines",
    "marketing_communication": "📁 Marketing",
    "logistique_transport": "📁 Logistique",
    "sante_medical": "📁 Santé",
    "education": "📁 Éducation",
    "droit_juridique": "📁 Juridique",
    "design_creatif": "📁 Design",
    "industrie_production": "📁 Industrie",
    "etudiant_stage": "📁 Étudiant / Stage",
    "autres": "📁 Autres",
}


def process_candidate_resume(candidate, extracted_text: str):
    """
    Pipeline de classification :
      1. Texte déjà extrait en amont
      2. Affectation du domaine métier via CVRouter
      3. Retourne le candidat classé
    """
    if not extracted_text:
        logger.warning("Texte extrait manquant — affectation par défaut 'autres'")
        candidate.domain = "autres"
        candidate.folder = FOLDER_LABELS["autres"]
        return candidate

    domain = CVRouter.assign_domain_strictly(
        extracted_title=getattr(candidate, "extracted_title", "")
        or getattr(candidate, "current_position", ""),
        full_text=extracted_text,
    )

    candidate.domain = domain or "autres"
    candidate.folder = FOLDER_LABELS.get(candidate.domain, FOLDER_LABELS["autres"])

    logger.info("Domaine attribué : %s", candidate.domain)
    return candidate


__all__ = [
    "CVExtractor",
    "CVRouter",
    "extract_text_from_bytes",
    "extract_text_from_path",
    "process_candidate_resume",
    "FOLDER_LABELS",
]
