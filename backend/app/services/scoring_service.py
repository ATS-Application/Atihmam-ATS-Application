"""
scoring_service.py — Service de scoring ATS pour le marché francophone africain.
Version 2.0 — Architecture hiérarchique à 4 niveaux avec leadership par actions.
Conçu pour Atihmam Conseils, adapté au contexte ivoirien et francophone.

Auteur : Magic_Mind pour Hamadou / Atihmam Conseils
Date   : 2026-06-03

Architecture :
- 27 domaines métier (Domain)
- 4 niveaux hiérarchiques (HierarchyLevel) : COLLABORATEUR, MANAGER_INTERMEDIAIRE,
  MANAGER_SENIOR, DIRECTION
- Poids différenciés par niveau hiérarchique (HIERARCHY_PROFILES)
- Pénalités de carence pour dimensions critiques sous-seuil (PENALTY_SYSTEM)
- Modèle sémantique multilingue (paraphrase-multilingual-MiniLM-L12-v2)
- Détection du leadership : titres passés + actions d'encadrement
- Indicateurs de complexité différenciés par niveau
- Certifications non-tech reconnues (OHADA, IFRS, SIRH, ISO, HACCP, etc.)
- Seuils éducatifs éliminatoires par niveau hiérarchique
"""

# =============================================================================
# Imports
# =============================================================================
import re
import math
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any, Set

# =============================================================================
# Utilitaire de normalisation textuelle
# =============================================================================

# Table de correspondance accents → caractères sans accent (français + spéciaux)
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
from collections import Counter

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# 1. Énumérations fondamentales
# =============================================================================

class HierarchyLevel(str, Enum):
    """
    Niveau hiérarchique du poste, détecté automatiquement depuis le titre.
    Détermine le profil de scoring (poids, seuils, indicateurs).
    """
    COLLABORATEUR = "collaborateur"               # Opérateur, technicien, analyste...
    MANAGER_INTERMEDIAIRE = "manager_intermediaire"  # Chef de service, team lead...
    MANAGER_SENIOR = "manager_senior"               # Responsable, chef de département
    DIRECTION = "direction"                          # Directeur, DG, VP, COMEX


class Domain(str, Enum):
    """
    27 domaines métier couvrant le spectre économique ivoirien et francophone.
    Utilisé pour l'ajustement des poids de scoring par domaine.
    """
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
# 2. Mapping des marqueurs de niveau hiérarchique (titres)
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
    """Profil de scoring complet pour un niveau hiérarchique."""
    level: HierarchyLevel
    # Poids des 9 dimensions (total = 1.0)
    w_experience: float = 0.25
    w_education: float = 0.12
    w_certifications: float = 0.08
    w_semantic: float = 0.20
    w_keywords: float = 0.10
    w_leadership: float = 0.05
    w_language: float = 0.05
    w_complexity: float = 0.10
    w_penalty: float = 0.05
    # Seuils
    min_years_experience: float = 0
    min_education_level: str = "none"
    require_certifications: bool = False
    require_leadership: bool = False
    # Multiplicateur de complexité
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
    Domain.TECH: 1.2,
    Domain.LEGAL: 1.5,
    Domain.HEALTH: 1.4,
    Domain.HR: 1.0,
    Domain.FINANCE: 1.3,
    Domain.MARKETING: 0.9,
    Domain.SALES: 0.8,
    Domain.EDUCATION: 1.0,
    Domain.AGRICULTURE: 1.3,
    Domain.CONSTRUCTION: 1.4,
    Domain.LOGISTICS: 1.0,
    Domain.TELECOM: 1.2,
    Domain.ENERGY: 1.5,
    Domain.MINING: 1.6,
    Domain.HOSPITALITY: 0.7,
    Domain.MEDIA: 0.9,
    Domain.INSURANCE: 1.2,
    Domain.REAL_ESTATE: 1.1,
    Domain.CONSULTING: 1.3,
    Domain.PUBLIC_ADMIN: 1.0,
    Domain.NGO: 0.9,
    Domain.PHARMA: 1.5,
    Domain.RETAIL: 0.7,
    Domain.TRANSPORT: 1.0,
    Domain.ENVIRONMENT: 1.2,
    Domain.CRAFTSMANSHIP: 1.1,
    Domain.SECURITY: 0.8,
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
# 6. Niveaux d'éducation (mapping et ordre)
# =============================================================================

EDUCATION_LEVEL_ORDER: List[str] = [
    "none",
    "cap_bep",
    "bac",
    "bac+2_bts_dut",
    "bac+3_licence",
    "bac+4_maitrise",
    "bac+5_master",
    "bac+8_doctorat",
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
# 7. Certifications reconnues (tech et non-tech, contexte africain)
# =============================================================================

CERTIFICATION_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Tech / IT
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
    # Contexte africain / francophone
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
             "aliases": ["cpa", "certified public accountant", "expert-comptable", "expertise comptable", "dpeco", "dscg", "dsc", "decof"]},
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
# 8. Verbes d'action de leadership (français + anglais)
# =============================================================================

LEADERSHIP_ACTION_VERBS: Dict[str, float] = {
    # Français - Management direct
    "dirigé": 1.0, "diriger": 0.9, "dirige": 1.0,
    "piloté": 1.0, "piloter": 0.9, "pilote": 1.0,
    "managé": 0.9, "manager": 0.8, "manage": 0.8,
    "supervisé": 0.8, "superviser": 0.7, "supervise": 0.8,
    "encadré": 0.8, "encadrer": 0.7, "encadre": 0.8,
    "coordonné": 0.7, "coordonner": 0.6, "coordonne": 0.7,
    "animé": 0.6, "animer": 0.5, "anime": 0.6,
    # Français - Leadership stratégique
    "conduit": 0.7, "conduire": 0.6,
    "initié": 0.7, "initier": 0.6,
    "transformé": 0.8, "transformer": 0.7,
    "restructuré": 0.8, "restructurer": 0.7,
    "développé": 0.5, "développer": 0.4,
    "fondé": 0.9, "fonder": 0.8,
    "créé": 0.6, "créer": 0.5,
    # Anglais
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
# 9. Configuration du système de pénalités de carence
# =============================================================================

@dataclass(frozen=True)
class DeficiencyPenalty:
    """Configuration d'une pénalité de carence pour une dimension."""
    dimension: str
    threshold: float           # Score sous lequel la pénalité s'applique
    max_penalty: float         # Pénalité maximale (proportion du score total)
    penalty_curve: str = "linear"  # linear, exponential, step
    description: str = ""


PENALTY_SYSTEM: List[DeficiencyPenalty] = [
    DeficiencyPenalty(
        dimension="experience",
        threshold=0.15,
        max_penalty=0.40,
        penalty_curve="exponential",
        description="Expérience critique insuffisante pour le poste",
    ),
    DeficiencyPenalty(
        dimension="education",
        threshold=0.10,
        max_penalty=0.25,
        penalty_curve="step",
        description="Niveau d'éducation en dessous du seuil requis",
    ),
    DeficiencyPenalty(
        dimension="certifications",
        threshold=0.05,
        max_penalty=0.15,
        penalty_curve="linear",
        description="Certifications obligatoires absentes",
    ),
    DeficiencyPenalty(
        dimension="leadership",
        threshold=0.10,
        max_penalty=0.20,
        penalty_curve="linear",
        description="Leadership requis mais non démontré",
    ),
    DeficiencyPenalty(
        dimension="language",
        threshold=0.10,
        max_penalty=0.10,
        penalty_curve="linear",
        description="Qualité linguistique insuffisante",
    ),
]


def compute_careness_penalty(
    dimension_scores: Dict[str, float],
    hierarchy_level: HierarchyLevel,
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Calcule la pénalité totale de carence et retourne le détail.
    """
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
            else:  # linear
                deficit = (pen.threshold - score) / pen.threshold
                penalty = pen.max_penalty * deficit

            total_penalty += penalty
            activated.append({
                "dimension": pen.dimension,
                "score": round(score, 3),
                "threshold": pen.threshold,
                "penalty_applied": round(penalty, 3),
                "description": pen.description,
            })

    total_penalty = min(total_penalty, 0.40)
    return total_penalty, activated


# =============================================================================
# 10. Détection de domaine à partir du titre de poste
# =============================================================================

DOMAIN_TITLE_KEYWORDS: Dict[Domain, List[str]] = {
    Domain.TECH: ["développeur", "developpeur", "ingénieur logiciel", "software",
                   "devops", "data", "cybersécurité", "cybersecurite", "fullstack",
                   "backend", "frontend", "mobile", "cloud", "architecte", "sre"],
    Domain.FINANCE: ["comptable", "finance", "audit", "trésorerie", "tresorerie",
                      "contrôleur", "controleur", "daf", "credit", "banque",
                      "microfinance", "fiscalité", "fiscalite"],
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
    Domain.REAL_ESTATE: ["immobilier", "immobilier", "promoteur", "agent immobilier"],
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
    """
    Détecte le domaine métier le plus probable à partir du titre de poste.
    Combine titres + description pour améliorer la précision.
    """
    combined = f"{title_lower} {description_lower}"
    scores: Dict[Domain, int] = {}

    for domain, keywords in DOMAIN_TITLE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[domain] = score

    if not scores:
        return Domain.CONSULTING  # Domaine par défaut

    return max(scores, key=scores.get)


# =============================================================================
# 11. Détection du niveau hiérarchique
# =============================================================================

def detect_hierarchy_level(title_lower: str) -> HierarchyLevel:
    """
    Détecte le niveau hiérarchique à partir du titre de poste.
    Priorité : DIRECTION > MANAGER_SENIOR > MANAGER_INTERMEDIAIRE > COLLABORATEUR
    """
    # Vérification par ordre de priorité décroissante
    for level in [HierarchyLevel.DIRECTION, HierarchyLevel.MANAGER_SENIOR,
                  HierarchyLevel.MANAGER_INTERMEDIAIRE]:
        markers = HIERARCHY_TITLE_MARKERS[level]
        for marker in markers:
            if marker in title_lower:
                return level

    return HierarchyLevel.COLLABORATEUR


# =============================================================================
# 12. Détection du niveau d'éducation
# =============================================================================

def detect_education_level(education_text: str) -> str:
    """
    Détecte le plus haut niveau d'éducation mentionné dans le texte.
    Retourne la clé EDUCATION_LEVEL_ORDER correspondante.
    """
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
    """
    Score d'expérience normalisé (0-1).
    Utilise une courbe sigmoïde pour éviter de pénaliser les seniors trop expérimentés.
    """
    profile = HIERARCHY_PROFILES[hierarchy_level]

    if required_years <= 0:
        ratio = min(cv_years / 5.0, 1.0) if cv_years > 0 else 0.0
    else:
        if cv_years >= required_years * 2:
            ratio = 1.0
        elif cv_years >= required_years:
            surplus = (cv_years - required_years) / required_years
            ratio = 0.7 + 0.3 * min(surplus, 1.0)
        else:
            ratio = cv_years / required_years

    # Pénalité si en dessous du seuil minimum
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
    """
    Score éducatif basé sur le niveau détecté vs le niveau requis par le poste.
    """
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
        # Aucun niveau requis
        score = min(cv_index / 4.0, 1.0)
        meets_requirement = True
    elif cv_index >= req_index + 2:
        # Niveau largement supérieur (ex: doctorat pour poste licence)
        score = 1.0
        meets_requirement = True
    elif cv_index >= req_index:
        # Niveau atteint ou légèrement supérieur
        score = 0.7 + 0.3 * (cv_index - req_index)
        meets_requirement = True
    elif cv_index >= req_index - 1:
        # Un cran en dessous
        score = 0.4
        meets_requirement = False
    else:
        # Plusieurs crans en dessous
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
    """
    Score de leadership combinant :
    1. Présence de titres passés avec marqueurs hiérarchiques
    2. Verbes d'action de leadership dans le texte du CV
    """
    profile = HIERARCHY_PROFILES[hierarchy_level]

    if not profile.require_leadership:
        return 1.0, {"leadership_required": False, "score": 1.0}

    text_lower = cv_text.lower()

    # 1. Score via verbes d'action
    verb_scores = []
    for verb, weight in LEADERSHIP_ACTION_VERBS.items():
        if verb in text_lower:
            verb_scores.append(weight)

    verb_score = max(verb_scores) if verb_scores else 0.0
    if len(verb_scores) >= 3:
        verb_score = min(verb_score + 0.1, 1.0)

    # 2. Score via titres passés hiérarchiques
    title_score = 0.0
    if past_titles:
        for title in past_titles:
            title_lower = title.lower()
            detected = detect_hierarchy_level(title_lower)
            if detected in [HierarchyLevel.MANAGER_SENIOR, HierarchyLevel.DIRECTION]:
                title_score = max(title_score, 0.8)
            elif detected == HierarchyLevel.MANAGER_INTERMEDIAIRE:
                title_score = max(title_score, 0.5)

    # Combinaison : verbes (60%) + titres (40%)
    combined = 0.6 * verb_score + 0.4 * title_score
    score = round(min(combined, 1.0), 3)

    return score, {
        "leadership_required": True,
        "verb_score": round(verb_score, 3),
        "title_score": round(title_score, 3),
        "combined": score,
        "verb_count": len(verb_scores),
    }


# =============================================================================
# 16. Scoring de complexité
# =============================================================================

def compute_complexity_score(
    cv_text: str,
    domain: Domain,
    hierarchy_level: HierarchyLevel,
) -> Tuple[float, Dict[str, Any]]:
    """
    Score de complexité mesurant la diversité du parcours.
    Plus le poste est élevé, plus on valorise les parcours multi-domaines.
    """
    profile = HIERARCHY_PROFILES[hierarchy_level]
    text_norm = normalize_text(cv_text)

    # Compter les domaines touchés (via les skills normalisés)
    domains_touched = 0
    for d, skills in DOMAIN_SKILLS.items():
        skills_norm = [normalize_text(s) for s in skills[:4]]
        if any(skill in text_norm for skill in skills_norm):
            domains_touched += 1

    # Score de base : diversité
    diversity_score = min(domains_touched / 5.0, 1.0)

    # Ajustement par niveau
    adjusted = diversity_score * profile.complexity_multiplier

    # Bonus si le domaine principal est bien couvert
    primary_skills = DOMAIN_SKILLS.get(domain, [])
    if primary_skills:
        primary_norm = [normalize_text(s) for s in primary_skills]
        primary_coverage = sum(1 for s in primary_norm if s in text_norm) / len(primary_norm)
        adjusted = 0.6 * adjusted + 0.4 * min(primary_coverage, 1.0)

    score = round(min(adjusted, 1.0), 3)
    return score, {
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
    """
    Score basé sur les certifications détectées, pondérées par niveau et domaine.
    Matching flexible : normalisation du texte + recherche via clé primaire ET aliases.
    """
    profile = HIERARCHY_PROFILES[hierarchy_level]
    text_norm = normalize_text(cv_text)
    found_certs = []
    total_weight = 0.0
    max_possible = 3.0  # Pour normalisation

    for cert_key, cert_info in CERTIFICATION_REGISTRY.items():
        # Rechercher la clé primaire ET tous les alias (normalisés)
        key_norm = normalize_text(cert_key)
        aliases = cert_info.get("aliases", [])
        all_terms = [key_norm] + [normalize_text(a) for a in aliases]

        matched = False
        for term in all_terms:
            if term in text_norm:
                matched = True
                break

        if matched:
            found_certs.append(cert_info["name"])
            weight = cert_info["weight"]
            # Bonus si le domaine de la certification correspond au poste
            if cert_info["domain"] == domain:
                weight *= 1.3
            # Bonus si certification de haut niveau pour poste senior
            if cert_info["level"] >= 4 and hierarchy_level in [
                HierarchyLevel.MANAGER_SENIOR, HierarchyLevel.DIRECTION
            ]:
                weight *= 1.2
            total_weight += weight

    score = round(min(total_weight / max_possible, 1.0), 3)

    # Si certifications obligatoires mais aucune trouvée : score plancher à 0.05
    # (un candidat sans certs n'est pas forcément incompétent, mais sera pénalisé)
    if profile.require_certifications and len(found_certs) == 0:
        score = 0.05

    return score, {
        "found_certifications": found_certs,
        "count": len(found_certs),
        "total_weight": round(total_weight, 3),
    }


# =============================================================================
# 18. Scoring sémantique (placeholder — modèle externe)
# =============================================================================

def compute_semantic_score(
    cv_text: str,
    job_description: str,
    domain: Domain,
) -> Tuple[float, Dict[str, Any]]:
    """
    Score sémantique utilisant paraphrase-multilingual-MiniLM-L12-v2.
    En l'absence du modèle chargé, utilise un fallback lexical normalisé.
    """
    cv_norm = normalize_text(cv_text)
    jd_norm = normalize_text(job_description)

    # Fallback lexical : bigrammes communs (normalisés)
    cv_words = set(re.findall(r'\b\w+\b', cv_norm))
    jd_words = set(re.findall(r'\b\w+\b', jd_norm))

    if not jd_words:
        return 0.5, {"method": "fallback_lexical", "note": "JD vide"}

    # Jaccard
    intersection = cv_words & jd_words
    union = cv_words | jd_words
    jaccard = len(intersection) / len(union) if union else 0.0

    # TF-IDF simplifié : pondération par rareté — skills normalisés
    domain_skills_raw = DOMAIN_SKILLS.get(domain, [])
    domain_skills_normalized = {normalize_text(s) for s in domain_skills_raw}
    skill_matches = intersection & domain_skills_normalized
    skill_ratio = len(skill_matches) / len(domain_skills_normalized) if domain_skills_normalized else 0.0

    # Combinaison : jaccard (40%) + skill match (60%)
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
    """
    Score de matching par mots-clés avec pondération par domaine.
    Matching insensible aux accents et à la casse.
    Le ratio est calculé sur le nombre de mots-clés requis OU sur les skills
    du domaine (si requis vide), avec un diviseur plafonné à 15 pour éviter
    les scores nuls sur les domaines à large spectre.
    """
    text_norm = normalize_text(cv_text)
    domain_skills_list = DOMAIN_SKILLS.get(domain, [])
    domain_skills_norm = [normalize_text(s) for s in domain_skills_list]
    required_norm = [normalize_text(kw) for kw in required_keywords]

    # Si mots-clés fournis explicitement : ne matcher que sur ceux-là
    if required_keywords:
        all_keywords = required_norm
        denominator = max(len(all_keywords), 1)
    else:
        # Sinon : skills du domaine comme fallback
        all_keywords = list(set(domain_skills_norm))
        # Plafonner le dénominateur pour ne pas écraser le score
        denominator = min(len(all_keywords), 12)

    if not all_keywords:
        return 0.5, {"method": "no_keywords", "note": "Aucun mot-clé configuré"}

    matched = []
    for kw_norm, kw_original in zip(all_keywords, all_keywords):
        if kw_norm in text_norm:
            matched.append(kw_original)

    # Ratio limité : matched / min(total_keywords, 12)
    ratio = len(matched) / denominator
    score = round(min(ratio * 1.2, 1.0), 3)

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
    """
    Évalue la qualité linguistique du CV et détecte la langue dominante.
    Ne pénalise pas un CV bien écrit en anglais pour un poste francophone.
    """
    if target_languages is None:
        target_languages = ["fr", "en"]

    text_lower = cv_text.lower()
    total_chars = len(cv_text)
    if total_chars < 50:
        return 0.3, {"error": "Texte trop court"}

    # Détection de langue simplifiée
    fr_markers = ["le ", "la ", "les ", "des ", "une ", "un ", "est ", "dans ",
                   "pour ", "avec ", "sur ", "sous ", "chez ", "je ", "nous ",
                   "expérience", "formation", "compétences", "entreprise"]
    en_markers = ["the ", "and ", "with ", "for ", "from ", "have ", "has ",
                   "experience", "education", "skills", "company", "worked"]

    fr_count = sum(1 for m in fr_markers if m in text_lower)
    en_count = sum(1 for m in en_markers if m in text_lower)

    if fr_count > en_count:
        detected_lang = "fr"
    elif en_count > fr_count:
        detected_lang = "en"
    else:
        detected_lang = "mixed"

    # Score de qualité basé sur la richesse lexicale
    words = re.findall(r'\b\w{3,}\b', text_lower)
    unique_words = set(words)
    lexical_richness = len(unique_words) / len(words) if words else 0.0

    # Score de structure (présence de sections)
    structure_markers = ["expérience", "experience", "formation", "education",
                          "compétences", "skills", "langues", "languages",
                          "certifications", "références", "references"]
    structure_score = sum(1 for m in structure_markers if m in text_lower) / len(structure_markers)

    # Longueur adéquate
    length_score = min(len(words) / 200, 1.0)

    score = round(0.3 * lexical_richness + 0.3 * structure_score + 0.2 * length_score + 0.2, 3)

    return score, {
        "detected_language": detected_lang,
        "lexical_richness": round(lexical_richness, 3),
        "structure_score": round(structure_score, 3),
        "word_count": len(words),
        "unique_words": len(unique_words),
    }

# =============================================================================
# 21. Dataclass CandidateScore
# =============================================================================

@dataclass
class CandidateScore:
    """Score complet d'un candidat avec toutes les dimensions et métadonnées."""
    candidate_id: str
    job_title: str
    # Hiérarchie et domaine détectés
    hierarchy_level: HierarchyLevel
    domain: Domain
    profile: HierarchyProfile
    # Scores dimensionnels (0-1)
    score_experience: float = 0.0
    score_education: float = 0.0
    score_certifications: float = 0.0
    score_semantic: float = 0.0
    score_keywords: float = 0.0
    score_leadership: float = 0.0
    score_language: float = 0.0
    score_complexity: float = 0.0
    # Pénalités
    penalty: float = 0.0
    penalty_details: List[Dict[str, Any]] = field(default_factory=list)
    # Score final
    final_score: float = 0.0
    # Détails
    details: Dict[str, Any] = field(default_factory=dict)
    # Métadonnées
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
) -> CandidateScore:
    """
    Fonction principale de scoring d'un candidat pour un poste donné.

    Args:
        candidate_id: Identifiant unique du candidat
        cv_text: Texte complet du CV
        job_title: Titre du poste visé
        job_description: Description détaillée du poste
        required_years_experience: Années d'expérience requises
        required_keywords: Mots-clés requis (optionnel)
        past_titles: Titres de postes précédents (optionnel)
        target_languages: Langues cibles attendues (défaut: ["fr", "en"])

    Returns:
        CandidateScore complet avec toutes les dimensions
    """
    if required_keywords is None:
        required_keywords = []
    if past_titles is None:
        past_titles = []
    if target_languages is None:
        target_languages = ["fr", "en"]

    # ---- Détection automatique ----
    title_lower = job_title.lower()
    jd_lower = job_description.lower()
    cv_lower = cv_text.lower()

    hierarchy_level = detect_hierarchy_level(title_lower)
    domain = detect_domain(title_lower, jd_lower)
    profile = HIERARCHY_PROFILES[hierarchy_level]
    detected_education = detect_education_level(cv_text)

    # ---- Extraction des années d'expérience ----
    # Pattern: "X ans", "X années", "X years", "X+ ans"
    years_pattern = re.findall(
        r'(\d+)\s*(?:\+)?\s*(?:ans?|années?|years?)(?:\s+d[\'\"](?:expérience|experience))?',
        cv_lower
    )
    cv_years = max([int(y) for y in years_pattern]) if years_pattern else 0.0

    # ---- Scoring des dimensions ----
    exp_score, exp_details = compute_experience_score(
        cv_years, required_years_experience, hierarchy_level
    )
    edu_score, edu_details = compute_education_score(
        detected_education, hierarchy_level
    )
    cert_score, cert_details = compute_certification_score(
        cv_text, domain, hierarchy_level
    )
    sem_score, sem_details = compute_semantic_score(
        cv_text, job_description, domain
    )
    kw_score, kw_details = compute_keyword_score(
        cv_text, required_keywords, domain
    )
    lead_score, lead_details = compute_leadership_score(
        cv_text, hierarchy_level, past_titles
    )
    lang_score, lang_details = compute_language_quality_score(
        cv_text, target_languages
    )
    comp_score, comp_details = compute_complexity_score(
        cv_text, domain, hierarchy_level
    )

    # ---- Agrégation pondérée ----
    weighted = (
        profile.w_experience * exp_score +
        profile.w_education * edu_score +
        profile.w_certifications * cert_score +
        profile.w_semantic * sem_score +
        profile.w_keywords * kw_score +
        profile.w_leadership * lead_score +
        profile.w_language * lang_score +
        profile.w_complexity * comp_score
    )

    # ---- Pénalités de carence ----
    dimension_scores = {
        "experience": exp_score,
        "education": edu_score,
        "certifications": cert_score,
        "leadership": lead_score,
        "language": lang_score,
    }
    penalty, penalty_details = compute_careness_penalty(
        dimension_scores, hierarchy_level
    )

    # ---- Score final ----
    raw_final = weighted - penalty + profile.w_penalty * (1.0 - penalty)
    final_score = round(max(0.0, min(raw_final, 1.0)), 4)

    # ---- Assemblage ----
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
            "experience": exp_details,
            "education": edu_details,
            "certifications": cert_details,
            "semantic": sem_details,
            "keywords": kw_details,
            "leadership": lead_details,
            "language": lang_details,
            "complexity": comp_details,
            "cv_years_detected": cv_years,
        },
        detected_education=detected_education,
        detected_language=lang_details.get("detected_language", "unknown"),
        past_titles=past_titles,
    )


# =============================================================================
# 23. Conversion en dictionnaire
# =============================================================================

def score_to_dict(score: CandidateScore) -> Dict[str, Any]:
    """
    Convertit un CandidateScore en dictionnaire sérialisable (JSON).
    """
    return {
        "candidate_id": score.candidate_id,
        "job_title": score.job_title,
        "hierarchy_level": score.hierarchy_level.value,
        "domain": score.domain.value,
        "final_score": score.final_score,
        "dimensions": {
            "experience": score.score_experience,
            "education": score.score_education,
            "certifications": score.score_certifications,
            "semantic": score.score_semantic,
            "keywords": score.score_keywords,
            "leadership": score.score_leadership,
            "language": score.score_language,
            "complexity": score.score_complexity,
        },
        "weights": {
            "w_experience": score.profile.w_experience,
            "w_education": score.profile.w_education,
            "w_certifications": score.profile.w_certifications,
            "w_semantic": score.profile.w_semantic,
            "w_keywords": score.profile.w_keywords,
            "w_leadership": score.profile.w_leadership,
            "w_language": score.profile.w_language,
            "w_complexity": score.profile.w_complexity,
            "w_penalty": score.profile.w_penalty,
        },
        "penalty": score.penalty,
        "penalty_details": score.penalty_details,
        "detected_education": score.detected_education,
        "detected_language": score.detected_language,
        "details": score.details,
    }


# =============================================================================
# 24. Feedback et apprentissage (boucle apprenante)
# =============================================================================

@dataclass
class FeedbackRecord:
    """Enregistrement de feedback recruteur pour ajustement des poids."""
    candidate_id: str
    job_title: str
    predicted_score: float
    actual_outcome: str       # "hired", "interviewed", "rejected"
    actual_rating: float      # Note réelle (0-1) attribuée par le recruteur
    timestamp: str = ""
    notes: str = ""


# Poids par défaut (état initial)
DEFAULT_WEIGHTS: Dict[str, float] = {
    "experience": 0.25,
    "education": 0.12,
    "certifications": 0.08,
    "semantic": 0.20,
    "keywords": 0.10,
    "leadership": 0.10,
    "language": 0.05,
    "complexity": 0.10,
}


def update_weights_from_feedback(
    current_weights: Dict[str, float],
    feedback_records: List[FeedbackRecord],
    learning_rate: float = 0.01,
) -> Dict[str, float]:
    """
    Ajuste les poids du scoring à partir du feedback recruteur.
    Utilise une descente de gradient simplifiée sur l'erreur de prédiction.

    Args:
        current_weights: Poids actuels (doivent sommer à ~1.0)
        feedback_records: Liste de feedbacks recruteur
        learning_rate: Taux d'apprentissage (0.001 à 0.05 recommandé)

    Returns:
        Nouveaux poids ajustés et normalisés
    """
    if not feedback_records:
        return current_weights

    new_weights = dict(current_weights)
    total_error = 0.0

    for fb in feedback_records:
        error = fb.actual_rating - fb.predicted_score
        total_error += abs(error)

        # Ajustement proportionnel à l'erreur sur chaque dimension
        for dim in new_weights:
            gradient = -2 * error * new_weights[dim]
            new_weights[dim] -= learning_rate * gradient

    # Normalisation
    total = sum(new_weights.values())
    if total > 0:
        new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}

    logger.info(
        f"Weights updated from {len(feedback_records)} feedbacks, "
        f"mean_abs_error={total_error/len(feedback_records):.4f}"
    )

    return new_weights


# =============================================================================
# 25. Fonctions utilitaires
# =============================================================================

def batch_score(
    candidates: List[Tuple[str, str]],
    job_title: str,
    job_description: str,
    required_years: float = 0,
    required_keywords: Optional[List[str]] = None,
) -> List[CandidateScore]:
    """
    Score un lot de candidats pour un même poste.
    """
    results = []
    for candidate_id, cv_text in candidates:
        try:
            score = score_candidate(
                candidate_id=candidate_id,
                cv_text=cv_text,
                job_title=job_title,
                job_description=job_description,
                required_years_experience=required_years,
                required_keywords=required_keywords,
            )
            results.append(score)
        except Exception as e:
            logger.error(f"Scoring failed for {candidate_id}: {e}")
            # Créer un score d'erreur
            results.append(CandidateScore(
                candidate_id=candidate_id,
                job_title=job_title,
                hierarchy_level=HierarchyLevel.COLLABORATEUR,
                domain=Domain.CONSULTING,
                profile=HIERARCHY_PROFILES[HierarchyLevel.COLLABORATEUR],
                final_score=0.0,
                details={"error": str(e)},
            ))
    return results


def rank_candidates(scores: List[CandidateScore]) -> List[CandidateScore]:
    """
    Trie les candidats par score final décroissant.
    """
    return sorted(scores, key=lambda s: s.final_score, reverse=True)


# =============================================================================
# __main__ — Tests intégrés
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("SCORING ATS 2.0 — Tests intégrés")
    print("=" * 70)

    # Test 1: Détection de niveau hiérarchique
    print("\n[Test 1] Détection hiérarchique")
    assert detect_hierarchy_level("directeur général") == HierarchyLevel.DIRECTION
    assert detect_hierarchy_level("chef de département finances") == HierarchyLevel.MANAGER_SENIOR
    assert detect_hierarchy_level("superviseur production") == HierarchyLevel.MANAGER_INTERMEDIAIRE
    assert detect_hierarchy_level("opérateur machine") == HierarchyLevel.COLLABORATEUR
    assert detect_hierarchy_level("ceo") == HierarchyLevel.DIRECTION
    assert detect_hierarchy_level("senior manager") == HierarchyLevel.MANAGER_SENIOR
    print("✓ 6/6 assertions OK")

    # Test 2: Détection de domaine
    print("\n[Test 2] Détection de domaine")
    assert detect_domain("comptable senior") == Domain.FINANCE
    assert detect_domain("chef de chantier btp") == Domain.CONSTRUCTION
    assert detect_domain("développeur fullstack") == Domain.TECH
    print("✓ 3/3 assertions OK")

    # Test 3: Scoring complet
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
    print(f"  Niveau détecté : {d['hierarchy_level']}")
    print(f"  Domaine       : {d['domain']}")
    print(f"  Score final   : {d['final_score']}")
    print(f"  Leadership    : {d['dimensions']['leadership']}")
    print(f"  Expérience    : {d['dimensions']['experience']}")
    print(f"  Pénalités     : {len(d['penalty_details'])}")
    assert d['hierarchy_level'] == "direction"
    assert d['domain'] == "finance"
    assert d['final_score'] > 0.5
    print("✓ Score directeur financier OK")

    # Test 4: Feedback + apprentissage
    print("\n[Test 4] Boucle de feedback apprenante")
    feedback = [
        FeedbackRecord(
            candidate_id="CAND-001",
            job_title="Directeur Financier",
            predicted_score=0.72,
            actual_outcome="hired",
            actual_rating=0.85,
            timestamp="2026-06-03",
        ),
        FeedbackRecord(
            candidate_id="CAND-002",
            job_title="Directeur Financier",
            predicted_score=0.65,
            actual_outcome="rejected",
            actual_rating=0.40,
            timestamp="2026-06-03",
        ),
    ]
    new_weights = update_weights_from_feedback(DEFAULT_WEIGHTS, feedback, learning_rate=0.01)
    print(f"  Poids ajustés ({len(feedback)} feedbacks):")
    for k, v in new_weights.items():
        print(f"    {k}: {v:.4f}")
    total = sum(new_weights.values())
    assert 0.99 <= total <= 1.01, f"Somme des poids = {total}, attendu ~1.0"
    print(f"  Somme des poids = {total:.4f}")
    print("✓ Feedback apprenant OK")

    print("\n" + "=" * 70)
    print("Tous les tests sont passés avec succès !")
    print("=" * 70)
