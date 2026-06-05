# backend/app/services/scoring_service.py
# =============================================================================
# CŒUR DU SYSTÈME DE NOTATION DES CANDIDATS
#
# Rôle : comparer un CV avec une offre d'emploi et produire un score de 0–100.
#
# Dimensions analysées :
#   • keyword       – mots-clés communs CV ↔ offre
#   • semantic      – similarité de sens (SentenceTransformer)
#   • experience    – années du candidat vs. exigées
#   • certification – certifications détectées
#   • education     – niveau et pertinence du diplôme
#   • leadership    – termes d'encadrement
#   • complexity    – profondeur technique/métier
#   • language      – maîtrise des langues étrangères
#
# Les poids sont adaptatifs (feedback recruteur) et se chargent depuis
# Supabase (table app_config, clé "ats_weights").
#
# IMPORTANT – imports circulaires :
#   compute_final_score() et get_final_candidate_assessment() vivent dans
#   ai_service.py car ils dépendent de analyze_cv_depth() qui est définie là.
#   Les placer ici créerait une importation circulaire.
# =============================================================================

from __future__ import annotations

import asyncio
import json
import os
import re
import torch
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity



# =============================================================================
# CACHE HuggingFace – DOIT être défini avant tout import transformers
# =============================================================================
_CACHE_DIR = Path("./.hf-cache")
_CACHE_DIR.mkdir(exist_ok=True)
os.environ.setdefault("HF_HOME",          str(_CACHE_DIR.resolve()))
os.environ.setdefault("TRANSFORMERS_CACHE", str(_CACHE_DIR.resolve()))

_MODEL_NAME = "all-MiniLM-L6-v2"


# Optimisations mémoire fortes pour Render (512MB)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
torch.set_num_threads(1)                    # Réduit fortement l'usage mémoire
torch.set_num_interop_threads(1)


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    print(f"[scoring] Loading SentenceTransformer ({_MODEL_NAME}) in low memory mode…")
    
    model = SentenceTransformer(_MODEL_NAME, device='cpu')
    
    # Réduction supplémentaire de mémoire
    model.half()          # Passe en float16 (réduit ~50% de RAM)
    
    return model


# =============================================================================
# UTILITAIRES COMMUNS
# =============================================================================

def _norm(text: str | None) -> str:
    """Normalise un texte : minuscules + strip."""
    return (text or "").lower().strip()


def _clamp(value: float) -> float:
    """Contraint une valeur dans [0, 100] et arrondit à 2 décimales."""
    return round(max(0.0, min(value, 100.0)), 2)


def safe_list(value: Any) -> list[str]:
    """Convertit en toute sécurité une valeur quelconque en liste de chaînes."""
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
    """Même logique que safe_list, mais pour des listes de dictionnaires."""
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

# --- Mots-clés & patterns tech pré-compilés ----------------------------------
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

# --- Scores par certification (pipeline tech) --------------------------------
CERTIFICATION_SCORES: dict[str, int] = {
    "aws":    35,
    "scrum":  30,
    "oracle": 35,
}

# --- Termes de leadership génériques (tech) ----------------------------------
LEADERSHIP_TERMS: tuple[str, ...] = (
    "lead", "leader", "mentor", "management", "architect",
    "code review", "scrum", "encadrement",
)

# --- Indicateurs de complexité (pipeline tech) -------------------------------
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

# --- Poids par défaut --------------------------------------------------------
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

# Mapping dimension_key → weight_key
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

# Poids actifs en mémoire (protégés par un verrou)
_active_weights: dict[str, float] = dict(DEFAULT_WEIGHTS)
_weights_lock = threading.Lock()


# =============================================================================
# DÉTECTION DE DOMAINE
# =============================================================================

_DOMAIN_DETECTION: dict[Domain, frozenset[str]] = {
    Domain.TECH: frozenset({
        "python", "java", "react", "docker", "kubernetes",
        "api", "backend", "frontend", "devops", "software",
        "développement logiciel", "informatique", "programmation",
    }),
    Domain.NETWORKS: frozenset({
        "réseau", "network", "cybersécurité", "cisco", "firewall",
        "switch", "vpn", "télécoms", "infrastructure réseau",
    }),
    Domain.ENGINEERING: frozenset({
        "mécanique", "électrique", "conception", "autocad",
        "solidworks", "bureau d'études", "ingénierie",
    }),
    Domain.SCIENCE: frozenset({
        "laboratoire", "recherche", "publication", "thèse",
        "protocole", "expérimentation", "chimie", "biologie",
    }),
    Domain.ENERGY: frozenset({
        "pétrole", "mines", "forage", "géologie", "raffinage",
        "énergie renouvelable", "solaire", "hydraulique",
    }),
    Domain.INDUSTRY: frozenset({
        "production", "usine", "chaîne de montage", "lean",
        "maintenance industrielle", "5s", "kaizen",
    }),
    Domain.QHSE: frozenset({
        "hse", "qualité", "iso 9001", "iso 14001",
        "sécurité au travail", "audit qualité", "non-conformité", "certification qhse",
    }),
    Domain.SUPPLY_CHAIN: frozenset({
        "achat", "supply chain", "approvisionnement", "logistique",
        "fournisseur", "négociation achat", "erp", "stock",
        "sla", "service-level agreement",
    }),
    Domain.PURCHASING_MANAGER: frozenset({
        "responsable achats", "chef des achats", "directeur achats",
        "sla", "service-level agreement",
    }),
    Domain.ADMIN: frozenset({
        "secrétariat", "assistante", "agenda", "courrier",
        "accueil", "classement", "bureautique", "archivage",
    }),
    Domain.AGRI: frozenset({
        "agriculture", "élevage", "agronomie", "semences",
        "cultures", "agroalimentaire", "terrain agricole",
    }),
    Domain.ART: frozenset({
        "design", "graphisme", "photographie", "illustration",
        "créatif", "adobe", "figma", "ux", "ui", "artiste",
    }),
    Domain.BANKING: frozenset({
        "banque", "assurance", "crédit", "risque", "bâle",
        "conformité", "actuariat", "portefeuille clients",
    }),
    Domain.SALES: frozenset({
        "vente", "commercial", "prospection", "crm", "ca",
        "chiffre d'affaires", "b2b", "b2c", "négociation commerciale",
    }),
    Domain.ACCOUNTING: frozenset({
        "comptabilité", "fiscalité", "bilan", "audit financier",
        "ifrs", "ohada", "contrôle de gestion", "trésorerie",
    }),
    Domain.BTP: frozenset({
        "construction", "btp", "chantier", "génie civil",
        "maçonnerie", "conducteur de travaux", "bâtiment",
    }),
    Domain.LEGAL: frozenset({
        "droit", "juridique", "contrat", "avocat", "notaire",
        "procédure", "contentieux", "réglementation",
    }),
    Domain.EDUCATION: frozenset({
        "enseignement", "formateur", "pédagogie", "curriculum",
        "professeur", "élèves", "formation professionnelle",
    }),
    Domain.HOSPITALITY: frozenset({
        "hôtellerie", "restauration", "cuisine", "chef",
        "service en salle", "accueil client", "f&b",
    }),
    Domain.REAL_ESTATE: frozenset({
        "immobilier", "transaction", "bail", "copropriété",
        "expertise immobilière", "promotion immobilière",
    }),
    Domain.JOURNALISM: frozenset({
        "journalisme", "rédaction", "médias", "presse",
        "reportage", "édition", "publication", "contenu éditorial",
    }),
    Domain.MARKETING: frozenset({
        "marketing", "communication", "stratégie digitale",
        "seo", "sem", "brand", "campagne", "publicité",
    }),
    Domain.HR: frozenset({
        "ressources humaines", "recrutement", "paie", "gpec",
        "formation", "relations sociales", "rh", "talent",
    }),
    Domain.HEALTH: frozenset({
        "médecin", "infirmier", "pharmacie", "santé", "clinique",
        "patient", "soins", "hôpital", "médical",
    }),
    Domain.GENERAL_SERVICES: frozenset({
        "maintenance", "facility", "nettoyage", "gardiennage",
        "services généraux", "prestataires",
    }),
    Domain.INTERN: frozenset({
        "stage", "jeune diplômé", "alternance", "apprentissage",
    }),
    Domain.TOURISM: frozenset({
        "tourisme", "voyage", "hôtel", "agence de voyage",
        "guide touristique", "loisirs",
    }),
    Domain.TRANSPORT: frozenset({
        "transport", "logistique", "chauffeur", "fret",
        "douane", "transit", "fleet management",
    }),
    Domain.SOCIAL: frozenset({
        "travail social", "ong", "humanitaire", "développement communautaire",
        "action sociale", "volontariat", "ngo",
    }),
}


def classify_domain(cv_text: str, job_title: str, job_requirements: str) -> Domain:
    """
    Détermine automatiquement le domaine métier.
    Compte les signaux présents dans le texte combiné ; retourne Domain.TECH si égalité.
    """
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

_DOMAIN_PROFILES: dict[Domain, DomainProfile] = {

    Domain.SUPPLY_CHAIN: DomainProfile(
        keywords=(
            "achat", "approvisionnement", "supply chain", "erp", "sap",
            "négociation", "fournisseur", "inventaire", "logistique",
            "appel d'offres", "sourcing", "stock", "s&op",
            "gestion des stocks", "planification", "prévision de la demande",
            "réduction des coûts", "optimisation des achats", "contrat fournisseur",
            "cahier des charges", "évaluation fournisseurs", "référencement fournisseur",
            "commande", "bon de commande", "délai de livraison", "rupture de stock",
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
            "négociation": 15, "sourcing international": 20, "réduction coûts": 15,
        },
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
        leadership_terms=("chef des achats", "responsable supply chain", "directeur achats"),
    ),

    Domain.PURCHASING_MANAGER: DomainProfile(
        keywords=(
            "responsable achats", "chef des achats", "directeur achats",
            "strategie achat", "sla", "gestion fournisseurs", "négociation achat",
            "supply chain", "politique d'achat", "service level agreement",
            "réduction des coûts", "p and l", "profit and loss",
            "portefeuille fournisseurs", "gestion des contrats d'achat",
            "wallet", "gestion des stocks", "gestion des approvisionnements",
            "stock", "appel d'offres", "procédure d'achat",
            "contrat-cadre", "cahier des charges", "évaluation fournisseurs",
            "panel fournisseurs", "audit fournisseur", "référencement fournisseur",
            "sourcing", "sourcing international", "centrale d'achat",
            "budget achats", "kpi achats", "tco", "total cost of ownership",
            "rfq", "rfp", "bon de commande", "commande", "catalogue achats",
            "procure-to-pay", "p2p", "edi", "erp", "sap", "demand planning",
            "performance fournisseur", "sla fournisseur", "vendor management",
            "achat durable", "rse fournisseurs", "import", "export", "incoterms",
            "plan d'achat", "stratégie de négociation", "économies d'achats",
            "tableau de bord achats", "reporting achats", "délai de livraison",
        ),
        indicators={"sla": 20, "service-level agreement": 20, "slas": 20},
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
    ),

    Domain.ADMIN: DomainProfile(
        keywords=(
            "secrétariat", "bureautique", "word", "excel", "agenda",
            "courrier", "classement", "archivage", "accueil", "office",
            "powerpoint", "outlook", "saisie", "rédaction administrative",
            "compte rendu", "procès-verbal", "gestion administrative",
            "secrétaire de direction", "assistante de direction",
            "office manager", "gestion documentaire", "ged",
            "numérisation", "tri du courrier", "standard téléphonique",
            "planification", "réservation", "gestion des déplacements",
            "organisation de réunions", "prise de notes", "frappe",
            "mise en page", "publipostage", "office 365", "teams",
            "sharepoint", "google workspace", "google docs", "google sheets",
            "administration du personnel", "gestion des congés",
            "tableau de bord", "suivi administratif", "relance",
            "facturation", "devis", "bon de commande", "suivi des paiements",
            "accueil physique", "accueil téléphonique", "agenda électronique",
            "confidentialité", "discrétion", "polyvalence administrative",
            "gestion des fournitures", "commandes de bureau",
            "organisation d'événements", "protocole",
        ),
        indicators={"bilingue": 20, "office 365": 15, "gestion agenda": 15},
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
    ),

    Domain.AGRI: DomainProfile(
        keywords=(
            "agronomie", "agriculture", "élevage", "cultures", "semences",
            "irrigation", "fertilisation", "agroalimentaire", "phytosanitaire",
            "agronome", "exploitation agricole", "gestion d'exploitation",
            "production végétale", "production animale", "maraîchage",
            "arboriculture", "viticulture", "sylviculture", "aquaculture",
            "pisciculture", "aviculture", "bovins", "ovins", "caprins",
            "sorgho", "maïs", "riz", "cacao", "café", "coton", "palmier à huile",
            "intrants agricoles", "pesticides", "herbicides", "fongicides",
            "engrais", "amendement", "compostage", "agriculture biologique",
            "certification bio", "agriculture durable", "agroécologie",
            "agroforesterie", "permaculture", "géospatial", "sig agricole",
            "météorologie agricole", "chaîne de valeur agricole",
            "stockage post-récolte", "transformation agroalimentaire",
            "commercialisation agricole", "coopérative agricole",
            "conseil agricole", "vulgarisation agricole", "financement agricole",
            "crédit rural", "microcrédit agricole", "projet de développement rural",
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
            "ux", "ui", "créatif", "branding", "motion design",
            "photographie", "vidéo", "3d", "after effects",
            "direction artistique", "identité visuelle", "charte graphique",
            "typographie", "mise en page", "infographie", "conception graphique",
            "design d'interface", "design produit", "design web",
            "ux research", "user testing", "wireframe", "prototype",
            "sketch", "adobe xd", "indesign", "premiere pro",
            "cinema 4d", "blender", "zbrush", "substance painter",
            "animation 3d", "vfx", "storyboard", "illustration",
            "dessin", "aquarelle", "peinture digitale", "retouche photo",
            "color grading", "montage vidéo", "réalisation", "scénario",
            "créativité", "concept art", "design thinking", "design system",
            "accessibilité numérique", "responsive design", "mobile-first",
            "landing page design", "ui kit", "design sprint",
            "communication visuelle", "arts plastiques", "multimédia",
        ),
        indicators={
            "direction artistique": 20, "identité visuelle": 15,
            "motion design": 15, "ux research": 20,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.35, "experience": 0.15,
            "education": 0.10, "complexity": 0.25, "leadership": 0.05,
        },
    ),

    Domain.BANKING: DomainProfile(
        keywords=(
            "banque", "assurance", "crédit", "risque", "portefeuille",
            "conformité", "bâle iii", "solvabilité", "actuariat",
            "kyc", "aml", "produits financiers", "taux",
            "analyse financière", "trésorerie bancaire", "liquidité",
            "fonds propres", "ratio de solvabilité", "stress test",
            "risque de crédit", "risque de marché", "risque opérationnel",
            "risque de liquidité", "notation financière", "scoring",
            "recouvrement", "contentieux bancaire", "garantie bancaire",
            "lettre de crédit", "trade finance", "financement structuré",
            "marchés financiers", "obligations", "actions", "dérivés",
            "swift", "sepa", "virement", "prélèvement", "mobile banking",
            "fintech", "open banking", "paiements digitaux", "microfinance",
            "crédit immobilier", "crédit consommation", "leasing",
            "assurance vie", "assurance dommages", "courtage", "prévoyance",
            "réassurance", "ifrs 9", "ifrs 17", "règlementation bancaire",
            "contrôle interne bancaire", "audit bancaire", "inspection",
            "direction des risques", "comité de crédit",
        ),
        indicators={
            "bâle iii": 20, "kyc/aml": 20, "actuariat": 20,
            "gestion risque": 15, "ifrs 9": 20,
        },
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
    ),

    Domain.SALES: DomainProfile(
        keywords=(
            "vente", "commercial", "prospection", "crm", "b2b", "b2c",
            "négociation", "chiffre d'affaires", "pipeline", "closing",
            "account manager", "fidélisation", "développement commercial",
            "téléprospection", "cold calling", "lead generation",
            "qualification", "cycle de vente", "funnel commercial",
            "grand compte", "key account", "vente complexe",
            "argumentaire de vente", "objections", "rebond commercial",
            "upsell", "cross-sell", "panier moyen", "taux de conversion",
            "quota", "objectifs commerciaux", "commissionnement",
            "variable commerciale", "incentive", "sales force",
            "salesforce", "hubspot", "zoho", "reporting commercial",
            "tableau de bord commercial", "kpi ventes",
            "prévision de ventes", "forecasting", "business development",
            "partenariat commercial", "réseau de distribution",
            "agent commercial", "vente indirecte", "vente directe",
            "pitch commercial", "démonstration produit", "offre commerciale",
            "devis", "proposition commerciale", "appel d'offres",
            "renouvellement", "rétention client", "satisfaction client",
            "nps", "customer success",
        ),
        indicators={
            "développement commercial": 15, "grand compte": 20,
            "b2b": 10, "crm": 10, "objectifs dépassés": 20,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.35, "experience": 0.15,
            "complexity": 0.25, "leadership": 0.10, "education": 0.05,
        },
        leadership_terms=("directeur commercial", "chef des ventes", "key account manager"),
    ),

    Domain.ACCOUNTING: DomainProfile(
        keywords=(
            "comptabilité", "fiscalité", "bilan", "ohada", "ifrs",
            "contrôle de gestion", "audit", "trésorerie", "sage",
            "déclarations fiscales", "rapprochement bancaire", "budget",
            "comptabilité générale", "comptabilité analytique",
            "comptabilité clients", "comptabilité fournisseurs",
            "grand livre", "journal comptable", "balance", "liasse fiscale",
            "compte de résultat", "flux de trésorerie", "cash flow",
            "immobilisations", "amortissement", "provision", "charges",
            "produits", "tva", "is", "impôt sur les sociétés", "cit",
            "impôt sur le revenu", "paie comptable", "charges sociales",
            "commissaire aux comptes", "expert-comptable", "commissariat",
            "due diligence", "consolidation", "normes comptables",
            "reporting financier", "états financiers", "normes ifrs",
            "normes syscohada", "syscoa", "bsc", "budget prévisionnel",
            "contrôle budgétaire", "suivi des coûts", "prix de revient",
            "coûts standards", "écarts", "analyse des écarts",
            "erp comptable", "odoo", "cegid", "wave", "navision",
        ),
        indicators={
            "ifrs": 20, "ohada": 20, "audit externe": 20,
            "contrôle de gestion": 15, "sage": 10,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.35, "experience": 0.15,
            "education": 0.10, "complexity": 0.25, "leadership": 0.05,
        },
    ),

    Domain.BTP: DomainProfile(
        keywords=(
            "construction", "btp", "génie civil", "conducteur de travaux",
            "chantier", "maçonnerie", "béton armé", "autocad",
            "planification", "lot technique", "métré", "vrd",
            "gros œuvre", "second œuvre", "infrastructure", "superstructure",
            "terrassement", "fondations", "charpente", "couverture",
            "plomberie", "électricité", "hvac", "climatisation",
            "revêtement", "carrelage", "peinture bâtiment", "menuiserie",
            "architecture", "plan d'exécution", "plan as-built",
            "dossier technique", "permis de construire", "cctp",
            "dpgf", "avant-métré", "appel d'offres btp", "budget chantier",
            "planning travaux", "gantt", "ms project", "primavera",
            "contrôle qualité chantier", "réception des travaux",
            "levée de réserves", "ged chantier", "étude de sol",
            "bureau de contrôle", "sps", "coordinateur sps",
            "inspection travaux", "suivi technique", "visa",
            "hse chantier", "plan phs", "prévention accidents",
            "bim", "revit", "maquette numérique",
        ),
        indicators={
            "conducteur de travaux senior": 20, "autocad": 15,
            "gestion multi-chantiers": 20, "vrd": 15, "béton armé": 10,
        },
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
        leadership_terms=("directeur de travaux", "chef de chantier", "ingénieur génie civil"),
    ),

    Domain.LEGAL: DomainProfile(
        keywords=(
            "droit", "juridique", "contrat", "contentieux", "procédure",
            "réglementation", "conformité", "ohada", "droit du travail",
            "droit des sociétés", "code civil", "tribunal",
            "avocat", "juriste", "conseil juridique", "veille juridique",
            "droit des affaires", "droit commercial", "droit fiscal",
            "droit pénal", "droit administratif", "droit international",
            "arbitrage", "médiation", "conciliation", "négociation juridique",
            "acte juridique", "statuts", "pacte d'actionnaires",
            "protocole d'accord", "mou", "nda", "contrat de travail",
            "convention collective", "règlement intérieur",
            "relations sociales", "licenciement", "rupture conventionnelle",
            "prud'hommes", "conseil d'état", "cour d'appel",
            "due diligence juridique", "audit juridique", "conformité réglementaire",
            "protection des données", "rgpd", "propriété intellectuelle",
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
            "enseignement", "formation", "pédagogie", "curriculum",
            "e-learning", "évaluation", "professeur", "ingénierie pédagogique",
            "formateur", "instructeur", "facilitateur", "coach",
            "enseignant", "tuteur", "mentor", "programme scolaire",
            "syllabus", "plan de cours", "objectifs pédagogiques",
            "compétences", "évaluation formative", "évaluation sommative",
            "contrôle continu", "examen", "certification",
            "formation professionnelle", "développement des compétences",
            "formation initiale", "formation continue", "upskilling",
            "reskilling", "lms", "moodle", "google classroom",
            "blended learning", "classe inversée", "gamification",
            "pédagogie active", "apprentissage par projet",
            "différenciation pédagogique", "inclusion scolaire",
            "soutien scolaire", "remédiation", "accompagnement",
            "orientation scolaire", "conseil pédagogique",
            "administration scolaire", "direction d'établissement",
            "inspection pédagogique", "recherche en éducation",
            "thèse", "publication académique", "université",
        ),
        indicators={
            "ingénierie pédagogique": 20, "e-learning": 15,
            "formation certifiante": 20,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.35, "experience": 0.15,
            "education": 0.10, "complexity": 0.25, "leadership": 0.05,
        },
    ),

    Domain.HOSPITALITY: DomainProfile(
        keywords=(
            "hôtellerie", "restauration", "cuisine", "service en salle",
            "f&b", "sommellerie", "haccp", "réception", "housekeeping",
            "hôtel", "restaurant", "brigade", "chef cuisinier", "chef de partie",
            "commis de cuisine", "pâtisserie", "boulangerie", "traiteur",
            "banquet", "événementiel", "room service", "concierge",
            "réservation", "check-in", "check-out", "pms",
            "front office", "back office", "yield management",
            "revenue management", "taux d'occupation", "revpar",
            "guest experience", "satisfaction client", "qualité hôtelière",
            "classification hôtelière", "étoiles", "label qualité",
            "bar", "cave à vins", "cocktail", "mixologie",
            "menu", "carte", "food cost", "ratio matière",
            "gestion des stocks restauration", "approvisionnement cuisine",
            "normes sanitaires", "hygiène alimentaire", "traçabilité",
            "plan de nettoyage", "désinfection", "contrôle qualité alimentaire",
            "maître d'hôtel", "directeur de restaurant", "directeur d'hôtel",
            "manager f&b", "directeur hébergement",
        ),
        indicators={
            "étoile michelin": 20, "haccp": 15,
            "revenue management": 20, "classification hôtelière": 15,
        },
        weight_overrides={
            "keyword": 0.10, "semantic": 0.30, "experience": 0.35,
            "education": 0.18, "complexity": 0.20, "leadership": 0.05,
        },
    ),

    Domain.REAL_ESTATE: DomainProfile(
        keywords=(
            "immobilier", "transaction", "bail", "promotion immobilière",
            "expertise", "copropriété", "aménagement", "négociation immobilière",
            "agent immobilier", "mandataire immobilier", "courtier immobilier",
            "vente immobilière", "location", "gestion locative", "syndic",
            "bien immobilier", "appartement", "villa", "immeuble", "terrain",
            "foncier", "lotissement", "programme immobilier", "vefa",
            "permis de construire", "plan local d'urbanisme", "plu",
            "dossier de financement", "prêt immobilier", "crédit immobilier",
            "taux immobilier", "apport personnel", "garantie hypothécaire",
            "acte de vente", "notaire", "compromis de vente",
            "promesse de vente", "due diligence immobilière",
            "état des lieux", "quittance de loyer", "charges locatives",
            "évaluation immobilière", "estimation immobilière", "valeur vénale",
            "diagnostic immobilier", "dpe", "amiante", "plomb",
            "réhabilitation", "rénovation", "travaux immobiliers",
            "gestion de patrimoine immobilier", "investissement locatif",
            "rendement locatif", "fiscalité immobilière", "sci",
        ),
        indicators={
            "promotion immobilière": 20, "expertise immobilière": 20,
            "vente de programmes": 15,
        },
        weight_overrides={
            "keyword": 0.20, "semantic": 0.35, "experience": 0.25,
            "education": 0.08, "complexity": 0.07, "leadership": 0.05,
        },
    ),

    Domain.JOURNALISM: DomainProfile(
        keywords=(
            "journalisme", "rédaction", "presse", "reportage", "médias",
            "enquête", "édition", "contenu éditorial", "interview",
            "photojournalisme", "digital media",
            "journaliste", "rédacteur", "chroniqueur", "correspondant",
            "grand reporter", "envoyé spécial", "pigiste", "freelance",
            "news", "actualité", "breaking news", "fact-checking",
            "vérification des faits", "sources journalistiques",
            "déontologie journalistique", "liberté de la presse",
            "journal", "magazine", "web média", "blog", "newsletter",
            "podcast", "radio", "télévision", "web tv", "streaming",
            "réseaux sociaux", "twitter journalisme", "community manager",
            "seo éditorial", "trafic", "audience", "analytics",
            "éditeur en chef", "rédacteur en chef", "secrétaire de rédaction",
            "maquette presse", "une", "titraille", "photographie de presse",
            "agence de presse", "fil d'information", "dépêche", "revue de presse",
            "veille médias", "relations presse", "attaché de presse",
        ),
        indicators={
            "grand reportage": 20, "rédacteur en chef": 20, "digital media": 15,
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
            "stratégie digitale", "content marketing", "kpi",
            "marketing digital", "marketing opérationnel", "marketing stratégique",
            "étude de marché", "segmentation", "ciblage", "positionnement",
            "mix marketing", "4p", "persona", "customer journey",
            "tunnel de conversion", "acquisition", "rétention", "fidélisation",
            "email marketing", "newsletter", "automation marketing",
            "marketing automation", "hubspot", "mailchimp", "sendinblue",
            "facebook ads", "instagram ads", "linkedin ads", "tiktok ads",
            "google analytics", "tag manager", "pixel", "a/b testing",
            "landing page", "conversion rate optimization", "cro",
            "affiliation", "influence marketing", "influenceur",
            "community management", "gestion des réseaux sociaux",
            "brand management", "notoriété", "image de marque",
            "plan de communication", "brief créatif", "message marketing",
            "rp", "relations publiques", "événementiel marketing",
            "trade marketing", "merchandising", "plv",
        ),
        indicators={
            "stratégie omnicanale": 20, "google ads": 15,
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
            "onboarding", "évaluation des performances", "rémunération",
            "ressources humaines", "gestion des ressources humaines",
            "gestion des talents", "marque employeur", "employer branding",
            "sourcing candidats", "entretien de recrutement",
            "assessment center", "intégration", "période d'essai",
            "plan de formation", "besoin en formation", "cpf",
            "plan de développement", "coaching", "feedback 360",
            "entretien annuel", "entretien professionnel",
            "gestion de carrière", "mobilité interne", "succession planning",
            "contrat de travail", "avenant", "rupture conventionnelle",
            "licenciement", "procédure disciplinaire", "sanctions",
            "délégués du personnel", "comité social et économique", "cse",
            "syndicats", "négociation collective", "accord d'entreprise",
            "règlement intérieur", "politique rh", "charte rh",
            "absentéisme", "turnover", "taux de rotation", "engagement",
            "qvt", "qualité de vie au travail", "bien-être", "rsst",
            "diversité", "inclusion", "égalité professionnelle",
        ),
        indicators={
            "gpec": 20, "sirh": 15, "négociation syndicale": 20,
            "talent management": 15, "rémunération variable": 10,
        },
        weight_overrides={
            "keyword": 0.22, "semantic": 0.33, "experience": 0.20,
            "education": 0.10, "complexity": 0.10, "leadership": 0.05,
        },
        leadership_terms=("drh", "directeur des ressources humaines", "hr business partner"),
    ),

    Domain.HEALTH: DomainProfile(
        keywords=(
            "médecine", "soins infirmiers", "pharmacie", "chirurgie",
            "diagnostic", "patient", "urgences", "bloc opératoire",
            "radiologie", "biologie médicale", "clinique", "protocole médical",
            "médecin", "infirmier", "infirmière", "aide-soignant",
            "sage-femme", "kinésithérapeute", "orthophoniste",
            "psychologue", "psychiatre", "cardiologue", "pédiatre",
            "dermatologue", "ophtalmologue", "gynécologue", "urologue",
            "orthopédiste", "anesthésiste", "réanimation", "soins intensifs",
            "unité de soins", "consultation", "hospitalisation",
            "ambulatoire", "télémédecine", "dossier médical",
            "dossier patient informatisé", "dpi", "prescription",
            "ordonnance", "traitement", "thérapie", "médicament",
            "pharmacovigilance", "essai clinique", "recherche médicale",
            "santé publique", "épidémiologie", "prévention",
            "vaccination", "dépistage", "promotion de la santé",
            "hygiène hospitalière", "infection nosocomiale",
            "stérilisation", "biomédicale", "dispositif médical",
        ),
        indicators={
            "spécialité médicale": 25, "chef de service": 20,
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
            "prestataires", "services généraux", "parc automobile", "hse",
            "gestion des installations", "facilities", "building management",
            "entretien des locaux", "propreté", "nettoyage industriel",
            "sécurité des bâtiments", "contrôle d'accès", "vidéosurveillance",
            "alarme incendie", "sécurité incendie", "évacuation",
            "maintenance préventive", "maintenance curative",
            "maintenance corrective", "gmao", "ticketing maintenance",
            "prestataires de services", "contrats de maintenance",
            "appel d'offres prestataires", "sla prestataires",
            "espaces verts", "jardinage", "entretien extérieur",
            "gestion des déchets", "tri sélectif", "développement durable",
            "flotte automobile", "gestion des véhicules", "carnet d'entretien",
            "assurance flotte", "télématique", "gps",
            "énergie", "eau", "électricité", "gaz", "fluides",
            "réduction des coûts énergie", "audit énergétique",
            "plan de prévention", "document unique", "risques professionnels",
            "espace de travail", "aménagement des bureaux",
        ),
        indicators={"facility management": 20, "gestion prestataires": 15},
        weight_overrides={
            "keyword": 0.20, "semantic": 0.35, "experience": 0.25,
            "education": 0.08, "complexity": 0.07, "leadership": 0.05,
        },
    ),

    Domain.INTERN: DomainProfile(
        keywords=(
            "stage", "alternance", "apprentissage", "projet académique",
            "mémoire", "rapport de stage",
            "stagiaire", "alternant", "apprenti", "étudiant",
            "licence", "master", "bts", "dut", "bachelor",
            "première expérience", "début de carrière", "junior",
            "encadrement", "tuteur de stage", "maître d'apprentissage",
            "projet de fin d'études", "pfe", "soutenance", "jury",
            "convention de stage", "contrat d'apprentissage",
            "contrat de professionnalisation", "formation en alternance",
            "centre de formation", "cfai", "cfa",
            "compétences transversales", "savoir-être", "soft skills",
            "motivation", "curiosité", "rigueur", "ponctualité",
            "travail en équipe", "adaptabilité", "autonomie",
            "langue étrangère", "anglais scolaire", "niveau b2",
            "excel basique", "word traitement de texte",
            "initiation professionnelle", "découverte métier",
            "immersion professionnelle", "projet transversal",
            "stage longue durée", "stage de fin d'études",
        ),
        indicators={"projet transversal": 10, "stage longue durée": 15},
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
    ),

    Domain.TOURISM: DomainProfile(
        keywords=(
            "tourisme", "voyage", "agence de voyage", "guide touristique",
            "billetterie", "crm touristique", "gds", "amadeus",
            "tour opérateur", "to", "voyagiste", "circuit touristique",
            "package voyage", "séjour", "excursion", "croisière",
            "tourisme d'affaires", "mice", "congrès", "séminaire",
            "tourisme balnéaire", "tourisme culturel", "écotourisme",
            "tourisme solidaire", "tourisme de luxe", "tourisme local",
            "office du tourisme", "destination marketing",
            "booking", "réservation en ligne", "hébergement touristique",
            "hôtel", "auberge de jeunesse", "gîte", "airbnb", "campsite",
            "transport touristique", "transfert aéroport",
            "guide de voyage", "interprète touristique",
            "visa", "passeport", "assurance voyage", "assistance",
            "galileo", "sabre", "worldspan", "travelport",
            "tarification aérienne", "yield aérien", "billet d'avion",
            "tourisme médical", "wellness tourism", "agritourisme",
            "itinéraire", "road trip", "travel blogger",
        ),
        indicators={"amadeus": 20, "gds": 15, "tourisme international": 20},
        weight_overrides=_NON_TECH_WEIGHT_DEFAULT,
    ),

    Domain.TRANSPORT: DomainProfile(
        keywords=(
            "transport", "logistique", "chauffeur", "fret", "douane",
            "transit", "affrètement", "tms", "déclaration en douane",
            "incoterms", "fleet management",
            "transport routier", "transport maritime", "transport aérien",
            "transport ferroviaire", "multimodal", "intermodal",
            "commissionnaire de transport", "freight forwarder",
            "transitaire", "freight broker", "courtier de fret",
            "bill of lading", "connaissement", "airway bill", "cmr",
            "import", "export", "dédouanement", "tarif douanier",
            "nomenclature douanière", "hs code", "origine des marchandises",
            "entrepôt sous douane", "mise à la consommation",
            "fret aérien", "fret maritime", "conteneur", "vrac",
            "palettisation", "emballage", "conditionnement",
            "messagerie", "express", "courrier", "dernier kilomètre",
            "livraison", "tournée", "optimisation des tournées",
            "routing", "gps", "télématique", "géolocalisation",
            "réglementation transport", "adr", "matières dangereuses",
            "conducteur poids lourd", "permis de conduire",
        ),
        indicators={
            "incoterms": 20, "tms": 20,
            "affrètement international": 20, "douane": 15, "fleet management": 15,
        },
        weight_overrides={
            "keyword": 0.25, "semantic": 0.30, "experience": 0.25,
            "education": 0.08, "complexity": 0.07, "leadership": 0.05,
        },
    ),

    Domain.SOCIAL: DomainProfile(
        keywords=(
            "travail social", "ong", "humanitaire", "développement communautaire",
            "action sociale", "volontariat", "projet social", "plaidoyer",
            "protection sociale", "assistance aux personnes vulnérables",
            "assistant social", "travailleur social", "éducateur spécialisé",
            "animateur socioculturel", "coordinateur", "chef de projet social",
            "bénévolat", "service civique", "corps de la paix",
            "droits humains", "droits de l'homme", "genre", "égalité",
            "inclusion sociale", "lutte contre la pauvreté",
            "protection de l'enfance", "violences basées sur le genre",
            "vbg", "autonomisation des femmes", "jeunesse",
            "développement local", "participation communautaire",
            "diagnostic communautaire", "enquête sociale",
            "gestion de cas", "case management", "suivi bénéficiaires",
            "rapport de mission", "monitoring évaluation", "me",
            "bailleurs de fonds", "donors", "ue", "usaid", "banque mondiale",
            "gestion de projet ong", "cadre logique", "logframe",
            "rapport narratif", "rapport financier bailleur",
            "appel à propositions", "concept note", "proposal writing",
            "terrain humanitaire", "urgence humanitaire", "camp de réfugiés",
        ),
        indicators={
            "gestion de projet ong": 20, "plaidoyer": 15,
            "financement bailleur": 20, "développement communautaire": 15,
        },
        weight_overrides={
            "keyword": 0.20, "semantic": 0.40, "experience": 0.18,
            "education": 0.12, "complexity": 0.05, "leadership": 0.05,
        },
    ),

    # ---- Domaines tech étendus -----------------------------------------------

    Domain.NETWORKS: DomainProfile(
        keywords=(
            "réseau", "cisco", "firewall", "switch", "vpn", "infrastructure",
            "cybersécurité", "pentest", "soc", "ids", "ips", "télécoms",
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
            "télécommunications", "fibre optique", "4g", "backbone",
        ),
        indicators={
            "pentest": 20, "soc": 20, "sd-wan": 20,
            "certifié ccna": 20, "certifié cissp": 25,
        },
        weight_overrides={
            "keyword": 0.25, "semantic": 0.30, "experience": 0.20,
            "certification": 0.10, "complexity": 0.10,
            "education": 0.03, "leadership": 0.02,
        },
    ),

    Domain.ENGINEERING: DomainProfile(
        keywords=(
            "mécanique", "électrique", "hydraulique", "conception", "autocad",
            "solidworks", "catia", "bureau d'études", "simulation", "erd",
            "maintenance préventive",
            "génie mécanique", "génie électrique", "génie industriel",
            "thermodynamique", "résistance des matériaux", "rdm",
            "éléments finis", "fem", "cfm", "cfd",
            "prototypage", "fabrication", "procédés de fabrication",
            "usinage", "soudure", "chaudronnerie", "tuyauterie",
            "électronique", "automatisme", "plc", "api",
            "siemens", "schneider", "allen bradley", "hmi", "scada",
            "instrumentation", "capteur", "mesure", "calibration",
            "maintenance industrielle", "fiabilité", "mttf", "mttr",
            "gmao", "maintenance totale", "tpm",
            "gestion de projet technique", "planning", "jalons",
            "normes techniques", "iso", "en", "astm", "asme",
            "certification de produit", "homologation", "essais",
            "calcul de structure", "dimensionnement", "contraintes",
            "tolérances", "métrologie", "contrôle qualité",
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
            "laboratoire", "protocole", "expérimentation", "publication",
            "thèse", "r&d", "chimie", "biologie", "statistiques",
            "matlab", "spss", "r", "python",
            "recherche scientifique", "sciences fondamentales",
            "sciences appliquées", "physique", "mathématiques",
            "biochimie", "microbiologie", "génétique", "immunologie",
            "virologie", "botanique", "zoologie", "écologie",
            "chimie organique", "chimie analytique", "chimie physique",
            "chromatographie", "spectroscopie", "électrophorèse", "pcr",
            "cell culture", "culture cellulaire", "flow cytometry",
            "imagerie médicale", "histologie", "anatomopathologie",
            "analyse de données", "big data", "machine learning scientifique",
            "modélisation", "simulation numérique", "calcul scientifique",
            "hpc", "cluster", "publication indexée", "peer review",
            "brevet", "propriété intellectuelle scientifique",
            "financement de la recherche", "anr", "h2020",
            "rapport d'avancement", "revue bibliographique",
            "état de l'art", "doctorat", "post-doctorat", "habilitation",
        ),
        indicators={
            "publication indexée": 25, "thèse": 20,
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
            "pétrole", "mines", "forage", "géologie", "raffinage",
            "énergie renouvelable", "solaire", "hydraulique", "reservoir",
            "hse pétrolier", "offshore",
            "gaz naturel", "gaz de pétrole", "gnl", "gpl",
            "pipeline", "transport d'hydrocarbures", "stockage",
            "exploration pétrolière", "sismique", "géophysique",
            "pétrophysique", "diagraphie", "carottage",
            "drilling", "well completion", "stimulation",
            "production pétrolière", "enhanced oil recovery", "eor",
            "reservoir simulation", "modélisation de réservoir",
            "éolien", "éolienne offshore", "solaire photovoltaïque",
            "solaire thermique", "biomasse", "biogaz",
            "géothermie", "hydroélectricité", "stockage d'énergie",
            "batterie", "hydrogène", "pile à combustible",
            "réseau électrique", "smart grid", "power plant",
            "centrale thermique", "centrale solaire", "centrale hydraulique",
            "mining", "extraction minière", "minerai", "or", "diamant",
            "cuivre", "bauxite", "phosphate", "traitement des minerais",
            "métallurgie", "hydrométallurgie", "pyrométallurgie",
        ),
        indicators={
            "offshore": 20, "reservoir engineering": 25,
            "hse pétrolier": 20, "énergie solaire": 15,
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
            "maintenance industrielle", "chaîne de montage", "plc",
            "automatisme", "erp", "ordonnancement",
            "chef de production", "responsable de production",
            "directeur d'usine", "responsable usine",
            "amélioration continue", "amélioration des processus",
            "six sigma", "black belt", "green belt", "vsm",
            "tpm", "smed", "poka yoke", "jidoka",
            "takt time", "cycle time", "efficacité globale", "trs", "oee",
            "contrôle de production", "suivi de production",
            "planning de production", "ordonnancement de fabrication",
            "gestion de la production", "mrp", "mrp2",
            "qualité de production", "contrôle qualité",
            "non-conformité", "rebut", "retraitement",
            "traçabilité", "gestion des lots", "sérialisation",
            "emballage industriel", "conditionnement",
            "gestion des flux", "flux physiques",
            "gestion des outillages", "gestionnaire outillage",
            "sécurité industrielle", "epi", "plan de prévention",
            "habilitations électriques", "caces", "travail en hauteur",
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
            "hse", "qualité", "iso 9001", "iso 14001", "ohsas 18001",
            "iso 45001", "audit qualité", "non-conformité", "plan de prévention",
            "document unique", "analyse des risques",
            "responsable qhse", "directeur qhse", "animateur sécurité",
            "ingénieur hse", "technicien qse",
            "système de management", "smq", "sme", "sms",
            "certification", "recertification", "surveillance", "tierce partie",
            "accréditation", "cofrac", "iatf 16949", "iso 13485",
            "iso 22000", "haccp", "brc", "ifs",
            "risque professionnel", "évaluation des risques", "duer",
            "plan d'action", "suivi des actions correctives",
            "action préventive", "amélioration continue",
            "indicateurs qualité", "kpi qualité", "tableau de bord qhse",
            "revue de direction", "audit interne", "audit externe",
            "programme d'audit", "rapport d'audit",
            "accident du travail", "enquête accident", "arbre des causes",
            "presqu'accident", "near miss", "reporting sécurité",
            "formation sécurité", "sensibilisation", "causerie sécurité",
            "permit to work", "permis de travail", "lock out tag out",
            "environnement", "émissions", "déchets industriels",
            "sol pollué", "dépollution", "veille réglementaire",
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

# Profil de secours utilisé quand aucun profil spécifique n'est disponible.
_FALLBACK_PROFILE = DomainProfile()


# =============================================================================
# PERTINENCE DU DIPLÔME PAR DOMAINE
# =============================================================================

_EDUCATION_RELEVANCE: dict[Domain, tuple[str, ...]] = {
    Domain.ACCOUNTING: ("comptabilité", "finance", "gestion", "fiscalité", "ohada", "ifrs", "sage"),
    Domain.BANKING:    ("banque", "finance", "économie", "actuariat"),
    Domain.TECH:       ("informatique", "développement", "ingénieur", "systèmes"),
    Domain.MARKETING:  ("marketing", "communication", "digital"),
    Domain.HR:         ("ressources humaines", "rh"),
    Domain.BTP:        ("génie civil", "bâtiment", "architecture"),
    Domain.AGRI:       ("agronomie", "agriculture"),
    Domain.LEGAL:      ("droit", "juridique"),
    Domain.HEALTH:     ("médecine", "pharmacie"),
    Domain.SALES:      ("commerce", "vente"),
}


# =============================================================================
# DÉTECTION DU NIVEAU PROFESSIONNEL
# =============================================================================

def detect_professional_level(cv_text: str, job_title: str = "") -> ProfessionalLevel:
    text = _norm(f"{cv_text} {job_title}")
    if any(t in text for t in ("dg", "directeur général", "ceo", "c-level")):
        return ProfessionalLevel.EXECUTIVE
    if any(t in text for t in ("directeur", "head of", "chief")):
        return ProfessionalLevel.DIRECTOR
    if any(t in text for t in ("manager", "responsable", "chef de")):
        return ProfessionalLevel.MANAGER
    if any(t in text for t in ("senior", "expert", "confirmé")):
        return ProfessionalLevel.SENIOR
    if any(t in text for t in ("junior", "stagiaire", "débutant")):
        return ProfessionalLevel.JUNIOR
    return ProfessionalLevel.MID_LEVEL


# =============================================================================
# CONSTRUCTION DES TEXTES DE SCORING
# =============================================================================

def _build_cv_text(cv: dict[str, Any]) -> str:
    """Représentation textuelle complète d'un CV."""
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
    """Calcule le total d'années d'expérience à partir de l'historique."""
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

            months = (end_dt.year - start_dt.year) * 12 + end_dt.month - start_dt.month
            total_months += max(months, 0)

        except (ValueError, TypeError):
            continue

    return round(total_months / 12, 1)


# =============================================================================
# MATCHING MOTS-CLÉS
# =============================================================================

def _extract_tech_keywords(text: str) -> set[str]:
    """Matching rapide pour les mots-clés tech (patterns pré-compilés)."""
    return {kw for kw, pat in _KW_PATTERNS.items() if pat.search(text)}


def _extract_keywords_from_set(text: str, keywords: tuple[str, ...]) -> set[str]:
    """Matching pour un tuple de mots-clés arbitraires."""
    result: set[str] = set()
    for kw in keywords:
        pat = re.compile(
            rf"\b{re.escape(kw)}\b" if " " not in kw else re.escape(kw),
            re.IGNORECASE,
        )
        if pat.search(text):
            result.add(kw)
    return result


def _keyword_match(
    cv_text : str,
    job_text: str,
    keywords: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """
    Score de correspondance par mots-clés.
    keywords=None → pipeline tech.  keywords fournis → pipeline domaine.
    """
    if keywords is None:
        cv_kws  = _extract_tech_keywords(cv_text)
        job_kws = _extract_tech_keywords(job_text)
    else:
        cv_kws  = _extract_keywords_from_set(cv_text, keywords)
        job_kws = _extract_keywords_from_set(job_text, keywords)

    matched = sorted(cv_kws & job_kws)
    missing = sorted(job_kws - cv_kws)
    score   = 50.0 if not job_kws else (len(matched) / len(job_kws)) * 100

    return {"score": _clamp(score), "matched": matched, "missing": missing}


# =============================================================================
# SCORE SÉMANTIQUE
# =============================================================================

def _semantic_score(cv_text: str, job_text: str) -> float:
    """Similarité sémantique cosinus (SentenceTransformer)."""
    cv_text  = cv_text[:4000]
    job_text = job_text[:2000]

    if not cv_text or not job_text:
        return 0.0

    try:
        model      = _get_model()
        embeddings = model.encode(
            [cv_text, job_text],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
        return _clamp(float(similarity) * 100)
    except Exception as exc:
        print(f"[scoring] Semantic similarity error: {exc}")
        return 0.0


# =============================================================================
# SCORERS PAR DIMENSION
# =============================================================================

def _experience_score(candidate_years: float, required_years: float) -> float:
    try:
        candidate_years = float(candidate_years or 0)
        required_years  = float(required_years  or 0)
        if required_years <= 0:
            return 100.0
        return _clamp((candidate_years / required_years) * 100)
    except Exception:
        return 0.0


def _certification_score(cv_text: str) -> float:
    """Score certifications (pipeline tech uniquement)."""
    total = sum(pts for cert, pts in CERTIFICATION_SCORES.items() if cert in cv_text)
    return _clamp(total)


def _education_relevance_score(cv_text: str, domain: Domain, job_text: str = "") -> float:
    text    = _norm(f"{cv_text} {job_text}")
    matches = sum(1 for kw in _EDUCATION_RELEVANCE.get(domain, ()) if kw in text)
    if matches >= 2:
        return 95.0
    if matches == 1:
        return 75.0
    return 40.0


def _education_score(
    cv_text: str,
    domain : Domain,
    job_text: str = "",
    level  : ProfessionalLevel = ProfessionalLevel.MID_LEVEL,
) -> float:
    """Score éducation tenant compte du niveau de diplôme et de sa pertinence métier."""
    cv_lower = _norm(cv_text)

    if "doctorat" in cv_lower or "phd" in cv_lower:
        level_score = 100.0
    elif any(x in cv_lower for x in ("master", "mastère", "ingénieur")):
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


def _leadership_score(cv_text: str, extra_terms: tuple[str, ...] = ()) -> float:
    all_terms = LEADERSHIP_TERMS + extra_terms
    matches   = sum(1 for term in all_terms if term in cv_text)
    return _clamp(matches * 20)


def _complexity_score(
    cv_text   : str,
    indicators: dict[str, int] | None = None,
) -> float:
    """Score de complexité / profondeur. Utilise COMPLEXITY_INDICATORS si non fourni."""
    source = indicators if indicators is not None else COMPLEXITY_INDICATORS
    return _clamp(sum(pts for term, pts in source.items() if term in cv_text))


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
    """Fusionne les poids de base avec les surcharges de domaine, puis normalise."""
    return _normalize_weights({**base, **overrides})


def _get_weights_for_level(
    base : dict[str, float],
    level: ProfessionalLevel,
) -> dict[str, float]:
    """Ajuste les poids selon le niveau professionnel."""
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
    """Charge les poids depuis Supabase ; retourne la copie mémoire si pas de DB."""
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
    """Sauvegarde les poids dans Supabase via un UPSERT."""
    if supabase is None:
        return
    try:
        supabase.table("app_config").upsert(
            {"key": "ats_weights", "value": weights},
            on_conflict="key",
        ).execute()
    except Exception as exc:
        print(f"[scoring] Failed to save weights to DB: {exc}")


def update_weights_from_feedback(
    *,
    supabase       : Any               = None,
    candidate_id   : str | None        = None,
    liked          : bool              = True,
    dimension_scores: dict[str, float] | None = None,
    feedback_data  : dict[str, float] | None  = None,
) -> None:
    """
    Adapte les poids selon le feedback d'un recruteur.

    Mode 1 — feedback_data : remplace directement les valeurs.
    Mode 2 — dimension_scores + liked : ajuste les dimensions > 50 pts.
    """
    global _active_weights

    weights = _load_weights(supabase)

    if feedback_data:
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
# GUARDRAILS PAR DIMENSION
# =============================================================================

# Seuils minimaux attendus par niveau ; clé = nom de dimension sans "_score"
_LEVEL_THRESHOLDS: dict[ProfessionalLevel, dict[str, float]] = {
    ProfessionalLevel.JUNIOR:   {"complexity": 15.0, "experience": 20.0},
    ProfessionalLevel.MANAGER:  {"leadership": 30.0, "experience": 35.0},
    ProfessionalLevel.DIRECTOR: {"leadership": 40.0, "education": 45.0, "experience": 40.0},
}


def _apply_dimension_guardrails(
    dimensions: dict[str, float],
    weights   : dict[str, float],
    level     : ProfessionalLevel,
) -> tuple[float, list[str]]:
    """
    Calcule le score pondéré avec pénalité pour les dimensions sous le seuil du niveau.
    Retourne (score_final, liste_avertissements).
    """
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
    """
    Calcule le score d'adéquation CV ↔ offre d'emploi (0–100).

    Retourne un dict contenant : score, confidence, domain,
    professional_level, reasoning, matched_keywords, missing_keywords,
    dimension_scores, warnings.
    """
    base_weights = _load_weights(supabase)
    cv_text      = _build_cv_text(cv_data)
    job_text     = _build_job_text(job_title, job_requirements)

    if domain is None:
        domain = classify_domain(cv_text, job_title, job_requirements)

    profile = _DOMAIN_PROFILES.get(domain, _FALLBACK_PROFILE)
    is_tech = domain in TECH_DOMAINS
    weights = _resolve_weights(base_weights, profile.weight_overrides)

    level   = detect_professional_level(cv_text, job_title)
    weights = _get_weights_for_level(weights, level)

    # --- Dimensions -----------------------------------------------------------
    kw_result = (
        _keyword_match(cv_text, job_text)
        if is_tech
        else _keyword_match(cv_text, job_text, profile.keywords)
    )

    sem_score    = _semantic_score(cv_text, job_text)
    cert_score   = _certification_score(cv_text) if is_tech else 0.0
    edu_score    = _education_score(cv_text, domain, job_text, level)
    lead_score   = _leadership_score(cv_text, profile.leadership_terms)
    cmpx_score   = (
        _complexity_score(cv_text)
        if is_tech
        else _complexity_score(cv_text, profile.indicators)
    )
    lang_score   = _language_score(cv_text)

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

    final_score, warnings = _apply_dimension_guardrails(dimensions, weights, level)

    return {
        "score":             final_score,
        "confidence":        round((sem_score + kw_result["score"]) / 200, 2),
        "domain":            domain.value,
        "professional_level": level.value,
        "reasoning":         f"Niveau={level.value} | {warnings or ['Aucun avertissement majeur']}",
        "matched_keywords":  kw_result["matched"],
        "missing_keywords":  kw_result["missing"],
        "dimension_scores":  dimensions,
        "warnings":          warnings,
    }


def compute_cv_quality_score(
    cv_data : dict[str, Any],
    supabase: Any = None,
) -> dict[str, Any]:
    """Score qualité autonome d'un CV (sans offre d'emploi)."""
    cv_text = _build_cv_text(cv_data)

    # ai_extracted_data déjà parsé dans _build_cv_text ; on le relit proprement.
    ai_data: dict[str, Any] = {}
    raw_ai = cv_data.get("ai_extracted_data")
    if isinstance(raw_ai, str):
        try:
            ai_data = json.loads(raw_ai)
        except Exception:
            pass
    elif isinstance(raw_ai, dict):
        ai_data = raw_ai

    domain  = classify_domain(cv_text, "", "")
    level   = detect_professional_level(cv_text)
    profile = _DOMAIN_PROFILES.get(domain, _FALLBACK_PROFILE)
    is_tech = domain in TECH_DOMAINS

    work_history    = (
        safe_dict_list(cv_data.get("work_history"))
        or safe_dict_list(ai_data.get("work_history"))
    )
    candidate_years = (
        cv_data.get("experience_years")
        or ai_data.get("experience_years")
        or infer_experience_years(work_history)
        or 0
    )

    edu_score    = _education_score(cv_text, domain, "", level)
    exp_score    = _clamp(float(candidate_years) * 10)
    lang_score   = _language_score(cv_text)
    lead_score   = _leadership_score(cv_text, profile.leadership_terms)

    if is_tech:
        cert_score  = _certification_score(cv_text)
        cmpx_score  = _complexity_score(cv_text)
    else:
        cert_score  = _clamp(sum(1 for t in profile.indicators if t in cv_text) * 25)
        cmpx_score  = _complexity_score(cv_text, profile.indicators)

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

    final_score, warnings = _apply_dimension_guardrails(dimensions, weights, level)

    return {
        "score":             final_score,
        "confidence":        0.65,
        "domain":            domain.value,
        "professional_level": level.value,
        "reasoning":         f"Qualité CV | {domain.value} | {level.value}",
        "matched_keywords":  [],
        "missing_keywords":  [],
        "dimension_scores":  dimensions,
        "warnings":          warnings,
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
    """Version async de compute_candidate_score (exécution dans un thread pool)."""
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
    """Score une liste de candidats pour une même offre (version synchrone)."""
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
    """Score une liste de candidats en parallèle (version async)."""
    tasks = [
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
