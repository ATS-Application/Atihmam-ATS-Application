"""
scoring_service.py — Service de scoring ATS pour le marché francophone africain.
Version 2.1 — Architecture hiérarchique à 4 niveaux avec leadership par actions.
Conçu pour Atihmam Conseils, adapté au contexte ivoirien et francophone.

Changelog v2.1:
- Suppression de compute_cv_quality_score (références indéfinies supprimées)
- compute_candidate_score accepte maintenant supabase= kwarg (ignoré, compatibilité)
- Correction __all__ (virgule manquante)
- Tous les helpers privés supprimés (NameError à runtime)

Changelog v2.1.1 (feedback loop fix):
- DEFAULT_WEIGHTS replaced with INTELLIGENT_SCORE_DEFAULT_WEIGHTS, whose 6 keys
  (skill_match, experience, project_complexity, seniority, domain_diversity,
  career_progression) match compute_intelligent_score's score_breakdown.
  The old 8-key hierarchical-profile weight space was never consumed by
  compute_intelligent_score, so feedback never affected scoring. DEFAULT_WEIGHTS
  is kept as a backwards-compat alias.
"""

# =============================================================================
# Imports
# =============================================================================
import re
import math
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
from collections import Counter

import numpy as np

logger = logging.getLogger(__name__)

# =============================================================================
# Utilitaire de normalisation textuelle
# =============================================================================

_ACCENT_TABLE = str.maketrans({
    'à': 'a', 'â': 'a', 'ä': 'a', 'á': 'a', 'ã': 'a', 'å': 'a',
    'è': 'e', 'é': 'e', 'ê': 'e', 'ë': 'e', 'ē': 'e',
    'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i', 'ī': 'i',
    'ò': 'o', 'ó': 'o', 'ô': 'o', 'ö': 'o', 'õ': 'o', 'ø': 'o', 'ō': 'o',
    'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u', 'ū': 'u',
    'ý': 'y', 'ÿ': 'y',
    'ç': 'c', 'ñ': 'n', 'š': 's', 'ž': 'z',
    'œ': 'oe', 'æ': 'ae', 'ß': 'ss',
})


def normalize_text(text: str) -> str:
    """
    Normalise un texte pour le matching insensible aux accents, ligatures
    et variations de casse.
    """
    return text.lower().translate(_ACCENT_TABLE)


# =============================================================================
# 1. Énumérations fondamentales
# =============================================================================

class HierarchyLevel(str, Enum):
    COLLABORATEUR = "collaborateur"
    MANAGER_INTERMEDIAIRE = "manager_intermediaire"
    MANAGER_SENIOR = "manager_senior"
    DIRECTION = "direction"


class Domain(str, Enum):
    TECH = "tech"
    LEGAL = "legal"
    HEALTH = "health"
    HR = "hr"
    FINANCE = "finance"
    MARKETING = "marketing"
    SALES = "sales"
    EDUCATION = "education"
    AGRICULTURE = "agriculture"
    CONSTRUCTION = "construction"
    LOGISTICS = "logistics"
    TELECOM = "telecom"
    ENERGY = "energy"
    MINING = "mining"
    HOSPITALITY = "hospitality"
    MEDIA = "media"
    INSURANCE = "insurance"
    REAL_ESTATE = "real_estate"
    CONSULTING = "consulting"
    PUBLIC_ADMIN = "public_admin"
    NGO = "ngo"
    PHARMA = "pharma"
    RETAIL = "retail"
    TRANSPORT = "transport"
    ENVIRONMENT = "environment"
    CRAFTSMANSHIP = "craftsmanship"
    SECURITY = "security"


# =============================================================================
# 2. Mapping des marqueurs de niveau hiérarchique
# =============================================================================

HIERARCHY_TITLE_MARKERS: Dict[HierarchyLevel, List[str]] = {
    HierarchyLevel.COLLABORATEUR: [
        "opérateur", "technicien", "analyste", "assistant", "agent",
        "ouvrier", "employé", "stagiaire", "junior", "débutant",
        "secrétaire", "comptable", "caissier", "chauffeur", "agent de",
        "operator", "technician", "analyst", "assistant", "agent",
        "junior", "staff", "operator", "clerk", "secretary",
    ],
    HierarchyLevel.MANAGER_INTERMEDIAIRE: [
        "chef de service", "chef service", "supervisor", "superviseur",
        "team lead", "team leader", "coordonnateur", "coordinateur",
        "chef d'équipe", "chef equipe", "responsable d'équipe",
        "responsable equipe", "manager de proximité", "contremaître",
        "contremaitre", "superintendent", "foreman",
    ],
    HierarchyLevel.MANAGER_SENIOR: [
        "responsable", "chef de département", "chef departement",
        "head of", "directeur adjoint", "directrice adjointe",
        "deputy director", "senior manager", "manager senior",
        "chef de division", "chef division", "chef de projet senior",
        "senior project manager", "responsable pôle", "responsable pole",
        "business unit manager", "head of department",
    ],
    HierarchyLevel.DIRECTION: [
        "directeur général", "directrice générale", "dg", "ceo",
        "directeur", "directrice", "president", "président",
        "vice-président", "vice president", "vp", "c-level",
        "chief", "comex", "codir", "board", "managing director",
        "executive director", "directeur exécutif", "pdg",
        "secrétaire général", "secretaire general",
    ],
}

# =============================================================================
# 3. Profils de scoring par niveau hiérarchique
# =============================================================================

@dataclass(frozen=True)
class HierarchyProfile:
    level: HierarchyLevel
    w_experience: float = 0.25
    w_education: float = 0.12
    w_certifications: float = 0.08
    w_semantic: float = 0.20
    w_keywords: float = 0.10
    w_leadership: float = 0.05
    w_language: float = 0.05
    w_complexity: float = 0.10
    w_penalty: float = 0.05
    min_years_experience: float = 0
    min_education_level: str = "none"
    require_certifications: bool = False
    require_leadership: bool = False
    complexity_multiplier: float = 1.0


HIERARCHY_PROFILES: Dict[HierarchyLevel, HierarchyProfile] = {
    HierarchyLevel.COLLABORATEUR: HierarchyProfile(
        level=HierarchyLevel.COLLABORATEUR,
        w_experience=0.20, w_education=0.15, w_certifications=0.10,
        w_semantic=0.15, w_keywords=0.15, w_leadership=0.00,
        w_language=0.05, w_complexity=0.10, w_penalty=0.10,
        min_years_experience=0,
        min_education_level="cap_bep",
        require_certifications=False,
        require_leadership=False,
        complexity_multiplier=0.8,
    ),
    HierarchyLevel.MANAGER_INTERMEDIAIRE: HierarchyProfile(
        level=HierarchyLevel.MANAGER_INTERMEDIAIRE,
        w_experience=0.22, w_education=0.12, w_certifications=0.08,
        w_semantic=0.18, w_keywords=0.12, w_leadership=0.10,
        w_language=0.05, w_complexity=0.08, w_penalty=0.05,
        min_years_experience=3,
        min_education_level="bac",
        require_certifications=False,
        require_leadership=True,
        complexity_multiplier=1.0,
    ),
    HierarchyLevel.MANAGER_SENIOR: HierarchyProfile(
        level=HierarchyLevel.MANAGER_SENIOR,
        w_experience=0.25, w_education=0.10, w_certifications=0.08,
        w_semantic=0.15, w_keywords=0.08, w_leadership=0.15,
        w_language=0.07, w_complexity=0.07, w_penalty=0.05,
        min_years_experience=7,
        min_education_level="bac+3_licence",
        require_certifications=True,
        require_leadership=True,
        complexity_multiplier=1.2,
    ),
    HierarchyLevel.DIRECTION: HierarchyProfile(
        level=HierarchyLevel.DIRECTION,
        w_experience=0.20, w_education=0.10, w_certifications=0.05,
        w_semantic=0.12, w_keywords=0.05, w_leadership=0.25,
        w_language=0.10, w_complexity=0.08, w_penalty=0.05,
        min_years_experience=10,
        min_education_level="bac+5_master",
        require_certifications=False,
        require_leadership=True,
        complexity_multiplier=1.5,
    ),
}

# =============================================================================
# 4. Indicateurs de complexité par domaine
# =============================================================================

DOMAIN_COMPLEXITY: Dict[Domain, float] = {
    Domain.TECH: 1.2, Domain.LEGAL: 1.5, Domain.HEALTH: 1.4,
    Domain.HR: 1.0, Domain.FINANCE: 1.3, Domain.MARKETING: 0.9,
    Domain.SALES: 0.8, Domain.EDUCATION: 1.0, Domain.AGRICULTURE: 1.3,
    Domain.CONSTRUCTION: 1.4, Domain.LOGISTICS: 1.0, Domain.TELECOM: 1.2,
    Domain.ENERGY: 1.5, Domain.MINING: 1.6, Domain.HOSPITALITY: 0.7,
    Domain.MEDIA: 0.9, Domain.INSURANCE: 1.2, Domain.REAL_ESTATE: 1.1,
    Domain.CONSULTING: 1.3, Domain.PUBLIC_ADMIN: 1.0, Domain.NGO: 0.9,
    Domain.PHARMA: 1.5, Domain.RETAIL: 0.7, Domain.TRANSPORT: 1.0,
    Domain.ENVIRONMENT: 1.2, Domain.CRAFTSMANSHIP: 1.1, Domain.SECURITY: 0.8,
}

# =============================================================================
# 5. Dictionnaires de compétences par domaine
# =============================================================================

DOMAIN_SKILLS: Dict[Domain, List[str]] = {
    Domain.TECH: ["python", "java", "sql", "cloud", "aws", "azure", "devops",
                   "api", "docker", "kubernetes", "git", "agile", "scrum",
                   "architecture", "microservices", "ci/cd", "linux"],
    Domain.LEGAL: ["droit", "contrat", "contentieux", "ohada", "conformité",
                    "compliance", "rgpd", "propriété intellectuelle", "arbitrage",
                    "médiation", "due diligence", "fusion", "acquisition"],
    Domain.HEALTH: ["médecine", "soins", "patient", "diagnostic", "chirurgie",
                     "pharmacie", "infirmier", "santé publique", "épidémiologie"],
    Domain.HR: ["recrutement", "formation", "gpec", "paie", "administration",
                "relations sociales", "dialogue social", "sirh", "talent",
                "onboarding", "assessment", "people"],
    Domain.FINANCE: ["comptabilité", "audit", "contrôle de gestion", "trésorerie",
                      "ifrs", "fiscalité", "reporting", "budget", "forecast",
                      "consolidation", "clôture", "p&l", "balance sheet"],
    Domain.MARKETING: ["digital", "branding", "seo", "sea", "content", "social media",
                        "campagne", "études", "crm", "acquisition", "fidélisation"],
    Domain.SALES: ["négociation", "prospection", "portefeuille", "pipeline",
                    "key account", "business development", "b2b", "b2c", "closing"],
    Domain.EDUCATION: ["pédagogie", "formation", "enseignement", "programme",
                        "évaluation", "andragogie", "elearning", "campus"],
    Domain.AGRICULTURE: ["agronomie", "culture", "élevage", "irrigation",
                          "haccp", "sécurité alimentaire", "agriculture durable",
                          "filière", "coopérative", "certification bio"],
    Domain.CONSTRUCTION: ["btp", "gros œuvre", "second œuvre", "bim", "bâtiment",
                           "travaux publics", "génie civil", "chantier", "topographie"],
    Domain.LOGISTICS: ["supply chain", "transport", "entrepôt", "stock",
                        "inventaire", "douane", "incoterms", "fret", "flux"],
    Domain.TELECOM: ["réseau", "fibre", "télécommunication", "antenne",
                      "5g", "ftth", "opérateur", "spectre", "datacenter"],
    Domain.ENERGY: ["électricité", "renouvelable", "solaire", "éolien",
                     "hydroélectrique", "réseau électrique", "maintenance"],
    Domain.MINING: ["mine", "extraction", "géologie", "minerai", "carrière",
                     "forage", "explosif", "traitement", "exploration"],
    Domain.HOSPITALITY: ["hôtellerie", "restauration", "accueil", "service",
                          "tourisme", "réservation", "hébergement"],
    Domain.MEDIA: ["journalisme", "rédaction", "production", "audiovisuel",
                    "édition", "broadcast", "streaming"],
    Domain.INSURANCE: ["assurance", "sinistre", "souscription", "actuariat",
                        "risque", "réassurance", "courtage", "prévoyance"],
    Domain.REAL_ESTATE: ["immobilier", "promotion", "transaction", "gestion",
                          "copropriété", "foncier", "syndic"],
    Domain.CONSULTING: ["conseil", "diagnostic", "stratégie", "transformation",
                         "audit", "mission", "recommandation"],
    Domain.PUBLIC_ADMIN: ["administration", "marché public", "service public",
                           "collectivité", "préfecture", "guichet"],
    Domain.NGO: ["humanitaire", "développement", "plaidoyer", "bailleur",
                  "subvention", "bénéficiaire", "terrain"],
    Domain.PHARMA: ["médicament", "essai clinique", "réglementaire", "amm",
                     "laboratoire", "bp", "biotech", "galénique"],
    Domain.RETAIL: ["distribution", "magasin", "rayon", "caisse", "merchandising",
                     "grande surface", "franchise", "click and collect"],
    Domain.TRANSPORT: ["logistique transport", "flotte", "routier", "maritime",
                        "aérien", "ferroviaire", "passager", "marchandise"],
    Domain.ENVIRONMENT: ["environnement", "développement durable", "rse",
                          "carbone", "bilan", "recyclage", "biodiversité"],
    Domain.CRAFTSMANSHIP: ["artisanat", "métier", "fabrication", "manuel",
                            "atelier", "savoir-faire", "compagnon"],
    Domain.SECURITY: ["sécurité", "sûreté", "gardiennage", "surveillance",
                       "télésurveillance", "contrôle d'accès", "prévention"],
}

# =============================================================================
# 6. Niveaux d'éducation
# =============================================================================

EDUCATION_LEVEL_ORDER: List[str] = [
    "none", "cap_bep", "bac", "bac+2_bts_dut", "bac+3_licence",
    "bac+4_maitrise", "bac+5_master", "bac+8_doctorat",
]

EDUCATION_MARKERS: Dict[str, List[str]] = {
    "cap_bep": ["cap", "bep", "bt", "brevet de technicien", "certificat d'aptitude"],
    "bac": ["baccalauréat", "bac", "baccalaureate", "high school diploma", "a level"],
    "bac+2_bts_dut": ["bts", "dut", "deug", "deust", "associate degree", "hnd"],
    "bac+3_licence": ["licence", "bachelor", "baccaleaureat", "ba ", "bsc", "b.a.", "b.s.", "llb"],
    "bac+4_maitrise": ["maîtrise", "maitrise", "master 1", "m1", "pgd", "postgraduate diploma"],
    "bac+5_master": ["master", "master 2", "m2", "msc", "mba", "ingénieur", "ingenieur",
                      "diplôme d'ingénieur", "grande école", "dsc", "llm"],
    "bac+8_doctorat": ["doctorat", "phd", "ph.d", "doctor", "docteur", "thèse"],
}

# =============================================================================
# 7. Certifications reconnues
# =============================================================================

CERTIFICATION_REGISTRY: Dict[str, Dict[str, Any]] = {
    "aws": {"name": "AWS Certification", "domain": Domain.TECH, "level": 3, "weight": 1.0,
             "aliases": ["amazon web services", "aws certified", "aws solutions architect"]},
    "azure": {"name": "Microsoft Azure", "domain": Domain.TECH, "level": 3, "weight": 1.0,
               "aliases": ["microsoft azure", "azure certified", "az-104", "az-204", "az-305", "az-400", "az-500", "az-900"]},
    "gcp": {"name": "Google Cloud", "domain": Domain.TECH, "level": 3, "weight": 0.9,
             "aliases": ["google cloud", "gcp certified", "google cloud platform"]},
    "cisco": {"name": "Cisco (CCNA/CCNP)", "domain": Domain.TECH, "level": 3, "weight": 1.0,
               "aliases": ["ccna", "ccnp", "ccie", "cisco certified"]},
    "comptia": {"name": "CompTIA", "domain": Domain.TECH, "level": 2, "weight": 0.8,
                 "aliases": ["comptia a+", "comptia network+", "comptia security+", "a+", "network+", "security+"]},
    "pmp": {"name": "Project Management Professional (PMP)", "domain": Domain.CONSULTING, "level": 4, "weight": 1.2,
             "aliases": ["project management professional", "pmi", "pmp certifie", "certified pmp"]},
    "prince2": {"name": "PRINCE2", "domain": Domain.CONSULTING, "level": 3, "weight": 1.0,
                 "aliases": ["prince 2", "prince2 practitioner", "prince2 foundation"]},
    "scrum": {"name": "Scrum Master / Product Owner", "domain": Domain.TECH, "level": 2, "weight": 0.7,
               "aliases": ["scrum master", "product owner", "psm", "cspo", "safe", "agiliste"]},
    "itil": {"name": "ITIL", "domain": Domain.TECH, "level": 3, "weight": 0.8,
              "aliases": ["itil v3", "itil v4", "itil foundation"]},
    "iso 9001": {"name": "ISO 9001 Quality Management", "domain": Domain.CONSULTING, "level": 3, "weight": 1.0,
                  "aliases": ["iso9001", "iso 9001", "qualite iso", "management qualite", "smq"]},
    "iso 14001": {"name": "ISO 14001 Environmental", "domain": Domain.ENVIRONMENT, "level": 3, "weight": 1.0,
                   "aliases": ["iso14001", "management environnemental", "sme"]},
    "iso 45001": {"name": "ISO 45001 OHS", "domain": Domain.SECURITY, "level": 3, "weight": 1.0,
                   "aliases": ["iso45001", "sante securite au travail", "ohsas 18001", "sst"]},
    "iso 22000": {"name": "ISO 22000 Food Safety", "domain": Domain.AGRICULTURE, "level": 3, "weight": 1.0,
                   "aliases": ["iso22000", "securite alimentaire iso", "fsms"]},
    "haccp": {"name": "HACCP", "domain": Domain.AGRICULTURE, "level": 3, "weight": 1.0,
               "aliases": ["haccp", "hazard analysis", "analyse des dangers"]},
    "ohada": {"name": "OHADA", "domain": Domain.LEGAL, "level": 4, "weight": 1.5,
               "aliases": ["ohada", "droit ohada", "acte uniforme"]},
    "ifrs": {"name": "IFRS Certification", "domain": Domain.FINANCE, "level": 4, "weight": 1.3,
              "aliases": ["ifrs", "normes ifrs", "international financial reporting", "ias/ifrs"]},
    "sirh": {"name": "SIRH Certification", "domain": Domain.HR, "level": 3, "weight": 1.0,
              "aliases": ["sirh", "systeme d'information rh", "logiciel rh", "hrms", "hr information system"]},
    "acca": {"name": "ACCA", "domain": Domain.FINANCE, "level": 4, "weight": 1.3,
              "aliases": ["acca", "association of chartered certified"]},
    "cima": {"name": "CIMA", "domain": Domain.FINANCE, "level": 4, "weight": 1.2,
              "aliases": ["cima", "chartered institute of management"]},
    "cfa": {"name": "CFA", "domain": Domain.FINANCE, "level": 5, "weight": 1.5,
             "aliases": ["cfa", "chartered financial analyst"]},
    "cpa": {"name": "CPA", "domain": Domain.FINANCE, "level": 4, "weight": 1.3,
             "aliases": ["cpa", "certified public accountant", "expert-comptable", "expertise comptable",
                         "dpeco", "dscg", "dsc", "decof"]},
    "toeic": {"name": "TOEIC", "domain": Domain.EDUCATION, "level": 1, "weight": 0.5,
               "aliases": ["toeic", "test of english for international"]},
    "toefl": {"name": "TOEFL", "domain": Domain.EDUCATION, "level": 1, "weight": 0.5,
               "aliases": ["toefl", "test of english as a foreign"]},
    "ielts": {"name": "IELTS", "domain": Domain.EDUCATION, "level": 1, "weight": 0.5,
               "aliases": ["ielts", "international english language testing"]},
    "delf": {"name": "DELF/DALF", "domain": Domain.EDUCATION, "level": 1, "weight": 0.4,
              "aliases": ["delf", "dalf", "diplome d'etudes en langue", "diplome approfondi de langue"]},
}

# =============================================================================
# 8. Verbes d'action de leadership
# =============================================================================

LEADERSHIP_ACTION_VERBS: Dict[str, float] = {
    "dirigé": 1.0, "diriger": 0.9, "dirige": 1.0,
    "piloté": 1.0, "piloter": 0.9, "pilote": 1.0,
    "managé": 0.9, "manager": 0.8, "manage": 0.8,
    "supervisé": 0.8, "superviser": 0.7, "supervise": 0.8,
    "encadré": 0.8, "encadrer": 0.7, "encadre": 0.8,
    "coordonné": 0.7, "coordonner": 0.6, "coordonne": 0.7,
    "animé": 0.6, "animer": 0.5, "anime": 0.6,
    "conduit": 0.7, "conduire": 0.6,
    "initié": 0.7, "initier": 0.6,
    "transformé": 0.8, "transformer": 0.7,
    "restructuré": 0.8, "restructurer": 0.7,
    "développé": 0.5, "développer": 0.4,
    "fondé": 0.9, "fonder": 0.8,
    "créé": 0.6, "créer": 0.5,
    "led": 1.0, "lead": 1.0,
    "managed": 0.9, "oversaw": 0.9,
    "supervised": 0.8,
    "coordinated": 0.7, "orchestrated": 0.8,
    "headed": 0.9, "directed": 1.0,
    "spearheaded": 0.9, "championed": 0.8,
    "mentored": 0.6, "coached": 0.5,
    "empowered": 0.7, "built": 0.5,
    "established": 0.7, "founded": 0.9,
}

# =============================================================================
# 9. Système de pénalités de carence
# =============================================================================

@dataclass(frozen=True)
class DeficiencyPenalty:
    dimension: str
    threshold: float
    max_penalty: float
    penalty_curve: str = "linear"
    description: str = ""


PENALTY_SYSTEM: List[DeficiencyPenalty] = [
    DeficiencyPenalty("experience",     0.15, 0.40, "exponential", "Expérience critique insuffisante pour le poste"),
    DeficiencyPenalty("education",      0.10, 0.25, "step",        "Niveau d'éducation en dessous du seuil requis"),
    DeficiencyPenalty("certifications", 0.05, 0.15, "linear",      "Certifications obligatoires absentes"),
    DeficiencyPenalty("leadership",     0.10, 0.20, "linear",      "Leadership requis mais non démontré"),
    DeficiencyPenalty("language",       0.10, 0.10, "linear",      "Qualité linguistique insuffisante"),
    DeficiencyPenalty("complexity",     0.20, 0.30, "exponential", "Maîtrise insuffisante des compétences du domaine")
]


def compute_careness_penalty(
    dimension_scores: Dict[str, float],
    hierarchy_level: HierarchyLevel,
) -> Tuple[float, List[Dict[str, Any]]]:
    total_penalty = 0.0
    activated = []

    for pen in PENALTY_SYSTEM:
        score = dimension_scores.get(pen.dimension, 1.0)
        if score < pen.threshold:
            if pen.penalty_curve == "exponential":
                deficit = (pen.threshold - score) / pen.threshold
                penalty = pen.max_penalty * (1 - math.exp(-3 * deficit))
            elif pen.penalty_curve == "step":
                penalty = pen.max_penalty
            else:
                deficit = (pen.threshold - score) / pen.threshold
                penalty = pen.max_penalty * deficit

            total_penalty += penalty
            activated.append({
                "dimension":       pen.dimension,
                "score":           round(score, 3),
                "threshold":       pen.threshold,
                "penalty_applied": round(penalty, 3),
                "description":     pen.description,
            })

    return min(total_penalty, 0.40), activated


# =============================================================================
# 10. Détection de domaine
# =============================================================================

DOMAIN_TITLE_KEYWORDS: Dict[Domain, List[str]] = {
    Domain.TECH: ["développeur", "developpeur", "ingénieur logiciel", "software",
                   "devops", "data", "cybersécurité", "cybersecurite", "fullstack",
                   "backend", "frontend", "mobile", "cloud", "architecte", "sre"],
    Domain.FINANCE: ["comptable", "finance", "financier", "financière", "audit",
                      "trésorerie", "tresorerie", "contrôleur", "controleur",
                      "daf", "credit", "banque", "microfinance",
                      "fiscalité", "fiscalite"],
    Domain.HR: ["rh", "ressources humaines", "recrutement", "paie", "formation",
                 "gpec", "talent", "people", "human resources"],
    Domain.AGRICULTURE: ["agronome", "agricole", "agriculture", "agro",
                          "élevage", "elevage", "cultures", "plantation"],
    Domain.CONSTRUCTION: ["btp", "bâtiment", "batiment", "construction",
                           "génie civil", "genie civil", "chantier", "architecte"],
    Domain.HEALTH: ["médecin", "medecin", "infirmier", "pharmacien", "santé",
                     "sante", "clinique", "hôpital", "hopital", "soins"],
    Domain.LEGAL: ["juriste", "avocat", "legal", "juridique", "conformité",
                    "conformite", "compliance", "notaire"],
    Domain.EDUCATION: ["enseignant", "professeur", "formateur", "éducation",
                        "education", "pédagogie", "pedagogie", "école", "ecole"],
    Domain.LOGISTICS: ["logistique", "supply chain", "transport", "entrepôt",
                        "entrepot", "magasinier", "douane"],
    Domain.MARKETING: ["marketing", "communication", "digital", "brand",
                        "social media", "community manager"],
    Domain.SALES: ["commercial", "vente", "business developer", "kam",
                    "account manager", "sales"],
    Domain.TELECOM: ["télécom", "telecom", "réseau", "reseau", "fibre",
                      "opérateur télécom"],
    Domain.ENERGY: ["énergie", "energie", "électricien", "electricien",
                     "électrique", "electrique", "solaire", "éolien", "eolien"],
    Domain.MINING: ["mine", "minier", "géologue", "geologue", "extraction",
                     "forage", "carrière", "carriere"],
    Domain.HOSPITALITY: ["hôtel", "hotel", "restaurant", "tourisme", "accueil",
                          "réception", "reception", "hospitality"],
    Domain.MEDIA: ["journaliste", "journalism", "rédacteur", "redacteur",
                    "média", "media", "presse", "tv", "radio"],
    Domain.INSURANCE: ["assurance", "assureur", "actuaire", "sinistre",
                        "courtier", "insurance"],
    Domain.REAL_ESTATE: ["immobilier", "promoteur", "agent immobilier"],
    Domain.CONSULTING: ["consultant", "conseil", "cabinet", "auditeur"],
    Domain.PUBLIC_ADMIN: ["fonctionnaire", "administration", "préfet", "prefet"],
    Domain.NGO: ["ong", "humanitaire", "développement international"],
    Domain.PHARMA: ["pharmacien", "pharmaceutique", "médicament", "medicament"],
    Domain.RETAIL: ["vendeur", "caissier", "magasin", "grande distribution"],
    Domain.TRANSPORT: ["chauffeur", "conducteur", "routier", "maritime", "aérien"],
    Domain.ENVIRONMENT: ["environnement", "environnementaliste", "rse", "durable"],
    Domain.CRAFTSMANSHIP: ["artisan", "menuiserie", "plomberie", "électricien bâtiment"],
    Domain.SECURITY: ["agent de sécurité", "vigile", "gardiennage", "sûreté"],
}


def detect_domain(title_lower: str, description_lower: str = "") -> Domain:
    combined = f"{title_lower} {description_lower}"
    scores: Dict[Domain, int] = {}
    for domain, keywords in DOMAIN_TITLE_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in combined)
        if count > 0:
            scores[domain] = count
    return max(scores, key=scores.get) if scores else Domain.CONSULTING


# =============================================================================
# 11. Détection du niveau hiérarchique
# =============================================================================

def detect_hierarchy_level(title_lower: str) -> HierarchyLevel:
    for level in [HierarchyLevel.DIRECTION, HierarchyLevel.MANAGER_SENIOR,
                  HierarchyLevel.MANAGER_INTERMEDIAIRE]:
        for marker in HIERARCHY_TITLE_MARKERS[level]:
            if marker in title_lower:
                return level
    return HierarchyLevel.COLLABORATEUR


# =============================================================================
# 12. Détection du niveau d'éducation
# =============================================================================

def detect_education_level(education_text: str) -> str:
    text_lower = education_text.lower()
    best_level = "none"
    best_index = 0

    for level_key, markers in EDUCATION_MARKERS.items():
        for marker in markers:
            if marker in text_lower:
                try:
                    level_index = EDUCATION_LEVEL_ORDER.index(level_key)
                    if level_index > best_index:
                        best_index = level_index
                        best_level = level_key
                except ValueError:
                    pass
                break

    return best_level


# =============================================================================
# 13. Scoring de l'expérience
# =============================================================================

def compute_experience_score(
    cv_years: float,
    required_years: float,
    hierarchy_level: HierarchyLevel,
) -> Tuple[float, Dict[str, Any]]:
    profile = HIERARCHY_PROFILES[hierarchy_level]

    if required_years <= 0:
        ratio = min(cv_years / 5.0, 1.0) if cv_years > 0 else 0.0
    elif cv_years >= required_years:
        ratio = 1.0          # Requis atteint = score plein, sans bonus pour l'excédent
    else:
        ratio = cv_years / required_years

    if cv_years < profile.min_years_experience:
        ratio *= 0.5

    score = min(ratio, 1.0)
    return score, {
        "cv_years": cv_years,
        "required_years": required_years,
        "ratio": round(ratio, 3),
        "above_threshold": cv_years >= profile.min_years_experience,
    }


# =============================================================================
# 14. Scoring de l'éducation
# =============================================================================

def compute_education_score(
    cv_education_level: str,
    hierarchy_level: HierarchyLevel,
) -> Tuple[float, Dict[str, Any]]:
    profile = HIERARCHY_PROFILES[hierarchy_level]

    try:
        cv_index = EDUCATION_LEVEL_ORDER.index(cv_education_level)
    except ValueError:
        cv_index = 0

    try:
        req_index = EDUCATION_LEVEL_ORDER.index(profile.min_education_level)
    except ValueError:
        req_index = 0

    if req_index == 0:
        score = min(cv_index / 4.0, 1.0)
        meets_requirement = True
    elif cv_index >= req_index + 2:
        score = 1.0
        meets_requirement = True
    elif cv_index >= req_index:
        score = 0.7 + 0.3 * (cv_index - req_index)
        meets_requirement = True
    elif cv_index >= req_index - 1:
        score = 0.4
        meets_requirement = False
    else:
        score = max(cv_index / req_index * 0.3, 0.05)
        meets_requirement = False

    return round(score, 3), {
        "cv_level": cv_education_level,
        "required_level": profile.min_education_level,
        "meets_requirement": meets_requirement,
    }


# =============================================================================
# 15. Scoring du leadership
# =============================================================================

def compute_leadership_score(
    cv_text: str,
    hierarchy_level: HierarchyLevel,
    past_titles: Optional[List[str]] = None,
) -> Tuple[float, Dict[str, Any]]:
    profile = HIERARCHY_PROFILES[hierarchy_level]

    if not profile.require_leadership:
        return 1.0, {"leadership_required": False, "score": 1.0}

    text_lower = cv_text.lower()

    verb_scores = [w for v, w in LEADERSHIP_ACTION_VERBS.items() if v in text_lower]
    verb_score = max(verb_scores) if verb_scores else 0.0
    if len(verb_scores) >= 3:
        verb_score = min(verb_score + 0.1, 1.0)

    title_score = 0.0
    if past_titles:
        for title in past_titles:
            detected = detect_hierarchy_level(title.lower())
            if detected in [HierarchyLevel.MANAGER_SENIOR, HierarchyLevel.DIRECTION]:
                title_score = max(title_score, 0.8)
            elif detected == HierarchyLevel.MANAGER_INTERMEDIAIRE:
                title_score = max(title_score, 0.5)

    combined = round(min(0.6 * verb_score + 0.4 * title_score, 1.0), 3)
    return combined, {
        "leadership_required": True,
        "verb_score":  round(verb_score, 3),
        "title_score": round(title_score, 3),
        "combined":    combined,
        "verb_count":  len(verb_scores),
    }


# =============================================================================
# 16. Scoring de complexité
# =============================================================================

def compute_complexity_score(
    cv_text: str,
    domain: Domain,
    hierarchy_level: HierarchyLevel,
) -> Tuple[float, Dict[str, Any]]:
    profile = HIERARCHY_PROFILES[hierarchy_level]
    text_norm = normalize_text(cv_text)

    domains_touched = sum(
        1 for d, skills in DOMAIN_SKILLS.items()
        if any(normalize_text(s) in text_norm for s in skills[:4])
    )
    diversity_score = min(domains_touched / 5.0, 1.0)
    adjusted = diversity_score * profile.complexity_multiplier

    primary_skills = DOMAIN_SKILLS.get(domain, [])
    if primary_skills:
        primary_norm = [normalize_text(s) for s in primary_skills]
        primary_coverage = sum(1 for s in primary_norm if s in text_norm) / len(primary_norm)
        adjusted = 0.6 * adjusted + 0.4 * min(primary_coverage, 1.0)

    return round(min(adjusted, 1.0), 3), {
        "domains_touched": domains_touched,
        "diversity_score": round(diversity_score, 3),
        "complexity_multiplier": profile.complexity_multiplier,
    }


# =============================================================================
# 17. Scoring des certifications
# =============================================================================

def compute_certification_score(
    cv_text: str,
    domain: Domain,
    hierarchy_level: HierarchyLevel,
) -> Tuple[float, Dict[str, Any]]:
    profile = HIERARCHY_PROFILES[hierarchy_level]
    text_norm = normalize_text(cv_text)
    found_certs = []
    total_weight = 0.0
    max_possible = 3.0

    for cert_key, cert_info in CERTIFICATION_REGISTRY.items():
        all_terms = [normalize_text(cert_key)] + [normalize_text(a) for a in cert_info.get("aliases", [])]
        if any(term in text_norm for term in all_terms):
            found_certs.append(cert_info["name"])
            weight = cert_info["weight"]
            if cert_info["domain"] == domain:
                weight *= 1.3
            if cert_info["level"] >= 4 and hierarchy_level in [
                HierarchyLevel.MANAGER_SENIOR, HierarchyLevel.DIRECTION
            ]:
                weight *= 1.2
            total_weight += weight

    score = round(min(total_weight / max_possible, 1.0), 3)
    if profile.require_certifications and not found_certs:
        score = 0.05

    return score, {
        "found_certifications": found_certs,
        "count": len(found_certs),
        "total_weight": round(total_weight, 3),
    }


# =============================================================================
# 18. Scoring sémantique
# =============================================================================

def compute_semantic_score(
    cv_text: str,
    job_description: str,
    domain: Domain,
) -> Tuple[float, Dict[str, Any]]:
    cv_norm = normalize_text(cv_text)
    jd_norm = normalize_text(job_description)

    cv_words = set(re.findall(r'\b\w+\b', cv_norm))
    jd_words = set(re.findall(r'\b\w+\b', jd_norm))

    if not jd_words:
        return 0.5, {"method": "fallback_lexical", "note": "JD vide"}

    intersection = cv_words & jd_words
    union = cv_words | jd_words
    jaccard = len(intersection) / len(union) if union else 0.0

    domain_skills_normalized = {normalize_text(s) for s in DOMAIN_SKILLS.get(domain, [])}
    skill_matches = intersection & domain_skills_normalized
    skill_ratio = len(skill_matches) / len(domain_skills_normalized) if domain_skills_normalized else 0.0

    score = round(0.4 * jaccard + 0.6 * skill_ratio, 3)
    return score, {
        "method": "fallback_lexical",
        "jaccard": round(jaccard, 3),
        "skill_match_ratio": round(skill_ratio, 3),
        "matched_skills": list(skill_matches)[:10],
    }


# =============================================================================
# 19. Scoring par mots-clés
# =============================================================================

def compute_keyword_score(
    cv_text: str,
    required_keywords: List[str],
    domain: Domain,
) -> Tuple[float, Dict[str, Any]]:
    text_norm = normalize_text(cv_text)
    domain_skills_norm = [normalize_text(s) for s in DOMAIN_SKILLS.get(domain, [])]
    required_norm = [normalize_text(kw) for kw in required_keywords]

    if required_keywords:
        all_keywords = required_norm
        denominator = max(len(all_keywords), 1)
    else:
        all_keywords = list(set(domain_skills_norm))
        denominator = min(len(all_keywords), 12)

    if not all_keywords:
        return 0.5, {"method": "no_keywords", "note": "Aucun mot-clé configuré"}

    matched = [kw for kw in all_keywords if kw in text_norm]
    ratio = len(matched) / denominator
    score = round(min(ratio * 1.5, 1.0), 3)

    return score, {
        "total_keywords": len(all_keywords),
        "denominator_used": denominator,
        "matched": len(matched),
        "matched_keywords": matched[:15],
        "ratio": round(ratio, 3),
    }


# =============================================================================
# 20. Scoring de la qualité linguistique
# =============================================================================

def compute_language_quality_score(
    cv_text: str,
    target_languages: Optional[List[str]] = None,
) -> Tuple[float, Dict[str, Any]]:
    if target_languages is None:
        target_languages = ["fr", "en"]

    text_lower = cv_text.lower()
    if len(cv_text) < 50:
        return 0.3, {"error": "Texte trop court"}

    fr_markers = ["le ", "la ", "les ", "des ", "une ", "un ", "est ", "dans ",
                   "pour ", "avec ", "sur ", "sous ", "chez ", "je ", "nous ",
                   "expérience", "formation", "compétences", "entreprise"]
    en_markers = ["the ", "and ", "with ", "for ", "from ", "have ", "has ",
                   "experience", "education", "skills", "company", "worked"]

    fr_count = sum(1 for m in fr_markers if m in text_lower)
    en_count = sum(1 for m in en_markers if m in text_lower)
    detected_lang = "fr" if fr_count > en_count else ("en" if en_count > fr_count else "mixed")

    words = re.findall(r'\b\w{3,}\b', text_lower)
    unique_words = set(words)
    lexical_richness = len(unique_words) / len(words) if words else 0.0

    structure_markers = ["expérience", "experience", "formation", "education",
                          "compétences", "skills", "langues", "languages",
                          "certifications", "références", "references"]
    structure_score = sum(1 for m in structure_markers if m in text_lower) / len(structure_markers)
    length_score = min(len(words) / 200, 1.0)

    score = round(0.3 * lexical_richness + 0.3 * structure_score + 0.2 * length_score + 0.2, 3)
    return score, {
        "detected_language": detected_lang,
        "lexical_richness":  round(lexical_richness, 3),
        "structure_score":   round(structure_score, 3),
        "word_count":        len(words),
        "unique_words":      len(unique_words),
    }


# =============================================================================
# 21. CandidateScore dataclass
# =============================================================================

@dataclass
class CandidateScore:
    candidate_id: str
    job_title: str
    hierarchy_level: HierarchyLevel
    domain: Domain
    profile: HierarchyProfile
    score_experience: float = 0.0
    score_education: float = 0.0
    score_certifications: float = 0.0
    score_semantic: float = 0.0
    score_keywords: float = 0.0
    score_leadership: float = 0.0
    score_language: float = 0.0
    score_complexity: float = 0.0
    penalty: float = 0.0
    penalty_details: List[Dict[str, Any]] = field(default_factory=list)
    final_score: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    detected_education: str = "none"
    detected_language: str = "unknown"
    past_titles: List[str] = field(default_factory=list)


# =============================================================================
# 22. Fonction principale de scoring
# =============================================================================

def score_candidate(
    candidate_id: str,
    cv_text: str,
    job_title: str,
    job_description: str,
    required_years_experience: float = 0,
    required_keywords: Optional[List[str]] = None,
    past_titles: Optional[List[str]] = None,
    target_languages: Optional[List[str]] = None,
    cv_years_hint: float = 0,
) -> CandidateScore:
    if required_keywords is None:
        required_keywords = []
    if past_titles is None:
        past_titles = []
    if target_languages is None:
        target_languages = ["fr", "en"]

    title_lower = job_title.lower()
    jd_lower = job_description.lower()
    cv_lower = cv_text.lower()

    hierarchy_level = detect_hierarchy_level(title_lower)
    domain = detect_domain(title_lower, jd_lower)
    profile = HIERARCHY_PROFILES[hierarchy_level]
    detected_education = detect_education_level(cv_text)

    years_pattern = re.findall(
        r'(\d+)\s*(?:\+)?\s*(?:ans?|années?|years?)(?:\s+d[\'\"](?:expérience|experience))?',
        cv_lower,
    )
    cv_years_from_text = max([int(y) for y in years_pattern]) if years_pattern else 0.0
    # Use structured hint (from ai_extracted experience_years) when regex finds nothing.
    # This covers cases where raw_text was not stored and only a reconstructed text
    # fragment (job titles only) is available.
    cv_years = max(cv_years_from_text, cv_years_hint)

    exp_score,  exp_details  = compute_experience_score(cv_years, required_years_experience, hierarchy_level)
    edu_score,  edu_details  = compute_education_score(detected_education, hierarchy_level)
    cert_score, cert_details = compute_certification_score(cv_text, domain, hierarchy_level)
    sem_score,  sem_details  = compute_semantic_score(cv_text, job_description, domain)
    kw_score,   kw_details   = compute_keyword_score(cv_text, required_keywords, domain)
    lead_score, lead_details = compute_leadership_score(cv_text, hierarchy_level, past_titles)
    lang_score, lang_details = compute_language_quality_score(cv_text, target_languages)
    comp_score, comp_details = compute_complexity_score(cv_text, domain, hierarchy_level)

    weighted = (
        profile.w_experience     * exp_score  +
        profile.w_education      * edu_score  +
        profile.w_certifications * cert_score +
        profile.w_semantic       * sem_score  +
        profile.w_keywords       * kw_score   +
        profile.w_leadership     * lead_score +
        profile.w_language       * lang_score +
        profile.w_complexity     * comp_score
    )

    dimension_scores_for_penalty = {
        "experience":     exp_score,
        "education":      edu_score,
        "certifications": cert_score,
        "leadership":     lead_score,
        "language":       lang_score,
    }
    penalty, penalty_details = compute_careness_penalty(dimension_scores_for_penalty, hierarchy_level)

    raw_final = weighted - penalty + profile.w_penalty * (1.0 - penalty)
    final_score = round(max(0.0, min(raw_final, 1.0)), 4)

    return CandidateScore(
        candidate_id=candidate_id,
        job_title=job_title,
        hierarchy_level=hierarchy_level,
        domain=domain,
        profile=profile,
        score_experience=round(exp_score, 3),
        score_education=round(edu_score, 3),
        score_certifications=round(cert_score, 3),
        score_semantic=round(sem_score, 3),
        score_keywords=round(kw_score, 3),
        score_leadership=round(lead_score, 3),
        score_language=round(lang_score, 3),
        score_complexity=round(comp_score, 3),
        penalty=round(penalty, 3),
        penalty_details=penalty_details,
        final_score=final_score,
        details={
            "experience":         exp_details,
            "education":          edu_details,
            "certifications":     cert_details,
            "semantic":           sem_details,
            "keywords":           kw_details,
            "leadership":         lead_details,
            "language":           lang_details,
            "complexity":         comp_details,
            "cv_years_detected":  cv_years,
        },
        detected_education=detected_education,
        detected_language=lang_details.get("detected_language", "unknown"),
        past_titles=past_titles,
    )


# =============================================================================
# 23. Conversion en dictionnaire
# =============================================================================

def score_to_dict(score: CandidateScore) -> Dict[str, Any]:
    return {
        "candidate_id":    score.candidate_id,
        "job_title":       score.job_title,
        "hierarchy_level": score.hierarchy_level.value,
        "domain":          score.domain.value,
        "final_score":     score.final_score,
        "dimensions": {
            "experience":     score.score_experience,
            "education":      score.score_education,
            "certifications": score.score_certifications,
            "semantic":       score.score_semantic,
            "keywords":       score.score_keywords,
            "leadership":     score.score_leadership,
            "language":       score.score_language,
            "complexity":     score.score_complexity,
        },
        "weights": {
            "w_experience":     score.profile.w_experience,
            "w_education":      score.profile.w_education,
            "w_certifications": score.profile.w_certifications,
            "w_semantic":       score.profile.w_semantic,
            "w_keywords":       score.profile.w_keywords,
            "w_leadership":     score.profile.w_leadership,
            "w_language":       score.profile.w_language,
            "w_complexity":     score.profile.w_complexity,
            "w_penalty":        score.profile.w_penalty,
        },
        "penalty":           score.penalty,
        "penalty_details":   score.penalty_details,
        "detected_education": score.detected_education,
        "detected_language": score.detected_language,
        "details":           score.details,
    }


# =============================================================================
# 24. Feedback et apprentissage
# =============================================================================

@dataclass
class FeedbackRecord:
    candidate_id: str
    job_title: str
    predicted_score: float
    actual_outcome: str
    actual_rating: float
    timestamp: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# Weight vector for compute_intelligent_score's score_breakdown.
#
# These 6 keys (skill_match, experience, project_complexity, seniority,
# domain_diversity, career_progression) correspond EXACTLY to the dimensions
# produced by intelligent_scoring_service.compute_intelligent_score and shown
# in the Analytics radar chart / ScoreDetailModal. This is the weight space
# that the recruiter feedback loop (feedback.py) reads and writes via
# app_config.ats_weights.
#
# The previous DEFAULT_WEIGHTS (8 keys: experience, education, certifications,
# semantic, keywords, leadership, language, complexity) belonged to the
# hierarchical scorer (score_candidate / HIERARCHY_PROFILES) and were never
# consumed by compute_intelligent_score — feedback written under that schema
# had no effect on candidate scoring. DEFAULT_WEIGHTS is kept below as a
# backwards-compat alias pointing at the new (correct) weight space.
# ---------------------------------------------------------------------------
INTELLIGENT_SCORE_DEFAULT_WEIGHTS: Dict[str, float] = {
    "skill_match":        0.35,
    "experience":         0.20,
    "project_complexity": 0.15,
    "seniority":          0.10,
    "domain_diversity":   0.10,
    "career_progression": 0.10,
}

# Backwards-compat alias (old name kept in case other modules import it)
DEFAULT_WEIGHTS = INTELLIGENT_SCORE_DEFAULT_WEIGHTS


def update_weights_from_feedback(
    current_weights: Dict[str, float],
    feedback_records: List[FeedbackRecord],
    learning_rate: float = 0.01,
) -> Dict[str, float]:
    if not feedback_records:
        return current_weights

    new_weights = dict(current_weights)
    total_error = 0.0

    for fb in feedback_records:
        error = fb.actual_rating - fb.predicted_score
        total_error += abs(error)
        for dim in new_weights:
            gradient = -2 * error * new_weights[dim]
            new_weights[dim] -= learning_rate * gradient

    total = sum(new_weights.values())
    if total > 0:
        new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}

    logger.info(
        "Weights updated from %d feedbacks, mean_abs_error=%.4f",
        len(feedback_records),
        total_error / len(feedback_records),
    )
    return new_weights


# =============================================================================
# 25. Batch utilities
# =============================================================================

def batch_score(
    candidates: List[Tuple[str, str]],
    job_title: str,
    job_description: str,
    required_years: float = 0,
    required_keywords: Optional[List[str]] = None,
) -> List[CandidateScore]:
    results = []
    for candidate_id, cv_text in candidates:
        try:
            results.append(score_candidate(
                candidate_id=candidate_id,
                cv_text=cv_text,
                job_title=job_title,
                job_description=job_description,
                required_years_experience=required_years,
                required_keywords=required_keywords,
            ))
        except Exception as exc:
            logger.error("Scoring failed for %s: %s", candidate_id, exc)
            results.append(CandidateScore(
                candidate_id=candidate_id,
                job_title=job_title,
                hierarchy_level=HierarchyLevel.COLLABORATEUR,
                domain=Domain.CONSULTING,
                profile=HIERARCHY_PROFILES[HierarchyLevel.COLLABORATEUR],
                final_score=0.0,
                details={"error": str(exc)},
            ))
    return results


def rank_candidates(scores: List[CandidateScore]) -> List[CandidateScore]:
    return sorted(scores, key=lambda s: s.final_score, reverse=True)


# =============================================================================
# COMPATIBILITY LAYER
# =============================================================================

# Quality dampening constants (applied in quality-fallback mode from drive_sync)
_KW_DAMPEN  = 0.85
_KW_CAP     = 85.0
_SEM_DAMPEN = 0.80
_SEM_CAP    = 75.0


def _build_cv_text(cv_data: dict) -> str:
    """
    Build a single text blob from a structured CV dict.
    Used as fallback when raw_text / full_text are absent (e.g. API re-score
    where cv_raw_text was not loaded). Includes skills, education, and languages
    so that keyword/semantic/certification scorers have something to work with.
    """
    if not isinstance(cv_data, dict):
        return str(cv_data)
    parts = []
    if cv_data.get("summary"):
        parts.append(cv_data["summary"])
    if cv_data.get("current_position") or cv_data.get("title"):
        parts.append(cv_data.get("current_position") or cv_data.get("title", ""))
    if cv_data.get("full_name"):
        parts.append(cv_data["full_name"])
    # Skills — most keyword-dense field
    skills = cv_data.get("skills", [])
    if skills:
        parts.append(" ".join(str(s) for s in skills))
    # Work history — title + description
    for exp in cv_data.get("work_history", []):
        parts.append(exp.get("title", ""))
        parts.append(exp.get("description", ""))
        parts.append(exp.get("company", ""))
    # Education — degree names matter for education scorer
    for edu in cv_data.get("education", []):
        if isinstance(edu, dict):
            parts.append(edu.get("degree", ""))
            parts.append(edu.get("institution", ""))
            parts.append(edu.get("field", ""))
        else:
            parts.append(str(edu))
    # Projects
    for proj in cv_data.get("projects", []):
        parts.append(proj.get("name", ""))
        parts.append(proj.get("description", ""))
    # Certifications
    for cert in cv_data.get("certifications", []):
        parts.append(str(cert))
    # Languages
    for lang in cv_data.get("languages", []):
        parts.append(str(lang))
    return " ".join(filter(None, parts))

def enrich_cv_data(cv_info: dict, raw_text: str) -> dict:
    """
    Injects raw_text into cv_data so compute_candidate_score has the full CV
    body for scoring. Without this, keyword/semantic/education/certification
    scorers receive empty text (or the sparse _build_cv_text reconstruction)
    and return artificially low/zero scores.

    Canonical home for this helper — cv_processing.py and drive_sync.py both
    import from here to avoid the divergence that caused Drive-synced
    candidates to score off thin text (see backfill_now.py).
    """
    enriched = dict(cv_info)
    enriched["raw_text"] = raw_text
    return enriched


def compute_candidate_score(
    cv_data: Dict[str, Any],
    job_title: str,
    job_requirements: str,
    supabase: Any = None,          # accepted, ignored — kept for call-site compat
) -> Dict[str, Any]:
    """
    Compatibility shim expected by ai_service.py, cv_processing.py, and drive_sync.py.
    Wraps the rich hierarchical scorer. Returns a dict on 0–100 scale with both
    canonical v2.0 dimension keys AND the frontend aliases ScorePanel.jsx expects.
    """
    if isinstance(cv_data, dict):
        cv_text = cv_data.get("raw_text") or cv_data.get("full_text") or _build_cv_text(cv_data)
    else:
        cv_text = str(cv_data)

    # Extract experience_years from structured data for the hint
    _exp_years_hint = 0.0
    if isinstance(cv_data, dict) and cv_data.get("experience_years"):
        try:
            _exp_years_hint = float(cv_data["experience_years"])
        except (ValueError, TypeError):
            pass

    score_obj = score_candidate(
        candidate_id="COMPAT-" + str(hash(cv_text[:100])),
        cv_text=cv_text,
        job_title=job_title,
        job_description=job_requirements,
        required_years_experience=(
            cv_data.get("experience_years") or 0 if isinstance(cv_data, dict) else 0
        ),
        required_keywords=(
            cv_data.get("skills", []) if isinstance(cv_data, dict) else []
        ),
        past_titles=[
            exp.get("title")
            for exp in (cv_data.get("work_history", []) if isinstance(cv_data, dict) else [])
            if exp.get("title")
        ],
        cv_years_hint=_exp_years_hint,
    )

    sd = score_to_dict(score_obj)
    dims = sd["dimensions"]

    return {
        "score":           round(sd["final_score"] * 100, 2),
        "confidence":      round(sd["final_score"] * 100, 2),
        "domain":          sd["domain"],
        "hierarchy_level": sd["hierarchy_level"],
        "reasoning": (
            f"Score calculé via scoring hiérarchique v2.1 "
            f"— Niveau: {sd['hierarchy_level']}"
        ),
        "matched_keywords": sd["details"]["keywords"].get("matched_keywords", []),
        "missing_keywords": [],
        "dimension_scores": {
            # canonical v2.0 keys
            "experience":     dims["experience"],
            "education":      dims["education"],
            "certifications": dims["certifications"],
            "semantic":       dims["semantic"],
            "keywords":       dims["keywords"],
            "leadership":     dims["leadership"],
            "language":       dims["language"],
            "complexity":     dims["complexity"],
            # frontend aliases (ScorePanel.jsx)
            "keyword_score":            dims["keywords"],
            "semantic_score":           dims["semantic"],
            "experience_score":         dims["experience"],
            "project_complexity_score": dims["complexity"],
            "education_score":          dims["education"],
            "certification_score":      dims["certifications"],
            "leadership_score":         dims["leadership"],
            "language_score":           dims["language"],
        },
        "full_details": sd,
    }


def classify_domain(job_title: str, job_description: str = "") -> str:
    """Compatibility shim: returns domain as string."""
    return detect_domain(job_title.lower(), job_description.lower()).value


# Backwards-compat alias
detect_domain_compat = classify_domain


def compute_candidate_score_compat(cv_text: str, job_title: str, job_requirements: str) -> dict:
    """Legacy alias for callers passing raw text instead of a dict."""
    return compute_candidate_score(
        cv_data={"raw_text": cv_text},
        job_title=job_title,
        job_requirements=job_requirements,
    )


# =============================================================================
# __main__ — Tests intégrés
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("SCORING ATS 2.1 — Tests intégrés")
    print("=" * 70)

    print("\n[Test 1] Détection hiérarchique")
    assert detect_hierarchy_level("directeur général")          == HierarchyLevel.DIRECTION
    assert detect_hierarchy_level("chef de département finances") == HierarchyLevel.MANAGER_SENIOR
    assert detect_hierarchy_level("superviseur production")     == HierarchyLevel.MANAGER_INTERMEDIAIRE
    assert detect_hierarchy_level("opérateur machine")          == HierarchyLevel.COLLABORATEUR
    assert detect_hierarchy_level("ceo")                        == HierarchyLevel.DIRECTION
    assert detect_hierarchy_level("senior manager")             == HierarchyLevel.MANAGER_SENIOR
    print("✓ 6/6 assertions OK")

    print("\n[Test 2] Détection de domaine")
    assert detect_domain("comptable senior")      == Domain.FINANCE
    assert detect_domain("chef de chantier btp")  == Domain.CONSTRUCTION
    assert detect_domain("développeur fullstack")  == Domain.TECH
    print("✓ 3/3 assertions OK")

    print("\n[Test 3] Scoring complet - Directeur Financier")
    cv = """
    Directeur Financier - 15 ans d'expérience
    Formation : MBA Finance, IFRS certification, OHADA
    Compétences : audit, contrôle de gestion, trésorerie, consolidation
    A dirigé une équipe de 12 personnes, piloté la transformation financière,
    restructuré les processus budgétaires, fondé le département contrôle de gestion.
    Langues : Français (natif), Anglais (courant), TOEIC 950
    Certifications : ACCA, CPA
    """
    score = score_candidate(
        candidate_id="CAND-001",
        cv_text=cv,
        job_title="Directeur Financier",
        job_description="Directeur financier expérimenté, management d'équipe, IFRS, consolidation",
        required_years_experience=10,
        required_keywords=["ifrs", "consolidation", "audit", "trésorerie"],
    )
    d = score_to_dict(score)
    print(f"  Niveau  : {d['hierarchy_level']}")
    print(f"  Domaine : {d['domain']}")
    print(f"  Score   : {d['final_score']}")
    assert d['hierarchy_level'] == "direction"
    assert d['domain'] == "finance"
    assert d['final_score'] > 0.5
    print("✓ Score directeur financier OK")

    print("\n[Test 4] compute_candidate_score (compat shim — supabase kwarg)")
    result = compute_candidate_score(
        cv_data={"raw_text": cv, "skills": ["audit", "ifrs"]},
        job_title="Directeur Financier",
        job_requirements="IFRS, audit, consolidation",
        supabase=None,
    )
    assert "score" in result
    assert "dimension_scores" in result
    assert "keyword_score" in result["dimension_scores"]
    print(f"  Score (0-100): {result['score']}")
    print("✓ Compat shim OK")

    print("\n[Test 5] Feedback apprenant (intelligent score weights)")
    feedback = [
        FeedbackRecord("CAND-001", "Directeur Financier", 0.72, "hired",    0.85, "2026-06-03"),
        FeedbackRecord("CAND-002", "Directeur Financier", 0.65, "rejected", 0.40, "2026-06-03"),
    ]
    new_weights = update_weights_from_feedback(INTELLIGENT_SCORE_DEFAULT_WEIGHTS, feedback, learning_rate=0.01)
    total = sum(new_weights.values())
    assert 0.99 <= total <= 1.01, f"Somme des poids = {total}"
    assert set(new_weights.keys()) == set(INTELLIGENT_SCORE_DEFAULT_WEIGHTS.keys())
    print(f"  Somme des poids = {total:.4f}")
    print("✓ Feedback apprenant OK")

    print("\n" + "=" * 70)
    print("Tous les tests sont passés avec succès !")
    print("=" * 70)


__all__ = [
    "compute_candidate_score",
    "compute_candidate_score_compat",
    "classify_domain",
    "detect_domain_compat",
    "score_candidate",
    "score_to_dict",
    "batch_score",
    "rank_candidates",
    "update_weights_from_feedback",
    "enrich_cv_data",
    "Domain",
    "HierarchyLevel",
    "HierarchyProfile",
    "CandidateScore",
    "FeedbackRecord",
    "DEFAULT_WEIGHTS",
    "INTELLIGENT_SCORE_DEFAULT_WEIGHTS",
    "DOMAIN_SKILLS",
    "HIERARCHY_PROFILES",
    "DOMAIN_COMPLEXITY",
]
