# backend/app/services/cv_parser.py
"""
Orchestrateur Principal du Pipeline - Atihmam ATS
===================================================
Coordonne séquentiellement les étapes :
CV → Lecture & Extraction → Identification du poste exact → Évaluation isolée
"""

from __future__ import annotations

import io
from app.services.cv_extractor import CVExtractor
from app.services.cv_router import CVRouter
from app.services.cv_evaluator import CVEvaluator

DOMAIN_VALUE_MAP = {
    "Informatique & Développement logiciel": "informatique_dev",
    "Réseaux & Cybersécurité":               "reseaux_cyber",
    "Construction & BTP":                    "construction_btp",
    "Ingénierie":                            "ingenierie",
    "Finance & Comptabilité":                "finance_comptabilite",
    "Banque & Assurance":                    "banque_assurance",
    "Ressources Humaines":                   "ressources_humaines",
    "Marketing & Communication":             "marketing_communication",
    "Logistique & Transport":                "logistique_transport",
    "Santé & Médical":                       "sante_medical",
    "Éducation & Formation":                 "education",
    "Droit & Juridique":                     "droit_juridique",
    "Design & Créatif":                      "design_creatif",
    "Industrie & Production":                "industrie_production",
    "Étudiant / Stage":                      "etudiant_stage",
}

def process_candidate_resume(candidate, extracted_text: str):
    """
    Nouveau déroulement de traitement strict :
      1. Lecture du CV (effectuée en amont) ou extraction si nécessaire
      2. Affectation directe du poste correspondant au domaine métier sans déviation
      3. Retourne le candidat classé
    """
    if not extracted_text:
        print("[PIPELINE] Texte extrait manquant — Affectation par défaut 'autres'")
        candidate.domain = "autres"
        candidate.folder = "📁 Autres"
        return candidate

    # Utilisation du nouveau routeur modulaire
    domain = CVRouter.assign_domain_strictly(
        extracted_title=getattr(candidate, "extracted_title", ""),
        full_text=extracted_text
    )

    candidate.domain = domain or "autres"
    candidate.folder = candidate.domain
    
    print(f"[PIPELINE] Domaine attribué avec succès : {candidate.domain}")
    return candidate