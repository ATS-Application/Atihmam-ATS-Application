# backend/app/services/scoring_service.py
# =============================================================================
# CŒUR DU SYSTÈME DE NOTATION DES CANDIDATS — v3.1 (bugfix v3.0)
#
# CORRECTIONS v3.1 :
#   • BUG #1 — keyword_score toujours 0 :
#       Ancienne logique : extrait les mots-clés du JOB TEXT via profile.keywords
#       → le job text est court/peu dense → job_kws vide → score 50 ou 0.
#       CORRECTION : approche CV-centric — on mesure combien de keywords du
#       profil apparaissent dans le CV, normalisé sur le total détecté dans
#       le job OU sur l'ensemble des keywords du profil si job trop pauvre.
#   • BUG #2 — semantic_score (Compétences) toujours 0 :
#       Le modèle SentenceTransformer peut crasher silencieusement en prod.
#       CORRECTION : fallback TF-IDF cosine similarity intégré ; le modèle
#       neural n'est tenté qu'une fois, puis on bascule sur le fallback.
#   • BUG #3 — normalisation des accents :
#       La fonction _norm() faisait un lower() mais ne retirait pas les accents,
#       causant des non-matchs entre "négociation" (CV) et "negociation" (index).
#       CORRECTION : _norm() utilise unicodedata pour supprimer les accents.
#   • Reste 100 % rétro-compatible avec ai_service.py (API publique inchangée).
# =============================================================================

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# =============================================================================
# CACHE HuggingFace — DOIT être défini avant tout import transformers
# =============================================================================
_CACHE_DIR = Path("./.hf-cache")
_CACHE_DIR.mkdir(exist_ok=True)
os.environ.setdefault("HF_HOME", str(_CACHE_DIR.resolve()))
os.environ.setdefault("TRANSFORMERS_CACHE", str(_CACHE_DIR.resolve()))

_MODEL_NAME = "all-MiniLM-L6-v2"

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Flag pour ne tenter le modèle neural qu'une seule fois (évite boucles d'erreur)
_neural_model_available: bool | None = None  # None = pas encore testé
_neural_model_lock = threading.Lock()

try:
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False


@lru_cache(maxsize=1)
def _get_model():
    """Charge le SentenceTransformer. Retourne None si indisponible."""
    if not _TORCH_AVAILABLE:
        return None
    try:
        from sentence_transformers import SentenceTransformer
        print(f"[scoring] Loading SentenceTransformer ({_MODEL_NAME})…")
        model = SentenceTransformer(
            _MODEL_NAME,
            device="cpu",
            model_kwargs={"torch_dtype": "float16"},
        )
        return model
    except Exception as exc:
        print(f"[scoring] SentenceTransformer unavailable: {exc}")
        return None


# =============================================================================
# UTILITAIRES COMMUNS
# =============================================================================

def _strip_accents(text: str) -> str:
    """Supprime les accents pour une comparaison robuste."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _norm(text: str | None) -> str:
    """
    Normalisation : minuscules + suppression des accents.
    CORRECTION v3.1 : l'ancienne version ne supprimait pas les accents,
    causant des non-matchs entre CV et mots-clés indexés.
    """
    if not text:
        return ""
    return _strip_accents(text.lower().strip())


def _clamp(value: float) -> float:
    return round(max(0.0, min(value, 100.0)), 2)


def safe_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if item]
        except (json.JSONDecodeError, ValueError):
            return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if item]
    return []


def safe_dict_list(value: Any) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
        except (json.JSONDecodeError, ValueError):
            return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


# =============================================================================
# ENUMS & TYPES
# =============================================================================

class Domain(str, Enum):
    TECH               = "Informatique & Développement logiciel"
    NETWORKS           = "Réseaux, Télécoms & Cybersécurité"
    ENGINEERING        = "Ingénierie & Techniques"
    SCIENCE            = "Sciences & Recherche"
    ENERGY             = "Énergie, Mines & Pétrole"
    INDUSTRY           = "Production & Industrie"
    QHSE               = "Qualité, Hygiène, Sécurité, Environnement (QHSE)"
    SUPPLY_CHAIN       = "Achats & Supply Chain"
    PURCHASING_MANAGER = "Responsable Achats"
    ADMIN              = "Administration & Secrétariat"
    AGRI               = "Agriculture & Agroalimentaire"
    ART                = "Art, Culture & Design"
    BANKING            = "Banque & Assurance"
    SALES              = "Commercial & Vente"
    ACCOUNTING         = "Comptabilité & Finance"
    BTP                = "Construction & BTP"
    LEGAL              = "Droit & Juridique"
    EDUCATION          = "Éducation & Formation"
    HOSPITALITY        = "Hôtellerie & Restauration"
    REAL_ESTATE        = "Immobilier"
    JOURNALISM         = "Journalisme & Médias"
    MARKETING          = "Marketing & Communication"
    HR                 = "Ressources Humaines (RH)"
    HEALTH             = "Santé & Médical"
    GENERAL_SERVICES   = "Services Généraux"
    INTERN             = "Stage / Jeune diplômé"
    TOURISM            = "Tourisme & Loisirs"
    TRANSPORT          = "Transport & Logistique"
    SOCIAL             = "Travail Social & ONG"


class ProfessionalLevel(str, Enum):
    JUNIOR    = "Junior / Employé"
    MID_LEVEL = "Confirmé / Mid-level"
    SENIOR    = "Senior"
    MANAGER   = "Manager / Responsable"
    DIRECTOR  = "Directeur / Head of"
    EXECUTIVE = "C-Level / DG / Executive"


class HierarchyLevel(str, Enum):
    COLLABORATEUR         = "collaborateur"
    MANAGER_INTERMEDIAIRE = "manager_intermediaire"
    MANAGER_SENIOR        = "manager_senior"
    DIRECTION             = "direction"


TECH_DOMAINS: frozenset[Domain] = frozenset({
    Domain.TECH,
    Domain.NETWORKS,
    Domain.ENGINEERING,
    Domain.SCIENCE,
    Domain.ENERGY,
    Domain.INDUSTRY,
    Domain.QHSE,
})


@dataclass
class DomainProfile:
    keywords         : tuple[str, ...] = field(default_factory=tuple)
    indicators       : dict[str, int]  = field(default_factory=dict)
    weight_overrides : dict[str, float]= field(default_factory=dict)
    leadership_terms : tuple[str, ...] = field(default_factory=tuple)


# =============================================================================
# CONSTANTES GLOBALES
# =============================================================================

TECH_KEYWORDS: tuple[str, ...] = (
    "spring boot", "node.js", "ci/cd",
    "python", "java", "spring", "react", "angular",
    "docker", "kubernetes", "aws", "azure", "gcp", "nestjs",
    "fastapi", "django", "graphql", "postgresql", "mongodb", "redis",
    "microservices", "scrum", "kafka", "typescript", "flutter",
    "tensorflow", "pytorch", "firebase",
)

_KW_PATTERNS: dict[str, re.Pattern] = {
    kw: re.compile(
        rf"\b{re.escape(kw)}\b" if " " not in kw else re.escape(kw),
        re.IGNORECASE,
    )
    for kw in TECH_KEYWORDS
}

CERTIFICATION_SCORES: dict[str, int] = {
    "aws":    35,
    "scrum":  30,
    "oracle": 35,
}

CERTIFICATION_REGISTRY: dict[str, dict[str, Any]] = {
    "aws":      {"name": "AWS Certification",        "domain": Domain.TECH,       "level": 3, "weight": 1.0},
    "azure":    {"name": "Microsoft Azure",          "domain": Domain.TECH,       "level": 3, "weight": 1.0},
    "gcp":      {"name": "Google Cloud",             "domain": Domain.TECH,       "level": 3, "weight": 0.9},
    "cisco":    {"name": "Cisco (CCNA/CCNP)",        "domain": Domain.NETWORKS,   "level": 3, "weight": 1.0},
    "pmp":      {"name": "PMP",                      "domain": Domain.ENGINEERING,"level": 4, "weight": 1.2},
    "prince2":  {"name": "PRINCE2",                  "domain": Domain.ENGINEERING,"level": 3, "weight": 1.0},
    "scrum":    {"name": "Scrum Master / PO",        "domain": Domain.TECH,       "level": 2, "weight": 0.7},
    "itil":     {"name": "ITIL",                     "domain": Domain.TECH,       "level": 3, "weight": 0.8},
    "iso 9001": {"name": "ISO 9001",                 "domain": Domain.QHSE,       "level": 3, "weight": 1.0},
    "iso 14001":{"name": "ISO 14001",                "domain": Domain.QHSE,       "level": 3, "weight": 1.0},
    "iso 45001":{"name": "ISO 45001",                "domain": Domain.QHSE,       "level": 3, "weight": 1.0},
    "iso 22000":{"name": "ISO 22000",                "domain": Domain.AGRI,       "level": 3, "weight": 1.0},
    "haccp":    {"name": "HACCP",                    "domain": Domain.AGRI,       "level": 3, "weight": 1.0},
    "ohada":    {"name": "OHADA",                    "domain": Domain.LEGAL,      "level": 4, "weight": 1.5},
    "ifrs":     {"name": "IFRS Certification",       "domain": Domain.ACCOUNTING, "level": 4, "weight": 1.3},
    "acca":     {"name": "ACCA",                     "domain": Domain.ACCOUNTING, "level": 4, "weight": 1.3},
    "cima":     {"name": "CIMA",                     "domain": Domain.ACCOUNTING, "level": 4, "weight": 1.2},
    "cfa":      {"name": "CFA",                      "domain": Domain.ACCOUNTING, "level": 5, "weight": 1.5},
    "cpa":      {"name": "CPA",                      "domain": Domain.ACCOUNTING, "level": 4, "weight": 1.3},
    "sirh":     {"name": "SIRH Certification",       "domain": Domain.HR,         "level": 3, "weight": 1.0},
    "toeic":    {"name": "TOEIC",                    "domain": Domain.EDUCATION,  "level": 1, "weight": 0.5},
    "toefl":    {"name": "TOEFL",                    "domain": Domain.EDUCATION,  "level": 1, "weight": 0.5},
    "ielts":    {"name": "IELTS",                    "domain": Domain.EDUCATION,  "level": 1, "weight": 0.5},
    "oracle":   {"name": "Oracle Certification",     "domain": Domain.TECH,       "level": 3, "weight": 1.0},
}

LEADERSHIP_TERMS: tuple[str, ...] = (
    "lead", "leader", "mentor", "management", "architect",
    "code review", "scrum", "encadrement",
)

LEADERSHIP_ACTION_VERBS: dict[str, float] = {
    "dirige": 1.0, "pilote": 1.0, "manage": 0.8,
    "supervise": 0.8, "encadre": 0.8, "coordonne": 0.7,
    "anime": 0.6, "conduit": 0.7, "initie": 0.7, "transforme": 0.8,
    "restructure": 0.8, "fonde": 0.9, "cree": 0.6,
    # formes passées (accents supprimés par _norm)
    "dirige": 1.0, "pilote": 1.0, "manage": 0.9,
    "supervise": 0.8, "encadre": 0.8, "coordonne": 0.7,
    "anime": 0.6, "conduit": 0.7, "initie": 0.7, "transforme": 0.8,
    "restructure": 0.8, "fonde": 0.9, "cree": 0.6,
    # anglais
    "led": 1.0, "lead": 1.0, "managed": 0.9, "oversaw": 0.9,
    "supervised": 0.8, "coordinated": 0.7, "orchestrated": 0.8,
    "headed": 0.9, "directed": 1.0, "spearheaded": 0.9,
    "championed": 0.8, "mentored": 0.6, "coached": 0.5,
    "empowered": 0.7, "built": 0.5, "established": 0.7, "founded": 0.9,
}

COMPLEXITY_INDICATORS: dict[str, int] = {
    "microservices":     20,
    "kubernetes":        20,
    "distributed":       15,
    "millions":          15,
    "scalable":          15,
    "ci/cd":             10,
    "aws":               10,
    "architecture":      15,
    "real-time":         15,
    "event-driven":      15,
    "high availability": 20,
    "machine learning":  10,
    "tensorflow":        10,
    "pytorch":           10,
}

DEFAULT_REQUIRED_EXPERIENCE: int = 3

DEFAULT_WEIGHTS: dict[str, float] = {
    "keyword":       0.10,
    "semantic":      0.20,
    "experience":    0.18,
    "certification": 0.08,
    "complexity":    0.22,
    "education":     0.13,
    "leadership":    0.05,
    "language":      0.04,
}

_DIM_TO_WEIGHT: dict[str, str] = {
    "keyword_score":            "keyword",
    "semantic_score":           "semantic",
    "experience_score":         "experience",
    "certification_score":      "certification",
    "education_score":          "education",
    "leadership_score":         "leadership",
    "project_complexity_score": "complexity",
    "language_score":           "language",
}

_LIKE_BOOST    = 0.05
_DISLIKE_DECAY = 0.05

_active_weights: dict[str, float] = dict(DEFAULT_WEIGHTS)
_weights_lock = threading.Lock()


# =============================================================================
# HIÉRARCHIE
# =============================================================================

HIERARCHY_TITLE_MARKERS: dict[HierarchyLevel, list[str]] = {
    HierarchyLevel.COLLABORATEUR: [
        "operateur", "technicien", "analyste", "assistant", "agent",
        "ouvrier", "employe", "stagiaire", "junior", "debutant",
        "secretaire", "comptable", "caissier", "chauffeur",
        "operator", "technician", "analyst", "junior", "staff", "clerk",
    ],
    HierarchyLevel.MANAGER_INTERMEDIAIRE: [
        "chef de service", "chef service", "supervisor", "superviseur",
        "team lead", "team leader", "coordonnateur", "coordinateur",
        "chef d'equipe", "chef equipe", "responsable d'equipe",
        "contremaitre", "superintendent", "foreman",
    ],
    HierarchyLevel.MANAGER_SENIOR: [
        "responsable", "chef de departement", "chef departement",
        "head of", "directeur adjoint", "directrice adjointe",
        "deputy director", "senior manager", "manager senior",
        "chef de division", "chef division", "chef de projet senior",
        "senior project manager", "responsable pole",
        "business unit manager", "head of department",
    ],
    HierarchyLevel.DIRECTION: [
        "directeur general", "directrice generale", "dg", "ceo",
        "directeur", "directrice", "president",
        "vice-president", "vice president", "vp", "c-level",
        "chief", "comex", "codir", "managing director",
        "executive director", "directeur executif", "pdg",
        "secretaire general",
    ],
}


@dataclass(frozen=True)
class HierarchyProfile:
    level: HierarchyLevel
    w_experience     : float = 0.25
    w_education      : float = 0.12
    w_certifications : float = 0.08
    w_semantic       : float = 0.20
    w_keywords       : float = 0.10
    w_leadership     : float = 0.05
    w_language       : float = 0.05
    w_complexity     : float = 0.10
    w_penalty        : float = 0.05
    min_years_experience  : float = 0
    min_education_level   : str   = "none"
    require_certifications: bool  = False
    require_leadership    : bool  = False
    complexity_multiplier : float = 1.0


HIERARCHY_PROFILES: dict[HierarchyLevel, HierarchyProfile] = {
    HierarchyLevel.COLLABORATEUR: HierarchyProfile(
        level=HierarchyLevel.COLLABORATEUR,
        w_experience=0.20, w_education=0.15, w_certifications=0.10,
        w_semantic=0.15, w_keywords=0.15, w_leadership=0.00,
        w_language=0.05, w_complexity=0.10, w_penalty=0.10,
        min_years_experience=0, min_education_level="cap_bep",
        require_certifications=False, require_leadership=False,
        complexity_multiplier=0.8,
    ),
    HierarchyLevel.MANAGER_INTERMEDIAIRE: HierarchyProfile(
        level=HierarchyLevel.MANAGER_INTERMEDIAIRE,
        w_experience=0.22, w_education=0.12, w_certifications=0.08,
        w_semantic=0.18, w_keywords=0.12, w_leadership=0.10,
        w_language=0.05, w_complexity=0.08, w_penalty=0.05,
        min_years_experience=3, min_education_level="bac",
        require_certifications=False, require_leadership=True,
        complexity_multiplier=1.0,
    ),
    HierarchyLevel.MANAGER_SENIOR: HierarchyProfile(
        level=HierarchyLevel.MANAGER_SENIOR,
        w_experience=0.25, w_education=0.10, w_certifications=0.08,
        w_semantic=0.15, w_keywords=0.08, w_leadership=0.15,
        w_language=0.07, w_complexity=0.07, w_penalty=0.05,
        min_years_experience=7, min_education_level="bac+3_licence",
        require_certifications=True, require_leadership=True,
        complexity_multiplier=1.2,
    ),
    HierarchyLevel.DIRECTION: HierarchyProfile(
        level=HierarchyLevel.DIRECTION,
        w_experience=0.20, w_education=0.10, w_certifications=0.05,
        w_semantic=0.12, w_keywords=0.05, w_leadership=0.25,
        w_language=0.10, w_complexity=0.08, w_penalty=0.05,
        min_years_experience=10, min_education_level="bac+5_master",
        require_certifications=False, require_leadership=True,
        complexity_multiplier=1.5,
    ),
}

_HIER_TO_PROF: dict[HierarchyLevel, ProfessionalLevel] = {
    HierarchyLevel.COLLABORATEUR:         ProfessionalLevel.MID_LEVEL,
    HierarchyLevel.MANAGER_INTERMEDIAIRE: ProfessionalLevel.MANAGER,
    HierarchyLevel.MANAGER_SENIOR:        ProfessionalLevel.SENIOR,
    HierarchyLevel.DIRECTION:             ProfessionalLevel.DIRECTOR,
}


# =============================================================================
# SYSTÈME DE PÉNALITÉS DE CARENCE
# =============================================================================

@dataclass(frozen=True)
class DeficiencyPenalty:
    dimension    : str
    threshold    : float
    max_penalty  : float
    penalty_curve: str = "linear"
    description  : str = ""


PENALTY_SYSTEM: list[DeficiencyPenalty] = [
    DeficiencyPenalty("experience",    0.15, 0.40, "exponential", "Expérience critique insuffisante"),
    DeficiencyPenalty("education",     0.10, 0.25, "step",        "Niveau d'éducation sous le seuil requis"),
    DeficiencyPenalty("certification", 0.05, 0.15, "linear",      "Certifications obligatoires absentes"),
    DeficiencyPenalty("leadership",    0.10, 0.20, "linear",      "Leadership requis mais non démontré"),
    DeficiencyPenalty("language",      0.10, 0.10, "linear",      "Qualité linguistique insuffisante"),
]


def _compute_careness_penalty(
    dim_scores_normalized: dict[str, float],
    hierarchy_level: HierarchyLevel,
) -> tuple[float, list[dict[str, Any]]]:
    total_penalty = 0.0
    activated: list[dict[str, Any]] = []

    for pen in PENALTY_SYSTEM:
        score = dim_scores_normalized.get(pen.dimension, 1.0)
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
# DÉTECTION DE DOMAINE
# =============================================================================

# -----------------------------------------------------------------------
# CORRECTION v3.1 : les clés du dictionnaire de détection sont maintenant
# stockées sans accents (via _strip_accents) pour correspondre au texte
# normalisé produit par _norm().
# -----------------------------------------------------------------------
def _build_detection_set(keywords: set[str]) -> frozenset[str]:
    """Normalise un ensemble de mots-clés pour la détection de domaine."""
    return frozenset(_strip_accents(k.lower()) for k in keywords)


_DOMAIN_DETECTION: dict[Domain, frozenset[str]] = {
    Domain.TECH: _build_detection_set({
        "python", "java", "react", "docker", "kubernetes",
        "api", "backend", "frontend", "devops", "software",
        "developpement logiciel", "informatique", "programmation",
    }),
    Domain.NETWORKS: _build_detection_set({
        "reseau", "network", "cybersecurite", "cisco", "firewall",
        "switch", "vpn", "telecoms", "infrastructure reseau",
    }),
    Domain.ENGINEERING: _build_detection_set({
        "mecanique", "electrique", "conception", "autocad",
        "solidworks", "bureau d'etudes", "ingenierie",
    }),
    Domain.SCIENCE: _build_detection_set({
        "laboratoire", "recherche", "publication", "these",
        "protocole", "experimentation", "chimie", "biologie",
    }),
    Domain.ENERGY: _build_detection_set({
        "petrole", "mines", "forage", "geologie", "raffinage",
        "energie renouvelable", "solaire", "hydraulique",
    }),
    Domain.INDUSTRY: _build_detection_set({
        "production", "usine", "chaine de montage", "lean",
        "maintenance industrielle", "5s", "kaizen",
    }),
    Domain.QHSE: _build_detection_set({
        "hse", "qualite", "iso 9001", "iso 14001",
        "securite au travail", "audit qualite", "non-conformite",
    }),
    Domain.SUPPLY_CHAIN: _build_detection_set({
        "achat", "supply chain", "approvisionnement", "logistique",
        "fournisseur", "negociation achat", "erp", "stock", "sla",
    }),
    Domain.PURCHASING_MANAGER: _build_detection_set({
        "responsable achats", "chef des achats", "directeur achats",
        "sla", "service-level agreement",
    }),
    Domain.ADMIN: _build_detection_set({
        "secretariat", "assistante", "agenda", "courrier",
        "accueil", "classement", "bureautique", "archivage",
    }),
    Domain.AGRI: _build_detection_set({
        "agriculture", "elevage", "agronomie", "semences",
        "cultures", "agroalimentaire", "terrain agricole",
    }),
    Domain.ART: _build_detection_set({
        "design", "graphisme", "photographie", "illustration",
        "creatif", "adobe", "figma", "ux", "ui", "artiste",
    }),
    Domain.BANKING: _build_detection_set({
        "banque", "assurance", "credit", "risque", "bale",
        "conformite", "actuariat", "portefeuille clients",
    }),
    Domain.SALES: _build_detection_set({
        "vente", "commercial", "prospection", "crm", "ca",
        "chiffre d'affaires", "b2b", "b2c", "negociation commerciale",
    }),
    Domain.ACCOUNTING: _build_detection_set({
        "comptabilite", "fiscalite", "bilan", "audit financier",
        "ifrs", "ohada", "controle de gestion", "tresorerie",
    }),
    Domain.BTP: _build_detection_set({
        "construction", "btp", "chantier", "genie civil",
        "maconnerie", "conducteur de travaux", "batiment",
    }),
    Domain.LEGAL: _build_detection_set({
        "droit", "juridique", "contrat", "avocat", "notaire",
        "procedure", "contentieux", "reglementation",
    }),
    Domain.EDUCATION: _build_detection_set({
        "enseignement", "formateur", "pedagogie", "curriculum",
        "professeur", "eleves", "formation professionnelle",
    }),
    Domain.HOSPITALITY: _build_detection_set({
        "hotellerie", "restauration", "cuisine", "chef",
        "service en salle", "accueil client", "f&b",
    }),
    Domain.REAL_ESTATE: _build_detection_set({
        "immobilier", "transaction", "bail", "copropriete",
        "expertise immobiliere", "promotion immobiliere",
    }),
    Domain.JOURNALISM: _build_detection_set({
        "journalisme", "redaction", "medias", "presse",
        "reportage", "edition", "publication", "contenu editorial",
    }),
    Domain.MARKETING: _build_detection_set({
        "marketing", "communication", "strategie digitale",
        "seo", "sem", "brand", "campagne", "publicite",
    }),
    Domain.HR: _build_detection_set({
        "ressources humaines", "recrutement", "paie", "gpec",
        "formation", "relations sociales", "rh", "talent",
    }),
    Domain.HEALTH: _build_detection_set({
        "medecin", "infirmier", "pharmacie", "sante", "clinique",
        "patient", "soins", "hopital", "medical",
    }),
    Domain.GENERAL_SERVICES: _build_detection_set({
        "maintenance", "facility", "nettoyage", "gardiennage",
        "services generaux", "prestataires",
    }),
    Domain.INTERN: _build_detection_set({
        "stage", "jeune diplome", "alternance", "apprentissage",
    }),
    Domain.TOURISM: _build_detection_set({
        "tourisme", "voyage", "hotel", "agence de voyage",
        "guide touristique", "loisirs",
    }),
    Domain.TRANSPORT: _build_detection_set({
        "transport", "logistique", "chauffeur", "fret",
        "douane", "transit", "fleet management",
    }),
    Domain.SOCIAL: _build_detection_set({
        "travail social", "ong", "humanitaire", "developpement communautaire",
        "action sociale", "volontariat", "ngo",
    }),
}


def classify_domain(cv_text: str, job_title: str, job_requirements: str) -> Domain:
    combined  = _norm(f"{cv_text} {job_title} {job_requirements}")
    best      = Domain.TECH
    best_hits = 0
    for domain, signals in _DOMAIN_DETECTION.items():
        hits = sum(1 for sig in signals if sig in combined)
        if hits > best_hits:
            best_hits = hits
            best      = domain
    return best


# =============================================================================
# PROFILS DE DOMAINE
# =============================================================================

_NON_TECH_WEIGHT_DEFAULT: dict[str, float] = {
    "keyword": 0.10, "semantic": 0.35, "experience": 0.15,
    "leadership": 0.10, "complexity": 0.25, "education": 0.05,
}


def _norm_keywords(kws: tuple[str, ...]) -> tuple[str, ...]:
    """
    Pré-normalise les mots-clés d'un profil (suppression accents + minuscules).
    CORRECTION v3.1 : permet la comparaison avec le texte normalisé par _norm().
    """
    return tuple(_strip_accents(k.lower()) for k in kws)


def _norm_indicators(ind: dict[str, int]) -> dict[str, int]:
    """Pré-normalise les clés d'indicateurs."""
    return {_strip_accents(k.lower()): v for k, v in ind.items()}


_DOMAIN_PROFILES_RAW: dict[Domain, DomainProfile] = {

    Domain.SUPPLY_CHAIN: DomainProfile(
        keywords=(
            "achat", "approvisionnement", "supply chain", "erp", "sap",
            "negociation", "fournisseur", "inventaire", "logistique",
            "appel d'offres", "sourcing", "stock", "s&op",
            "gestion des stocks", "planification", "prevision de la demande",
            "reduction des couts", "optimisation des achats", "contrat fournisseur",
            "cahier des charges", "evaluation fournisseurs", "referencement fournisseur",
            "commande", "bon de commande", "delai de livraison", "rupture de stock",
            "just-in-time", "kanban", "lean supply chain", "audit fournisseur",
            "panel fournisseurs", "portefeuille fournisseurs", "contrat-cadre",
            "transport", "incoterms", "import", "export", "douane",
            "demand planning", "master data", "edi", "p2p", "procure-to-pay",
            "catalogue achats", "budget achats", "kpi achats", "tco",
            "total cost of ownership", "achat durable", "rse fournisseurs",
            "rfq", "rfp", "sourcing international", "centrale d'achat",
            "vendor management", "sla fournisseur", "performance fournisseur",
        ),
        indicators={
            "sap": 20, "erp": 15, "s&op": 20,
            "negociation": 15, "sourcing international": 20, "reduction couts": 15,
        },
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
        leadership_terms=("chef des achats", "responsable supply chain", "directeur achats"),
    ),

    Domain.PURCHASING_MANAGER: DomainProfile(
        keywords=(
            "responsable achats", "chef des achats", "directeur achats",
            "strategie achat", "sla", "gestion fournisseurs", "negociation achat",
            "supply chain", "politique d'achat", "service level agreement",
            "reduction des couts", "p and l", "profit and loss",
            "portefeuille fournisseurs", "gestion des contrats d'achat",
            "wallet", "gestion des stocks", "gestion des approvisionnements",
            "stock", "appel d'offres", "procedure d'achat",
            "contrat-cadre", "cahier des charges", "evaluation fournisseurs",
            "panel fournisseurs", "audit fournisseur", "referencement fournisseur",
            "sourcing", "sourcing international", "centrale d'achat",
            "budget achats", "kpi achats", "tco", "total cost of ownership",
            "rfq", "rfp", "bon de commande", "commande", "catalogue achats",
            "procure-to-pay", "p2p", "edi", "erp", "sap", "demand planning",
            "performance fournisseur", "sla fournisseur", "vendor management",
            "achat durable", "rse fournisseurs", "import", "export", "incoterms",
            "plan d'achat", "strategie de negociation", "economies d'achats",
            "tableau de bord achats", "reporting achats", "delai de livraison",
        ),
        indicators={"sla": 20, "service-level agreement": 20, "slas": 20},
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
    ),

    Domain.ADMIN: DomainProfile(
        keywords=(
            "secretariat", "bureautique", "word", "excel", "agenda",
            "courrier", "classement", "archivage", "accueil", "office",
            "powerpoint", "outlook", "saisie", "redaction administrative",
            "compte rendu", "proces-verbal", "gestion administrative",
            "secretaire de direction", "assistante de direction",
            "office manager", "gestion documentaire", "ged",
            "numerisation", "tri du courrier", "standard telephonique",
            "planification", "reservation", "gestion des deplacements",
            "organisation de reunions", "prise de notes", "frappe",
            "mise en page", "publipostage", "office 365", "teams",
            "sharepoint", "google workspace", "google docs", "google sheets",
            "administration du personnel", "gestion des conges",
            "tableau de bord", "suivi administratif", "relance",
            "facturation", "devis", "bon de commande", "suivi des paiements",
            "accueil physique", "accueil telephonique", "agenda electronique",
            "confidentialite", "discretion", "polyvalence administrative",
            "gestion des fournitures", "commandes de bureau",
            "organisation d'evenements", "protocole",
        ),
        indicators={"bilingue": 20, "office 365": 15, "gestion agenda": 15},
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
    ),

    Domain.AGRI: DomainProfile(
        keywords=(
            "agronomie", "agriculture", "elevage", "cultures", "semences",
            "irrigation", "fertilisation", "agroalimentaire", "phytosanitaire",
            "agronome", "exploitation agricole", "gestion d'exploitation",
            "production vegetale", "production animale", "maraichage",
            "arboriculture", "viticulture", "sylviculture", "aquaculture",
            "pisciculture", "aviculture", "bovins", "ovins", "caprins",
            "sorgho", "mais", "riz", "cacao", "cafe", "coton", "palmier a huile",
            "intrants agricoles", "pesticides", "herbicides", "fongicides",
            "engrais", "amendement", "compostage", "agriculture biologique",
            "certification bio", "agriculture durable", "agroecologie",
            "agroforesterie", "permaculture", "geospatial", "sig agricole",
            "meteorologie agricole", "chaine de valeur agricole",
            "stockage post-recolte", "transformation agroalimentaire",
            "commercialisation agricole", "cooperative agricole",
            "conseil agricole", "vulgarisation agricole", "financement agricole",
            "credit rural", "microcredit agricole", "projet de developpement rural",
        ),
        indicators={
            "agriculture biologique": 20, "certification bio": 20,
            "gestion d'exploitation": 15, "irrigation": 10,
        },
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
    ),

    Domain.ART: DomainProfile(
        keywords=(
            "design", "graphisme", "illustrator", "photoshop", "figma",
            "ux", "ui", "creatif", "branding", "motion design",
            "photographie", "video", "3d", "after effects",
            "direction artistique", "identite visuelle", "charte graphique",
            "typographie", "mise en page", "infographie", "conception graphique",
            "design d'interface", "design produit", "design web",
            "ux research", "user testing", "wireframe", "prototype",
            "sketch", "adobe xd", "indesign", "premiere pro",
            "cinema 4d", "blender", "zbrush", "substance painter",
            "animation 3d", "vfx", "storyboard", "illustration",
            "dessin", "aquarelle", "peinture digitale", "retouche photo",
            "color grading", "montage video", "realisation", "scenario",
            "creativite", "concept art", "design thinking", "design system",
            "accessibilite numerique", "responsive design", "mobile-first",
            "landing page design", "ui kit", "design sprint",
            "communication visuelle", "arts plastiques", "multimedia",
        ),
        indicators={
            "direction artistique": 20, "identite visuelle": 15,
            "motion design": 15, "ux research": 20,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.35, "experience": 0.15,
            "education": 0.10, "complexity": 0.25, "leadership": 0.05,
        },
    ),

    Domain.BANKING: DomainProfile(
        keywords=(
            "banque", "assurance", "credit", "risque", "portefeuille",
            "conformite", "bale iii", "solvabilite", "actuariat",
            "kyc", "aml", "produits financiers", "taux",
            "analyse financiere", "tresorerie bancaire", "liquidite",
            "fonds propres", "ratio de solvabilite", "stress test",
            "risque de credit", "risque de marche", "risque operationnel",
            "risque de liquidite", "notation financiere", "scoring",
            "recouvrement", "contentieux bancaire", "garantie bancaire",
            "lettre de credit", "trade finance", "financement structure",
            "marches financiers", "obligations", "actions", "derives",
            "swift", "sepa", "virement", "prelevement", "mobile banking",
            "fintech", "open banking", "paiements digitaux", "microfinance",
            "credit immobilier", "credit consommation", "leasing",
            "assurance vie", "assurance dommages", "courtage", "prevoyance",
            "reassurance", "ifrs 9", "ifrs 17", "reglementation bancaire",
            "controle interne bancaire", "audit bancaire", "inspection",
            "direction des risques", "comite de credit",
        ),
        indicators={
            "bale iii": 20, "kyc/aml": 20, "actuariat": 20,
            "gestion risque": 15, "ifrs 9": 20,
        },
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
    ),

    Domain.SALES: DomainProfile(
        keywords=(
            "vente", "commercial", "prospection", "crm", "b2b", "b2c",
            "negociation", "chiffre d'affaires", "pipeline", "closing",
            "account manager", "fidelisation", "developpement commercial",
            "teleprospection", "cold calling", "lead generation",
            "qualification", "cycle de vente", "funnel commercial",
            "grand compte", "key account", "vente complexe",
            "argumentaire de vente", "objections", "rebond commercial",
            "upsell", "cross-sell", "panier moyen", "taux de conversion",
            "quota", "objectifs commerciaux", "commissionnement",
            "variable commerciale", "incentive", "sales force",
            "salesforce", "hubspot", "zoho", "reporting commercial",
            "tableau de bord commercial", "kpi ventes",
            "prevision de ventes", "forecasting", "business development",
            "partenariat commercial", "reseau de distribution",
            "agent commercial", "vente indirecte", "vente directe",
            "pitch commercial", "demonstration produit", "offre commerciale",
            "devis", "proposition commerciale", "appel d'offres",
            "renouvellement", "retention client", "satisfaction client",
            "nps", "customer success",
        ),
        indicators={
            "developpement commercial": 15, "grand compte": 20,
            "b2b": 10, "crm": 10, "objectifs depasses": 20,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.35, "experience": 0.15,
            "complexity": 0.25, "leadership": 0.10, "education": 0.05,
        },
        leadership_terms=("directeur commercial", "chef des ventes", "key account manager"),
    ),

    Domain.ACCOUNTING: DomainProfile(
        keywords=(
            "comptabilite", "fiscalite", "bilan", "ohada", "ifrs",
            "controle de gestion", "audit", "tresorerie", "sage",
            "declarations fiscales", "rapprochement bancaire", "budget",
            "comptabilite generale", "comptabilite analytique",
            "comptabilite clients", "comptabilite fournisseurs",
            "grand livre", "journal comptable", "balance", "liasse fiscale",
            "compte de resultat", "flux de tresorerie", "cash flow",
            "immobilisations", "amortissement", "provision", "charges",
            "produits", "tva", "is", "impot sur les societes", "cit",
            "impot sur le revenu", "paie comptable", "charges sociales",
            "commissaire aux comptes", "expert-comptable", "commissariat",
            "due diligence", "consolidation", "normes comptables",
            "reporting financier", "etats financiers", "normes ifrs",
            "normes syscohada", "syscoa", "bsc", "budget previsionnel",
            "controle budgetaire", "suivi des couts", "prix de revient",
            "couts standards", "ecarts", "analyse des ecarts",
            "erp comptable", "odoo", "cegid", "wave", "navision",
        ),
        indicators={
            "ifrs": 20, "ohada": 20, "audit externe": 20,
            "controle de gestion": 15, "sage": 10,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.35, "experience": 0.15,
            "education": 0.10, "complexity": 0.25, "leadership": 0.05,
        },
    ),

    Domain.BTP: DomainProfile(
        keywords=(
            "construction", "btp", "genie civil", "conducteur de travaux",
            "chantier", "maconnerie", "beton arme", "autocad",
            "planification", "lot technique", "metre", "vrd",
            "gros oeuvre", "second oeuvre", "infrastructure", "superstructure",
            "terrassement", "fondations", "charpente", "couverture",
            "plomberie", "electricite", "hvac", "climatisation",
            "revetement", "carrelage", "peinture batiment", "menuiserie",
            "architecture", "plan d'execution", "plan as-built",
            "dossier technique", "permis de construire", "cctp",
            "dpgf", "avant-metre", "appel d'offres btp", "budget chantier",
            "planning travaux", "gantt", "ms project", "primavera",
            "controle qualite chantier", "reception des travaux",
            "levee de reserves", "ged chantier", "etude de sol",
            "bureau de controle", "sps", "coordinateur sps",
            "inspection travaux", "suivi technique", "visa",
            "hse chantier", "plan phs", "prevention accidents",
            "bim", "revit", "maquette numerique",
        ),
        indicators={
            "conducteur de travaux senior": 20, "autocad": 15,
            "gestion multi-chantiers": 20, "vrd": 15, "beton arme": 10,
        },
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
        leadership_terms=("directeur de travaux", "chef de chantier", "ingenieur genie civil"),
    ),

    Domain.LEGAL: DomainProfile(
        keywords=(
            "droit", "juridique", "contrat", "contentieux", "procedure",
            "reglementation", "conformite", "ohada", "droit du travail",
            "droit des societes", "code civil", "tribunal",
            "avocat", "juriste", "conseil juridique", "veille juridique",
            "droit des affaires", "droit commercial", "droit fiscal",
            "droit penal", "droit administratif", "droit international",
            "arbitrage", "mediation", "conciliation", "negociation juridique",
            "acte juridique", "statuts", "pacte d'actionnaires",
            "protocole d'accord", "mou", "nda", "contrat de travail",
            "convention collective", "reglement interieur",
            "relations sociales", "licenciement", "rupture conventionnelle",
            "prud'hommes", "conseil d'etat", "cour d'appel",
            "due diligence juridique", "audit juridique", "conformite reglementaire",
            "protection des donnees", "rgpd", "propriete intellectuelle",
            "marque", "brevet", "droit d'auteur", "contrats internationaux",
            "droit ohada", "acte uniforme", "registre du commerce",
            "immatriculation", "dissolution", "liquidation",
        ),
        indicators={
            "droit ohada": 20, "contentieux complexe": 20,
            "contrats internationaux": 20, "droit des affaires": 15,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.35, "experience": 0.15,
            "education": 0.10, "complexity": 0.25, "leadership": 0.05,
        },
    ),

    Domain.EDUCATION: DomainProfile(
        keywords=(
            "enseignement", "formation", "pedagogie", "curriculum",
            "e-learning", "evaluation", "professeur", "ingenierie pedagogique",
            "formateur", "instructeur", "facilitateur", "coach",
            "enseignant", "tuteur", "mentor", "programme scolaire",
            "syllabus", "plan de cours", "objectifs pedagogiques",
            "competences", "evaluation formative", "evaluation sommative",
            "controle continu", "examen", "certification",
            "formation professionnelle", "developpement des competences",
            "formation initiale", "formation continue", "upskilling",
            "reskilling", "lms", "moodle", "google classroom",
            "blended learning", "classe inversee", "gamification",
            "pedagogie active", "apprentissage par projet",
            "differenciation pedagogique", "inclusion scolaire",
            "soutien scolaire", "remediation", "accompagnement",
            "orientation scolaire", "conseil pedagogique",
            "administration scolaire", "direction d'etablissement",
            "inspection pedagogique", "recherche en education",
            "these", "publication academique", "universite",
        ),
        indicators={
            "ingenierie pedagogique": 20, "e-learning": 15,
            "formation certifiante": 20,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.35, "experience": 0.15,
            "education": 0.10, "complexity": 0.25, "leadership": 0.05,
        },
    ),

    Domain.HOSPITALITY: DomainProfile(
        keywords=(
            "hotellerie", "restauration", "cuisine", "service en salle",
            "f&b", "sommellerie", "haccp", "reception", "housekeeping",
            "hotel", "restaurant", "brigade", "chef cuisinier", "chef de partie",
            "commis de cuisine", "patisserie", "boulangerie", "traiteur",
            "banquet", "evenementiel", "room service", "concierge",
            "reservation", "check-in", "check-out", "pms",
            "front office", "back office", "yield management",
            "revenue management", "taux d'occupation", "revpar",
            "guest experience", "satisfaction client", "qualite hoteliere",
            "classification hoteliere", "etoiles", "label qualite",
            "bar", "cave a vins", "cocktail", "mixologie",
            "menu", "carte", "food cost", "ratio matiere",
            "gestion des stocks restauration", "approvisionnement cuisine",
            "normes sanitaires", "hygiene alimentaire", "tracabilite",
            "plan de nettoyage", "desinfection", "controle qualite alimentaire",
            "maitre d'hotel", "directeur de restaurant", "directeur d'hotel",
            "manager f&b", "directeur hebergement",
        ),
        indicators={
            "etoile michelin": 20, "haccp": 15,
            "revenue management": 20, "classification hoteliere": 15,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.30, "experience": 0.35,
            "education": 0.18, "complexity": 0.20, "leadership": 0.05,
        },
    ),

    Domain.REAL_ESTATE: DomainProfile(
        keywords=(
            "immobilier", "transaction", "bail", "promotion immobiliere",
            "expertise", "copropriete", "amenagement", "negociation immobiliere",
            "agent immobilier", "mandataire immobilier", "courtier immobilier",
            "vente immobiliere", "location", "gestion locative", "syndic",
            "bien immobilier", "appartement", "villa", "immeuble", "terrain",
            "foncier", "lotissement", "programme immobilier", "vefa",
            "permis de construire", "plan local d'urbanisme", "plu",
            "dossier de financement", "pret immobilier", "credit immobilier",
            "taux immobilier", "apport personnel", "garantie hypothecaire",
            "acte de vente", "notaire", "compromis de vente",
            "promesse de vente", "due diligence immobiliere",
            "etat des lieux", "quittance de loyer", "charges locatives",
            "evaluation immobiliere", "estimation immobiliere", "valeur venale",
            "diagnostic immobilier", "dpe", "amiante", "plomb",
            "rehabilitation", "renovation", "travaux immobiliers",
            "gestion de patrimoine immobilier", "investissement locatif",
            "rendement locatif", "fiscalite immobiliere", "sci",
        ),
        indicators={
            "promotion immobiliere": 20, "expertise immobiliere": 20,
            "vente de programmes": 15,
        },
        weight_overrides={
            "keyword": 0.20, "semantic": 0.35, "experience": 0.25,
            "education": 0.08, "complexity": 0.07, "leadership": 0.05,
        },
    ),

    Domain.JOURNALISM: DomainProfile(
        keywords=(
            "journalisme", "redaction", "presse", "reportage", "medias",
            "enquete", "edition", "contenu editorial", "interview",
            "photojournalisme", "digital media",
            "journaliste", "redacteur", "chroniqueur", "correspondant",
            "grand reporter", "envoye special", "pigiste", "freelance",
            "news", "actualite", "breaking news", "fact-checking",
            "verification des faits", "sources journalistiques",
            "deontologie journalistique", "liberte de la presse",
            "journal", "magazine", "web media", "blog", "newsletter",
            "podcast", "radio", "television", "web tv", "streaming",
            "reseaux sociaux", "twitter journalisme", "community manager",
            "seo editorial", "trafic", "audience", "analytics",
            "editeur en chef", "redacteur en chef", "secretaire de redaction",
            "maquette presse", "une", "titraille", "photographie de presse",
            "agence de presse", "fil d'information", "depeche", "revue de presse",
            "veille medias", "relations presse", "attache de presse",
        ),
        indicators={
            "grand reportage": 20, "redacteur en chef": 20, "digital media": 15,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.40, "experience": 0.20,
            "education": 0.08, "complexity": 0.27, "leadership": 0.05,
        },
    ),

    Domain.MARKETING: DomainProfile(
        keywords=(
            "marketing", "communication", "seo", "sem", "google ads",
            "social media", "brand", "campagne", "inbound", "cms",
            "strategie digitale", "content marketing", "kpi",
            "marketing digital", "marketing operationnel", "marketing strategique",
            "etude de marche", "segmentation", "ciblage", "positionnement",
            "mix marketing", "4p", "persona", "customer journey",
            "tunnel de conversion", "acquisition", "retention", "fidelisation",
            "email marketing", "newsletter", "automation marketing",
            "marketing automation", "hubspot", "mailchimp", "sendinblue",
            "facebook ads", "instagram ads", "linkedin ads", "tiktok ads",
            "google analytics", "tag manager", "pixel", "a/b testing",
            "landing page", "conversion rate optimization", "cro",
            "affiliation", "influence marketing", "influenceur",
            "community management", "gestion des reseaux sociaux",
            "brand management", "notoriete", "image de marque",
            "plan de communication", "brief creatif", "message marketing",
            "rp", "relations publiques", "evenementiel marketing",
            "trade marketing", "merchandising", "plv",
        ),
        indicators={
            "strategie omnicanale": 20, "google ads": 15,
            "brand management": 20, "inbound marketing": 15,
            "marketing automation": 20,
        },
        weight_overrides={
            "keyword": 0.25, "semantic": 0.35, "experience": 0.18,
            "education": 0.07, "complexity": 0.10, "leadership": 0.05,
        },
    ),

    Domain.HR: DomainProfile(
        keywords=(
            "recrutement", "paie", "gpec", "sirh", "droit du travail",
            "formation", "relations sociales", "talent management",
            "onboarding", "evaluation des performances", "remuneration",
            "ressources humaines", "gestion des ressources humaines",
            "gestion des talents", "marque employeur", "employer branding",
            "sourcing candidats", "entretien de recrutement",
            "assessment center", "integration", "periode d'essai",
            "plan de formation", "besoin en formation", "cpf",
            "plan de developpement", "coaching", "feedback 360",
            "entretien annuel", "entretien professionnel",
            "gestion de carriere", "mobilite interne", "succession planning",
            "contrat de travail", "avenant", "rupture conventionnelle",
            "licenciement", "procedure disciplinaire", "sanctions",
            "delegues du personnel", "comite social et economique", "cse",
            "syndicats", "negociation collective", "accord d'entreprise",
            "reglement interieur", "politique rh", "charte rh",
            "absenteisme", "turnover", "taux de rotation", "engagement",
            "qvt", "qualite de vie au travail", "bien-etre", "rsst",
            "diversite", "inclusion", "egalite professionnelle",
        ),
        indicators={
            "gpec": 20, "sirh": 15, "negociation syndicale": 20,
            "talent management": 15, "remuneration variable": 10,
        },
        weight_overrides={
            "keyword": 0.22, "semantic": 0.33, "experience": 0.20,
            "education": 0.10, "complexity": 0.10, "leadership": 0.05,
        },
        leadership_terms=("drh", "directeur des ressources humaines", "hr business partner"),
    ),

    Domain.HEALTH: DomainProfile(
        keywords=(
            "medecine", "soins infirmiers", "pharmacie", "chirurgie",
            "diagnostic", "patient", "urgences", "bloc operatoire",
            "radiologie", "biologie medicale", "clinique", "protocole medical",
            "medecin", "infirmier", "infirmiere", "aide-soignant",
            "sage-femme", "kinesitherapeute", "orthophoniste",
            "psychologue", "psychiatre", "cardiologue", "pediatre",
            "dermatologue", "ophtalmologue", "gynecologue", "urologue",
            "orthopediste", "anesthesiste", "reanimation", "soins intensifs",
            "unite de soins", "consultation", "hospitalisation",
            "ambulatoire", "telemedecine", "dossier medical",
            "dossier patient informatise", "dpi", "prescription",
            "ordonnance", "traitement", "therapie", "medicament",
            "pharmacovigilance", "essai clinique", "recherche medicale",
            "sante publique", "epidemiologie", "prevention",
            "vaccination", "depistage", "promotion de la sante",
            "hygiene hospitaliere", "infection nosocomiale",
            "sterilisation", "biomedicale", "dispositif medical",
        ),
        indicators={
            "specialite medicale": 25, "chef de service": 20,
            "recherche clinique": 20, "urgences": 15,
        },
        weight_overrides={
            "keyword": 0.04, "semantic": 0.30, "experience": 0.30,
            "education": 0.23, "complexity": 0.10, "leadership": 0.03,
        },
    ),

    Domain.GENERAL_SERVICES: DomainProfile(
        keywords=(
            "facility management", "maintenance", "nettoyage", "gardiennage",
            "prestataires", "services generaux", "parc automobile", "hse",
            "gestion des installations", "facilities", "building management",
            "entretien des locaux", "proprete", "nettoyage industriel",
            "securite des batiments", "controle d'acces", "videosurveillance",
            "alarme incendie", "securite incendie", "evacuation",
            "maintenance preventive", "maintenance curative",
            "maintenance corrective", "gmao", "ticketing maintenance",
            "prestataires de services", "contrats de maintenance",
            "appel d'offres prestataires", "sla prestataires",
            "espaces verts", "jardinage", "entretien exterieur",
            "gestion des dechets", "tri selectif", "developpement durable",
            "flotte automobile", "gestion des vehicules", "carnet d'entretien",
            "assurance flotte", "telematique", "gps",
            "energie", "eau", "electricite", "gaz", "fluides",
            "reduction des couts energie", "audit energetique",
            "plan de prevention", "document unique", "risques professionnels",
            "espace de travail", "amenagement des bureaux",
        ),
        indicators={"facility management": 20, "gestion prestataires": 15},
        weight_overrides={
            "keyword": 0.20, "semantic": 0.35, "experience": 0.25,
            "education": 0.08, "complexity": 0.07, "leadership": 0.05,
        },
    ),

    Domain.INTERN: DomainProfile(
        keywords=(
            "stage", "alternance", "apprentissage", "projet academique",
            "memoire", "rapport de stage",
            "stagiaire", "alternant", "apprenti", "etudiant",
            "licence", "master", "bts", "dut", "bachelor",
            "premiere experience", "debut de carriere", "junior",
            "encadrement", "tuteur de stage", "maitre d'apprentissage",
            "projet de fin d'etudes", "pfe", "soutenance", "jury",
            "convention de stage", "contrat d'apprentissage",
            "contrat de professionnalisation", "formation en alternance",
            "centre de formation", "cfai", "cfa",
            "competences transversales", "savoir-etre", "soft skills",
            "motivation", "curiosite", "rigueur", "ponctualite",
            "travail en equipe", "adaptabilite", "autonomie",
            "langue etrangere", "anglais scolaire", "niveau b2",
            "excel basique", "word traitement de texte",
            "initiation professionnelle", "decouverte metier",
            "immersion professionnelle", "projet transversal",
            "stage longue duree", "stage de fin d'etudes",
        ),
        indicators={"projet transversal": 10, "stage longue duree": 15},
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
    ),

    Domain.TOURISM: DomainProfile(
        keywords=(
            "tourisme", "voyage", "agence de voyage", "guide touristique",
            "billetterie", "crm touristique", "gds", "amadeus",
            "tour operateur", "to", "voyagiste", "circuit touristique",
            "package voyage", "sejour", "excursion", "croisiere",
            "tourisme d'affaires", "mice", "congres", "seminaire",
            "tourisme balneaire", "tourisme culturel", "ecotourisme",
            "tourisme solidaire", "tourisme de luxe", "tourisme local",
            "office du tourisme", "destination marketing",
            "booking", "reservation en ligne", "hebergement touristique",
            "hotel", "auberge de jeunesse", "gite", "airbnb", "campsite",
            "transport touristique", "transfert aeroport",
            "guide de voyage", "interprete touristique",
            "visa", "passeport", "assurance voyage", "assistance",
            "galileo", "sabre", "worldspan", "travelport",
            "tarification aerienne", "yield aerien", "billet d'avion",
            "tourisme medical", "wellness tourism", "agritourisme",
            "itineraire", "road trip", "travel blogger",
        ),
        indicators={"amadeus": 20, "gds": 15, "tourisme international": 20},
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
    ),

    Domain.TRANSPORT: DomainProfile(
        keywords=(
            "transport", "logistique", "chauffeur", "fret", "douane",
            "transit", "affretement", "tms", "declaration en douane",
            "incoterms", "fleet management",
            "transport routier", "transport maritime", "transport aerien",
            "transport ferroviaire", "multimodal", "intermodal",
            "commissionnaire de transport", "freight forwarder",
            "transitaire", "freight broker", "courtier de fret",
            "bill of lading", "connaissement", "airway bill", "cmr",
            "import", "export", "dedouanement", "tarif douanier",
            "nomenclature douaniere", "hs code", "origine des marchandises",
            "entrepot sous douane", "mise a la consommation",
            "fret aerien", "fret maritime", "conteneur", "vrac",
            "palettisation", "emballage", "conditionnement",
            "messagerie", "express", "courrier", "dernier kilometre",
            "livraison", "tournee", "optimisation des tournees",
            "routing", "gps", "telematique", "geolocalisation",
            "reglementation transport", "adr", "matieres dangereuses",
            "conducteur poids lourd", "permis de conduire",
        ),
        indicators={
            "incoterms": 20, "tms": 20,
            "affretement international": 20, "douane": 15, "fleet management": 15,
        },
        weight_overrides={
            "keyword": 0.25, "semantic": 0.30, "experience": 0.25,
            "education": 0.08, "complexity": 0.07, "leadership": 0.05,
        },
    ),

    Domain.SOCIAL: DomainProfile(
        keywords=(
            "travail social", "ong", "humanitaire", "developpement communautaire",
            "action sociale", "volontariat", "projet social", "plaidoyer",
            "protection sociale", "assistance aux personnes vulnerables",
            "assistant social", "travailleur social", "educateur specialise",
            "animateur socioculturel", "coordinateur", "chef de projet social",
            "benevolat", "service civique", "corps de la paix",
            "droits humains", "droits de l'homme", "genre", "egalite",
            "inclusion sociale", "lutte contre la pauvrete",
            "protection de l'enfance", "violences basees sur le genre",
            "vbg", "autonomisation des femmes", "jeunesse",
            "developpement local", "participation communautaire",
            "diagnostic communautaire", "enquete sociale",
            "gestion de cas", "case management", "suivi beneficiaires",
            "rapport de mission", "monitoring evaluation", "me",
            "bailleurs de fonds", "donors", "ue", "usaid", "banque mondiale",
            "gestion de projet ong", "cadre logique", "logframe",
            "rapport narratif", "rapport financier bailleur",
            "appel a propositions", "concept note", "proposal writing",
            "terrain humanitaire", "urgence humanitaire", "camp de refugies",
        ),
        indicators={
            "gestion de projet ong": 20, "plaidoyer": 15,
            "financement bailleur": 20, "developpement communautaire": 15,
        },
        weight_overrides={
            "keyword": 0.20, "semantic": 0.40, "experience": 0.18,
            "education": 0.12, "complexity": 0.05, "leadership": 0.05,
        },
    ),

    Domain.NETWORKS: DomainProfile(
        keywords=(
            "reseau", "cisco", "firewall", "switch", "vpn", "infrastructure",
            "cybersecurite", "pentest", "soc", "ids", "ips", "telecoms",
            "5g", "lte", "sd-wan",
            "routeur", "vlan", "tcp/ip", "dns", "dhcp", "bgp", "ospf",
            "mpls", "wan", "lan", "wifi", "bluetooth", "nfc",
            "fortinet", "palo alto", "checkpoint", "juniper",
            "sophos", "stormshield", "snort", "suricata",
            "siem", "splunk", "elk", "graylog", "qradar",
            "edr", "ndr", "xdr", "zero trust", "ztna",
            "identity access management", "iam", "ldap", "active directory",
            "okta", "sso", "mfa", "pki", "certificats ssl tls",
            "cloud networking", "aws vpc", "azure networking",
            "nist", "iso 27001", "pci dss", "rgpd technique",
            "test d'intrusion", "vulnerability assessment", "ctf",
            "malware analysis", "threat intelligence", "incident response",
            "voip", "sip", "unified communications", "uc",
            "telecommunications", "fibre optique", "4g", "backbone",
        ),
        indicators={
            "pentest": 20, "soc": 20, "sd-wan": 20,
            "certifie ccna": 20, "certifie cissp": 25,
        },
        weight_overrides={
            "keyword": 0.25, "semantic": 0.30, "experience": 0.20,
            "certification": 0.10, "complexity": 0.10,
            "education": 0.03, "leadership": 0.02,
        },
    ),

    Domain.ENGINEERING: DomainProfile(
        keywords=(
            "mecanique", "electrique", "hydraulique", "conception", "autocad",
            "solidworks", "catia", "bureau d'etudes", "simulation", "erd",
            "maintenance preventive",
            "genie mecanique", "genie electrique", "genie industriel",
            "thermodynamique", "resistance des materiaux", "rdm",
            "elements finis", "fem", "cfm", "cfd",
            "prototypage", "fabrication", "procedes de fabrication",
            "usinage", "soudure", "chaudronnerie", "tuyauterie",
            "electronique", "automatisme", "plc", "api",
            "siemens", "schneider", "allen bradley", "hmi", "scada",
            "instrumentation", "capteur", "mesure", "calibration",
            "maintenance industrielle", "fiabilite", "mttf", "mttr",
            "gmao", "maintenance totale", "tpm",
            "gestion de projet technique", "planning", "jalons",
            "normes techniques", "iso", "en", "astm", "asme",
            "certification de produit", "homologation", "essais",
            "calcul de structure", "dimensionnement", "contraintes",
            "tolerances", "metrologie", "controle qualite",
            "audit technique", "revue de conception",
        ),
        indicators={
            "catia": 20, "simulation cfd": 20,
            "certification iso": 15, "projet r&d": 15,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.30, "experience": 0.30,
            "certification": 0.05, "complexity": 0.15,
            "education": 0.07, "leadership": 0.02,
        },
    ),

    Domain.SCIENCE: DomainProfile(
        keywords=(
            "laboratoire", "protocole", "experimentation", "publication",
            "these", "r&d", "chimie", "biologie", "statistiques",
            "matlab", "spss", "r", "python",
            "recherche scientifique", "sciences fondamentales",
            "sciences appliquees", "physique", "mathematiques",
            "biochimie", "microbiologie", "genetique", "immunologie",
            "virologie", "botanique", "zoologie", "ecologie",
            "chimie organique", "chimie analytique", "chimie physique",
            "chromatographie", "spectroscopie", "electrophorese", "pcr",
            "cell culture", "culture cellulaire", "flow cytometry",
            "imagerie medicale", "histologie", "anatomopathologie",
            "analyse de donnees", "big data", "machine learning scientifique",
            "modelisation", "simulation numerique", "calcul scientifique",
            "hpc", "cluster", "publication indexee", "peer review",
            "brevet", "propriete intellectuelle scientifique",
            "financement de la recherche", "anr", "h2020",
            "rapport d'avancement", "revue bibliographique",
            "etat de l'art", "doctorat", "post-doctorat", "habilitation",
        ),
        indicators={
            "publication indexee": 25, "these": 20,
            "brevet": 20, "financement recherche": 15,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.30, "experience": 0.20,
            "certification": 0.05, "complexity": 0.15,
            "education": 0.15, "leadership": 0.05,
        },
    ),

    Domain.ENERGY: DomainProfile(
        keywords=(
            "petrole", "mines", "forage", "geologie", "raffinage",
            "energie renouvelable", "solaire", "hydraulique", "reservoir",
            "hse petrolier", "offshore",
            "gaz naturel", "gaz de petrole", "gnl", "gpl",
            "pipeline", "transport d'hydrocarbures", "stockage",
            "exploration petroliere", "sismique", "geophysique",
            "petrophy sique", "diagraphie", "carottage",
            "drilling", "well completion", "stimulation",
            "production petroliere", "enhanced oil recovery", "eor",
            "reservoir simulation", "modelisation de reservoir",
            "eolien", "eolienne offshore", "solaire photovoltaique",
            "solaire thermique", "biomasse", "biogaz",
            "geothermie", "hydroelectricite", "stockage d'energie",
            "batterie", "hydrogene", "pile a combustible",
            "reseau electrique", "smart grid", "power plant",
            "centrale thermique", "centrale solaire", "centrale hydraulique",
            "mining", "extraction miniere", "minerai", "or", "diamant",
            "cuivre", "bauxite", "phosphate", "traitement des minerais",
            "metallurgie", "hydrometallurgie", "pyrometallurgie",
        ),
        indicators={
            "offshore": 20, "reservoir engineering": 25,
            "hse petrolier": 20, "energie solaire": 15,
        },
        weight_overrides={
            "keyword": 0.25, "semantic": 0.30, "experience": 0.25,
            "certification": 0.05, "complexity": 0.10,
            "education": 0.03, "leadership": 0.02,
        },
    ),

    Domain.INDUSTRY: DomainProfile(
        keywords=(
            "production", "usine", "lean manufacturing", "5s", "kaizen",
            "maintenance industrielle", "chaine de montage", "plc",
            "automatisme", "erp", "ordonnancement",
            "chef de production", "responsable de production",
            "directeur d'usine", "responsable usine",
            "amelioration continue", "amelioration des processus",
            "six sigma", "black belt", "green belt", "vsm",
            "tpm", "smed", "poka yoke", "jidoka",
            "takt time", "cycle time", "efficacite globale", "trs", "oee",
            "controle de production", "suivi de production",
            "planning de production", "ordonnancement de fabrication",
            "gestion de la production", "mrp", "mrp2",
            "qualite de production", "controle qualite",
            "non-conformite", "rebut", "retraitement",
            "tracabilite", "gestion des lots", "serialisation",
            "emballage industriel", "conditionnement",
            "gestion des flux", "flux physiques",
            "gestion des outillages", "gestionnaire outillage",
            "securite industrielle", "epi", "plan de prevention",
            "habilitations electriques", "caces", "travail en hauteur",
        ),
        indicators={
            "lean manufacturing": 20, "automatisme plc": 20,
            "tpm": 15, "six sigma": 25,
        },
        weight_overrides={
            "keyword": 0.25, "semantic": 0.30, "experience": 0.25,
            "certification": 0.05, "complexity": 0.10,
            "education": 0.03, "leadership": 0.02,
        },
    ),

    Domain.QHSE: DomainProfile(
        keywords=(
            "hse", "qualite", "iso 9001", "iso 14001", "ohsas 18001",
            "iso 45001", "audit qualite", "non-conformite", "plan de prevention",
            "document unique", "analyse des risques",
            "responsable qhse", "directeur qhse", "animateur securite",
            "ingenieur hse", "technicien qse",
            "systeme de management", "smq", "sme", "sms",
            "certification", "recertification", "surveillance", "tierce partie",
            "accreditation", "cofrac", "iatf 16949", "iso 13485",
            "iso 22000", "haccp", "brc", "ifs",
            "risque professionnel", "evaluation des risques", "duer",
            "plan d'action", "suivi des actions correctives",
            "action preventive", "amelioration continue",
            "indicateurs qualite", "kpi qualite", "tableau de bord qhse",
            "revue de direction", "audit interne", "audit externe",
            "programme d'audit", "rapport d'audit",
            "accident du travail", "enquete accident", "arbre des causes",
            "presqu'accident", "near miss", "reporting securite",
            "formation securite", "sensibilisation", "causerie securite",
            "permit to work", "permis de travail", "lock out tag out",
            "environnement", "emissions", "dechets industriels",
            "sol pollue", "depollution", "veille reglementaire",
        ),
        indicators={
            "iso 9001": 20, "iso 45001": 20,
            "audit tierce partie": 20, "analyse des risques": 15,
        },
        weight_overrides={
            "keyword": 0.25, "semantic": 0.30, "experience": 0.20,
            "certification": 0.10, "complexity": 0.10,
            "education": 0.03, "leadership": 0.02,
        },
    ),
}

# -----------------------------------------------------------------------
# Pré-normalise tous les profils une seule fois au chargement du module
# -----------------------------------------------------------------------
_DOMAIN_PROFILES: dict[Domain, DomainProfile] = {
    domain: DomainProfile(
        keywords=_norm_keywords(profile.keywords),
        indicators=_norm_indicators(profile.indicators),
        weight_overrides=profile.weight_overrides,
        leadership_terms=_norm_keywords(profile.leadership_terms),
    )
    for domain, profile in _DOMAIN_PROFILES_RAW.items()
}

_FALLBACK_PROFILE = DomainProfile()

# =============================================================================
# PERTINENCE DU DIPLÔME PAR DOMAINE
# =============================================================================

_EDUCATION_RELEVANCE: dict[Domain, tuple[str, ...]] = {
    Domain.ACCOUNTING: ("comptabilite", "finance", "gestion", "fiscalite", "ohada", "ifrs", "sage"),
    Domain.BANKING:    ("banque", "finance", "economie", "actuariat"),
    Domain.TECH:       ("informatique", "developpement", "ingenieur", "systemes"),
    Domain.MARKETING:  ("marketing", "communication", "digital"),
    Domain.HR:         ("ressources humaines", "rh"),
    Domain.BTP:        ("genie civil", "batiment", "architecture"),
    Domain.AGRI:       ("agronomie", "agriculture"),
    Domain.LEGAL:      ("droit", "juridique"),
    Domain.HEALTH:     ("medecine", "pharmacie"),
    Domain.SALES:      ("commerce", "vente"),
}


# =============================================================================
# DÉTECTION DU NIVEAU HIÉRARCHIQUE
# =============================================================================

def detect_hierarchy_level(title_lower: str) -> HierarchyLevel:
    # title_lower doit déjà être normalisé via _norm()
    for level in [HierarchyLevel.DIRECTION, HierarchyLevel.MANAGER_SENIOR,
                  HierarchyLevel.MANAGER_INTERMEDIAIRE]:
        for marker in HIERARCHY_TITLE_MARKERS[level]:
            if marker in title_lower:
                return level
    return HierarchyLevel.COLLABORATEUR


def detect_professional_level(cv_text: str, job_title: str = "") -> ProfessionalLevel:
    text = _norm(f"{cv_text} {job_title}")
    hier = detect_hierarchy_level(text)
    return _HIER_TO_PROF.get(hier, ProfessionalLevel.MID_LEVEL)


# =============================================================================
# CONSTRUCTION DES TEXTES DE SCORING
# =============================================================================

def _build_cv_text(cv: dict[str, Any]) -> str:
    ai_data: dict[str, Any] = {}
    raw_ai = cv.get("ai_extracted_data")
    if isinstance(raw_ai, str):
        try:
            ai_data = json.loads(raw_ai)
        except (json.JSONDecodeError, ValueError):
            pass
    elif isinstance(raw_ai, dict):
        ai_data = raw_ai

    work_history = (
        safe_dict_list(cv.get("work_history"))
        or safe_dict_list(ai_data.get("work_history"))
    )
    projects = (
        safe_dict_list(cv.get("projects"))
        or safe_dict_list(ai_data.get("projects"))
    )
    education = (
        safe_dict_list(cv.get("education"))
        or safe_dict_list(ai_data.get("education"))
    )
    skills = (
        safe_list(cv.get("skills"))
        or safe_list(ai_data.get("skills"))
    )
    certifications = (
        safe_list(cv.get("certifications"))
        or safe_list(ai_data.get("certifications"))
    )

    parts: list[str] = [
        str(cv.get("summary", "") or ai_data.get("summary", "")),
        str(cv.get("current_position", "") or ai_data.get("current_position", "")),
        " ".join(skills),
        " ".join(certifications),
    ]
    for job in work_history:
        parts += [
            str(job.get("title", "")),
            str(job.get("company", "")),
            str(job.get("description", "")),
        ]
    for project in projects:
        parts += [
            str(project.get("name", "")),
            str(project.get("tech", "")),
            str(project.get("description", "")),
            str(project.get("complexity", "")),
        ]
    for edu in education:
        parts += [
            str(edu.get("degree", "")),
            str(edu.get("institution", "")),
        ]
    cv_raw = cv.get("cv_raw_text", "")
    if cv_raw:
        parts.append(str(cv_raw)[:1000])

    return _norm(" ".join(filter(None, parts)))


def _build_job_text(title: str, requirements: str) -> str:
    return _norm(f"{title} {requirements}")


# =============================================================================
# CALCUL DES ANNÉES D'EXPÉRIENCE
# =============================================================================

def infer_experience_years(work_history: list[Any]) -> float:
    total_months = 0
    for item in work_history:
        if not isinstance(item, dict):
            continue
        duration = item.get("duration_months")
        if isinstance(duration, (int, float)) and duration > 0:
            total_months += int(duration)
            continue
        start = item.get("start_date")
        end   = item.get("end_date")
        if not start:
            continue
        try:
            start_str = start[:7] if len(start) >= 7 else f"{start[:4]}-01"
            if end and len(end) >= 7:
                end_str = end[:7]
            elif end and len(end) >= 4:
                end_str = f"{end[:4]}-01"
            else:
                end_str = None
            start_dt = datetime.strptime(start_str, "%Y-%m")
            end_dt   = datetime.strptime(end_str, "%Y-%m") if end_str else datetime.utcnow()
            months   = (end_dt.year - start_dt.year) * 12 + end_dt.month - start_dt.month
            total_months += max(months, 0)
        except (ValueError, TypeError):
            continue
    return round(total_months / 12, 1)


# =============================================================================
# MATCHING MOTS-CLÉS — CORRECTION v3.1
# =============================================================================
#
# ANCIEN comportement (bugué) :
#   - Extrayait les mots-clés du JOB TEXT via profile.keywords
#   - Si le job text est court/peu dense → job_kws = {} → score 50 ou 0
#   - Si le job text est modérément dense mais sans les bons termes → 0
#
# NOUVEAU comportement :
#   - Pour les domaines non-tech : approche CV-centric.
#     On mesure combien de mots-clés du profil sont présents dans le CV.
#     On utilise le job text UNIQUEMENT pour affiner la liste "requis"
#     (les keywords du profil qui sont aussi dans le job), ou l'ensemble
#     complet si le job est trop pauvre.
#   - Pour les domaines tech : comportement inchangé (keywords tech bien
#     présents dans les offres d'emploi).
#
# =============================================================================

def _extract_tech_keywords(text: str) -> set[str]:
    return {kw for kw, pat in _KW_PATTERNS.items() if pat.search(text)}


def _extract_keywords_from_set(text: str, keywords: tuple[str, ...]) -> set[str]:
    """Retourne les mots-clés (déjà normalisés) présents dans text (déjà normalisé)."""
    result: set[str] = set()
    for kw in keywords:
        if " " in kw:
            if kw in text:
                result.add(kw)
        else:
            # word-boundary simulé : vérifie que le mot n'est pas collé à d'autres lettres
            idx = text.find(kw)
            while idx != -1:
                before_ok = (idx == 0 or not text[idx - 1].isalpha())
                after_ok  = (idx + len(kw) == len(text) or not text[idx + len(kw)].isalpha())
                if before_ok and after_ok:
                    result.add(kw)
                    break
                idx = text.find(kw, idx + 1)
    return result


def _keyword_match(
    cv_text  : str,
    job_text : str,
    keywords : tuple[str, ...] | None = None,
    is_tech  : bool = False,
) -> dict[str, Any]:
    """
    CORRECTION v3.1 — logique CV-centric pour domaines non-tech.

    Pour les domaines tech (is_tech=True) :
      On extrait les mots-clés du CV ET du job (offre riche en termes tech).
      Score = intersection / job_keywords.

    Pour les domaines non-tech (is_tech=False) :
      On extrait les mots-clés du CV ET du job.
      Si le job contient suffisamment de keywords (>=3), on score sur ceux-là.
      Sinon (job trop pauvre) on score sur l'ensemble des keywords du profil
      présents dans le CV, normalisé sur le total du profil.
      Cela évite un score 0 quand le job text ne contient aucun keyword.
    """
    if is_tech or keywords is None:
        cv_kws  = _extract_tech_keywords(cv_text)
        job_kws = _extract_tech_keywords(job_text)
        matched = sorted(cv_kws & job_kws)
        missing = sorted(job_kws - cv_kws)
        score   = 50.0 if not job_kws else (len(matched) / len(job_kws)) * 100
        return {"score": _clamp(score), "matched": matched, "missing": missing}

    # --- Domaine non-tech : approche CV-centric ---
    cv_kws  = _extract_keywords_from_set(cv_text,  keywords)
    job_kws = _extract_keywords_from_set(job_text, keywords)

    if len(job_kws) >= 3:
        # Le job est suffisamment dense : on mesure l'alignement CV ↔ job
        matched = sorted(cv_kws & job_kws)
        missing = sorted(job_kws - cv_kws)
        score   = (len(matched) / len(job_kws)) * 100
    else:
        # Le job est trop pauvre : on mesure la couverture du CV sur le profil entier
        total_profile_kws = len(keywords)
        matched = sorted(cv_kws)
        missing = []  # on ne peut pas déterminer ce qui "manque" depuis le job
        score   = (len(cv_kws) / max(total_profile_kws, 1)) * 100 if cv_kws else 0.0
        # Normalise : un CV couvrant 20 % du profil → bon score (scale ×3, cap 100)
        score   = min(score * 3.0, 100.0)

    return {"score": _clamp(score), "matched": matched, "missing": missing}


# =============================================================================
# SCORE SÉMANTIQUE — CORRECTION v3.1
# =============================================================================
#
# Deux niveaux de fallback :
#   1. Modèle neural SentenceTransformer (si disponible)
#   2. Similarité cosinus TF-IDF via sklearn (toujours disponible)
#
# Le flag _neural_model_available mémorise si le modèle a déjà échoué
# pour ne pas retenter à chaque appel.
#
# =============================================================================

def _tfidf_cosine_similarity(text_a: str, text_b: str) -> float:
    """
    Fallback sémantique : similarité cosinus TF-IDF.
    Fonctionne sans GPU ni téléchargement de modèle.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as sk_cosine

        vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=1,
            max_features=5000,
        )
        tfidf = vectorizer.fit_transform([text_a, text_b])
        sim   = sk_cosine(tfidf[0], tfidf[1])[0][0]
        return _clamp(float(sim) * 100)
    except Exception as exc:
        print(f"[scoring] TF-IDF fallback error: {exc}")
        return 0.0


def _semantic_score(cv_text: str, job_text: str) -> float:
    global _neural_model_available

    cv_text  = cv_text[:4000]
    job_text = job_text[:2000]

    if not cv_text or not job_text:
        return 0.0

    # Tente le modèle neural seulement si pas encore marqué indisponible
    with _neural_model_lock:
        try_neural = (_neural_model_available is not False)

    if try_neural:
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            model = _get_model()
            if model is not None:
                embeddings = model.encode(
                    [cv_text, job_text],
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
                similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
                with _neural_model_lock:
                    _neural_model_available = True
                return _clamp(float(similarity) * 100)
            else:
                with _neural_model_lock:
                    _neural_model_available = False
        except Exception as exc:
            print(f"[scoring] Neural semantic error (switching to TF-IDF): {exc}")
            with _neural_model_lock:
                _neural_model_available = False

    # Fallback TF-IDF
    return _tfidf_cosine_similarity(cv_text, job_text)


# =============================================================================
# SCORERS PAR DIMENSION
# =============================================================================

def _experience_score(candidate_years: float, required_years: float) -> float:
    try:
        candidate_years = float(candidate_years or 0)
        required_years  = float(required_years  or 0)
        if required_years <= 0:
            return 100.0
        if candidate_years >= required_years * 2:
            return 100.0
        if candidate_years >= required_years:
            surplus = (candidate_years - required_years) / required_years
            return _clamp(70.0 + 30.0 * min(surplus, 1.0))
        return _clamp((candidate_years / required_years) * 100)
    except Exception:
        return 0.0


def _certification_score(cv_text: str, domain: Domain | None = None) -> float:
    text = _norm(cv_text)
    total_weight = 0.0
    for cert_key, cert_info in CERTIFICATION_REGISTRY.items():
        cert_key_norm = _strip_accents(cert_key.lower())
        if cert_key_norm in text:
            w = cert_info["weight"]
            if domain and cert_info["domain"] == domain:
                w *= 1.3
            total_weight += w
    return _clamp(min(total_weight / 3.0, 1.0) * 100)


def _education_relevance_score(cv_text: str, domain: Domain, job_text: str = "") -> float:
    text    = _norm(f"{cv_text} {job_text}")
    matches = sum(1 for kw in _EDUCATION_RELEVANCE.get(domain, ()) if kw in text)
    if matches >= 2:
        return 95.0
    if matches == 1:
        return 75.0
    return 40.0


def _education_score(
    cv_text : str,
    domain  : Domain,
    job_text: str = "",
    level   : ProfessionalLevel = ProfessionalLevel.MID_LEVEL,
) -> float:
    cv_lower = _norm(cv_text)
    if "doctorat" in cv_lower or "phd" in cv_lower:
        level_score = 100.0
    elif any(x in cv_lower for x in ("master", "mastere", "ingenieur")):
        level_score = 85.0
    elif any(x in cv_lower for x in ("licence", "bachelor", "bts", "dut")):
        level_score = 70.0
    else:
        level_score = 50.0

    relevance = _education_relevance_score(cv_text, domain, job_text)
    final     = (level_score * 0.6) + (relevance * 0.4)
    if level in (ProfessionalLevel.DIRECTOR, ProfessionalLevel.EXECUTIVE):
        final = min(100.0, final * 1.1)
    return _clamp(final)


def _leadership_score(
    cv_text     : str,
    extra_terms : tuple[str, ...] = (),
    past_titles : list[str] | None = None,
) -> float:
    text = _norm(cv_text)

    # 1. Verbes d'action (déjà sans accents grâce à _norm)
    verb_scores = [w for verb, w in LEADERSHIP_ACTION_VERBS.items() if verb in text]
    verb_score  = max(verb_scores) if verb_scores else 0.0
    if len(verb_scores) >= 3:
        verb_score = min(verb_score + 0.1, 1.0)

    # 2. Mots-clés classiques
    all_terms  = LEADERSHIP_TERMS + extra_terms
    kw_matches = sum(1 for t in all_terms if _norm(t) in text)
    kw_score   = min(kw_matches * 0.2, 1.0)

    # 3. Titres passés
    title_score = 0.0
    if past_titles:
        for title in past_titles:
            detected = detect_hierarchy_level(_norm(title))
            if detected in (HierarchyLevel.MANAGER_SENIOR, HierarchyLevel.DIRECTION):
                title_score = max(title_score, 0.8)
            elif detected == HierarchyLevel.MANAGER_INTERMEDIAIRE:
                title_score = max(title_score, 0.5)

    combined = 0.6 * verb_score + 0.2 * kw_score + 0.2 * title_score
    return _clamp(combined * 100)


def _complexity_score(
    cv_text   : str,
    indicators: dict[str, int] | None = None,
) -> float:
    # cv_text est déjà normalisé (sans accents) par _norm()
    source = indicators if indicators is not None else COMPLEXITY_INDICATORS
    # Normalise aussi les clés des indicateurs si nécessaire
    norm_source = {_strip_accents(k.lower()): v for k, v in source.items()}
    return _clamp(sum(pts for term, pts in norm_source.items() if term in cv_text))


def _language_score(cv_text: str) -> float:
    text  = _norm(cv_text)
    score = 50.0
    if any(x in text for x in ("anglais", "english", "toeic", "b2", "c1", "fluent", "courant")):
        score += 30
    if any(x in text for x in ("espagnol", "portugais")):
        score += 10
    return _clamp(score)


# =============================================================================
# GESTION DES POIDS
# =============================================================================

def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: round(v / total, 4) for k, v in weights.items()}


def _resolve_weights(
    base     : dict[str, float],
    overrides: dict[str, float],
) -> dict[str, float]:
    return _normalize_weights({**base, **overrides})


def _get_weights_for_level(
    base : dict[str, float],
    level: ProfessionalLevel,
) -> dict[str, float]:
    weights = base.copy()
    if level in (ProfessionalLevel.DIRECTOR, ProfessionalLevel.EXECUTIVE):
        weights.update({
            "leadership": 0.15, "education": 0.15,
            "experience": 0.22, "complexity": 0.20,
        })
    elif level == ProfessionalLevel.MANAGER:
        weights.update({"leadership": 0.12, "education": 0.13, "experience": 0.20})
    elif level == ProfessionalLevel.JUNIOR:
        weights.update({"education": 0.18, "leadership": 0.03, "complexity": 0.22})
    return _normalize_weights(weights)


def _load_weights(supabase=None) -> dict[str, float]:
    if supabase is None:
        with _weights_lock:
            return dict(_active_weights)
    try:
        resp   = (
            supabase.table("app_config")
            .select("value")
            .eq("key", "ats_weights")
            .single()
            .execute()
        )
        stored = resp.data and resp.data.get("value")
        if stored:
            if isinstance(stored, str):
                stored = json.loads(stored)
            if isinstance(stored, dict) and all(k in stored for k in DEFAULT_WEIGHTS):
                return {k: float(v) for k, v in stored.items()}
    except Exception as exc:
        print(f"[scoring] Failed to load weights from DB: {exc}")
    with _weights_lock:
        return dict(_active_weights)


def _save_weights(weights: dict[str, float], supabase=None) -> None:
    if supabase is None:
        return
    try:
        supabase.table("app_config").upsert(
            {"key": "ats_weights", "value": weights},
            on_conflict="key",
        ).execute()
    except Exception as exc:
        print(f"[scoring] Failed to save weights to DB: {exc}")


@dataclass
class FeedbackRecord:
    candidate_id    : str
    job_title       : str
    predicted_score : float
    actual_outcome  : str
    actual_rating   : float
    timestamp       : str = ""
    notes           : str = ""


def update_weights_from_feedback(
    *,
    supabase        : Any                      = None,
    candidate_id    : str | None               = None,
    liked           : bool                     = True,
    dimension_scores: dict[str, float] | None  = None,
    feedback_data   : dict[str, float] | None  = None,
    feedback_records: list[FeedbackRecord] | None = None,
    learning_rate   : float = 0.01,
) -> None:
    global _active_weights
    weights = _load_weights(supabase)

    if feedback_records:
        new_w = dict(weights)
        for fb in feedback_records:
            error = fb.actual_rating - fb.predicted_score
            for dim in new_w:
                gradient = -2 * error * new_w[dim]
                new_w[dim] -= learning_rate * gradient
        total = sum(new_w.values())
        if total > 0:
            weights = {k: round(v / total, 4) for k, v in new_w.items()}

    elif feedback_data:
        for key, value in feedback_data.items():
            if key in weights:
                try:
                    weights[key] = float(value)
                except (TypeError, ValueError):
                    continue

    elif dimension_scores:
        delta = _LIKE_BOOST if liked else -_DISLIKE_DECAY
        for dim_key, dim_val in dimension_scores.items():
            if not isinstance(dim_val, (int, float)) or dim_val <= 50:
                continue
            weight_key = _DIM_TO_WEIGHT.get(dim_key)
            if weight_key and weight_key in weights:
                weights[weight_key] = max(0.01, weights[weight_key] + delta)

    weights = _normalize_weights(weights)
    with _weights_lock:
        _active_weights = weights
    _save_weights(weights, supabase)


# =============================================================================
# GUARDRAILS
# =============================================================================

_LEVEL_THRESHOLDS: dict[ProfessionalLevel, dict[str, float]] = {
    ProfessionalLevel.JUNIOR:   {"complexity": 15.0, "experience": 20.0},
    ProfessionalLevel.MANAGER:  {"leadership": 30.0, "experience": 35.0},
    ProfessionalLevel.DIRECTOR: {"leadership": 40.0, "education": 45.0, "experience": 40.0},
}


def _apply_dimension_guardrails(
    dimensions: dict[str, float],
    weights   : dict[str, float],
    level     : ProfessionalLevel,
    hier_level: HierarchyLevel | None = None,
) -> tuple[float, list[str]]:
    thresholds = _LEVEL_THRESHOLDS.get(level, {})
    warnings   : list[str] = []
    adjusted   = 0.0

    for dim_name, score in dimensions.items():
        weight_key = _DIM_TO_WEIGHT.get(dim_name)
        if weight_key is None:
            continue
        weight   = weights.get(weight_key, 0.0)
        base_key = dim_name.replace("_score", "")

        penalty = 0.0
        if base_key in thresholds and score < thresholds[base_key]:
            penalty = (thresholds[base_key] - score) * weight * 0.75
            warnings.append(f"{base_key} faible pour {level.value} ({score:.1f})")

        adjusted += (score * weight) - penalty

    if hier_level is not None:
        dim_norm = {
            "experience":    dimensions.get("experience_score",         0.0) / 100,
            "education":     dimensions.get("education_score",          0.0) / 100,
            "certification": dimensions.get("certification_score",      0.0) / 100,
            "leadership":    dimensions.get("leadership_score",         0.0) / 100,
            "language":      dimensions.get("language_score",           0.0) / 100,
        }
        carence_penalty, carence_details = _compute_careness_penalty(dim_norm, hier_level)
        if carence_penalty > 0:
            adjusted -= carence_penalty * 100
            warnings += [d["description"] for d in carence_details]

    return _clamp(adjusted), warnings


# =============================================================================
# POINT D'ENTRÉE PRINCIPAL
# =============================================================================

def compute_candidate_score(
    *,
    cv_data            : dict[str, Any],
    job_title          : str,
    job_requirements   : str,
    required_experience: int        = DEFAULT_REQUIRED_EXPERIENCE,
    supabase           : Any        = None,
    domain             : Domain | None = None,
) -> dict[str, Any]:
    base_weights = _load_weights(supabase)
    cv_text      = _build_cv_text(cv_data)
    job_text     = _build_job_text(job_title, job_requirements)

    if domain is None:
        domain = classify_domain(cv_text, job_title, job_requirements)

    profile    = _DOMAIN_PROFILES.get(domain, _FALLBACK_PROFILE)
    is_tech    = domain in TECH_DOMAINS
    weights    = _resolve_weights(base_weights, profile.weight_overrides)
    level      = detect_professional_level(cv_text, job_title)
    hier_level = detect_hierarchy_level(_norm(f"{cv_text} {job_title}"))
    weights    = _get_weights_for_level(weights, level)

    # CORRECTION v3.1 : passage du flag is_tech + keywords normalisés
    kw_result  = _keyword_match(
        cv_text, job_text,
        keywords=None if is_tech else profile.keywords,
        is_tech=is_tech,
    )
    sem_score  = _semantic_score(cv_text, job_text)
    cert_score = _certification_score(cv_text, domain)
    edu_score  = _education_score(cv_text, domain, job_text, level)
    lead_score = _leadership_score(cv_text, profile.leadership_terms)
    cmpx_score = _complexity_score(
        cv_text,
        indicators=None if is_tech else profile.indicators,
    )
    lang_score = _language_score(cv_text)

    work_history = (
        safe_dict_list(cv_data.get("work_history"))
        or safe_dict_list(
            (cv_data.get("ai_extracted_data") or {}).get("work_history", [])
            if isinstance(cv_data.get("ai_extracted_data"), dict)
            else []
        )
    )
    candidate_years = (
        cv_data.get("experience_years")
        or infer_experience_years(work_history)
        or 0
    )
    exp_score = _experience_score(candidate_years, required_experience)

    dimensions = {
        "keyword_score":            kw_result["score"],
        "semantic_score":           sem_score,
        "experience_score":         exp_score,
        "certification_score":      cert_score,
        "education_score":          edu_score,
        "leadership_score":         lead_score,
        "project_complexity_score": cmpx_score,
        "language_score":           lang_score,
    }

    final_score, warnings = _apply_dimension_guardrails(
        dimensions, weights, level, hier_level
    )

    return {
        "score":              final_score,
        "confidence":         round((sem_score + kw_result["score"]) / 200, 2),
        "domain":             domain.value,
        "professional_level": level.value,
        "hierarchy_level":    hier_level.value,
        "reasoning":          f"Niveau={level.value} | Hiérarchie={hier_level.value} | {warnings or ['Aucun avertissement majeur']}",
        "matched_keywords":   kw_result["matched"],
        "missing_keywords":   kw_result["missing"],
        "dimension_scores":   dimensions,
        "warnings":           warnings,
    }


def compute_cv_quality_score(
    cv_data : dict[str, Any],
    supabase: Any = None,
) -> dict[str, Any]:
    cv_text = _build_cv_text(cv_data)

    ai_data: dict[str, Any] = {}
    raw_ai = cv_data.get("ai_extracted_data")
    if isinstance(raw_ai, str):
        try:
            ai_data = json.loads(raw_ai)
        except Exception:
            pass
    elif isinstance(raw_ai, dict):
        ai_data = raw_ai

    domain     = classify_domain(cv_text, "", "")
    level      = detect_professional_level(cv_text)
    hier_level = detect_hierarchy_level(_norm(cv_text))
    profile    = _DOMAIN_PROFILES.get(domain, _FALLBACK_PROFILE)
    is_tech    = domain in TECH_DOMAINS

    work_history = (
        safe_dict_list(cv_data.get("work_history"))
        or safe_dict_list(ai_data.get("work_history"))
    )
    candidate_years = (
        cv_data.get("experience_years")
        or ai_data.get("experience_years")
        or infer_experience_years(work_history)
        or 0
    )

    edu_score  = _education_score(cv_text, domain, "", level)
    exp_score  = _clamp(float(candidate_years) * 10)
    lang_score = _language_score(cv_text)
    lead_score = _leadership_score(cv_text, profile.leadership_terms)

    if is_tech:
        cert_score = _certification_score(cv_text, domain)
        cmpx_score = _complexity_score(cv_text)
    else:
        cert_score = _clamp(
            sum(1 for t in profile.indicators if t in cv_text) * 25
        )
        cmpx_score = _complexity_score(cv_text, profile.indicators)

    base_weights = _load_weights(supabase)
    weights      = _resolve_weights(base_weights, profile.weight_overrides)
    weights      = _get_weights_for_level(weights, level)

    dimensions = {
        "keyword_score":            0.0,
        "semantic_score":           0.0,
        "experience_score":         exp_score,
        "certification_score":      cert_score,
        "education_score":          edu_score,
        "leadership_score":         lead_score,
        "project_complexity_score": cmpx_score,
        "language_score":           lang_score,
    }

    final_score, warnings = _apply_dimension_guardrails(
        dimensions, weights, level, hier_level
    )

    return {
        "score":              final_score,
        "confidence":         0.65,
        "domain":             domain.value,
        "professional_level": level.value,
        "hierarchy_level":    hier_level.value,
        "reasoning":          f"Qualité CV | {domain.value} | {level.value}",
        "matched_keywords":   [],
        "missing_keywords":   [],
        "dimension_scores":   dimensions,
        "warnings":           warnings,
    }


# =============================================================================
# VERSION ASYNCHRONE
# =============================================================================

async def compute_candidate_score_async(
    *,
    cv_data            : dict[str, Any],
    job_title          : str,
    job_requirements   : str,
    required_experience: int        = DEFAULT_REQUIRED_EXPERIENCE,
    supabase           : Any        = None,
    domain             : Domain | None = None,
) -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: compute_candidate_score(
            cv_data=cv_data,
            job_title=job_title,
            job_requirements=job_requirements,
            required_experience=required_experience,
            supabase=supabase,
            domain=domain,
        ),
    )


# =============================================================================
# SCORING EN LOT
# =============================================================================

def batch_score_candidates(
    candidates         : list[dict[str, Any]],
    *,
    job_title          : str,
    job_requirements   : str,
    required_experience: int        = DEFAULT_REQUIRED_EXPERIENCE,
    supabase           : Any        = None,
    domain             : Domain | None = None,
) -> list[dict[str, Any]]:
    results = [
        {
            "cv": cv,
            **compute_candidate_score(
                cv_data=cv,
                job_title=job_title,
                job_requirements=job_requirements,
                required_experience=required_experience,
                supabase=supabase,
                domain=domain,
            ),
        }
        for cv in candidates
    ]
    return sorted(results, key=lambda r: r["score"], reverse=True)


async def batch_score_candidates_async(
    candidates         : list[dict[str, Any]],
    *,
    job_title          : str,
    job_requirements   : str,
    required_experience: int        = DEFAULT_REQUIRED_EXPERIENCE,
    supabase           : Any        = None,
    domain             : Domain | None = None,
) -> list[dict[str, Any]]:
    tasks  = [
        compute_candidate_score_async(
            cv_data=cv,
            job_title=job_title,
            job_requirements=job_requirements,
            required_experience=required_experience,
            supabase=supabase,
            domain=domain,
        )
        for cv in candidates
    ]
    scores  = await asyncio.gather(*tasks)
    results = [{"cv": cv, **score} for cv, score in zip(candidates, scores)]
    return sorted(results, key=lambda r: r["score"], reverse=True)
