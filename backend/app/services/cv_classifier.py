# backend/app/services/cv_classifier.py

"""
Advanced CV Classifier
=================================================

Features:
    - Weighted keyword scoring
    - Strong keywords = +3
    - Weak keywords   = +1
    - Prefix / stem matching
    - Accent normalization
    - Multi-language support (FR + EN)
    - Counts ALL keyword occurrences
    - Legacy rule compatibility
    - Returns highest scoring domain
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from app.config.classification_rules import CLASSIFICATION_RULES


# =========================================================
# EXTENDED DOMAIN KEYWORDS
# =========================================================

EXTENDED_DOMAINS: dict[str, dict[str, list[str]]] = {
    "informatique_dev": {
        "strong": [
            "software engineer",
            "software developer",
            "developpeur",
            "développeur",
            "developer",
            "data scientist",
            "ml engineer",
            "ai engineer",
            "data engineer",
            "frontend developer",
            "backend developer",
            "fullstack developer",
            "web developer",
            "mobile developer",
            "devops engineer",
            "cloud engineer",
            "software architect",
            "tech lead",
            "python developer",
            "java developer",
            "react developer",
        ],
        "weak": [
            "react",
            "angular",
            "vue",
            "nextjs",
            "node",
            "nodejs",
            "python",
            "java",
            "php",
            "javascript",
            "typescript",
            "django",
            "fastapi",
            "spring",
            "laravel",
            "docker",
            "kubernetes",
            "terraform",
            "aws",
            "azure",
            "gcp",
            "sql",
            "mongodb",
            "postgresql",
            "mysql",
            "html",
            "css",
            "tailwind",
            "api",
            "graphql",
            "microservices",
            "informatique",
            "programmation",
            "algorithme",
        ],
    },

    "reseaux_cyber": {
        "strong": [
            "cybersecurity",
            "cybersécurité",
            "security analyst",
            "security engineer",
            "network engineer",
            "network administrator",
            "soc analyst",
            "ethical hacker",
            "pentest",
        ],
        "weak": [
            "network",
            "reseau",
            "réseau",
            "firewall",
            "vpn",
            "ccna",
            "ccnp",
            "cisco",
            "siem",
            "wireshark",
            "nmap",
            "kali",
        ],
    },

    "construction_btp": {
        "strong": [
            "civil engineer",
            "genie civil",
            "génie civil",
            "conducteur de travaux",
            "chef de chantier",
            "architecte",
            "topographe",
        ],
        "weak": [
            "btp",
            "construction",
            "chantier",
            "batiment",
            "bâtiment",
            "beton",
            "béton",
            "revit",
            "autocad",
        ],
    },

    "ingenierie": {
        "strong": [
            "mechanical engineer",
            "electrical engineer",
            "industrial engineer",
            "process engineer",
            "quality engineer",
            "automation engineer",
        ],
        "weak": [
            "mecanique",
            "mécanique",
            "electromecanique",
            "robotique",
            "solidworks",
            "catia",
            "ansys",
            "kaizen",
            "iso 9001",
        ],
    },

    "finance_comptabilite": {
        "strong": [
            "comptable",
            "accountant",
            "financial analyst",
            "auditeur",
            "auditor",
            "expert comptable",
            "controleur de gestion",
        ],
        "weak": [
            "finance",
            "comptabilite",
            "comptabilité",
            "audit",
            "budget",
            "ifrs",
            "syscohada",
            "fiscalite",
        ],
    },

    "banque_assurance": {
        "strong": [
            "conseiller bancaire",
            "analyste credit",
            "analyste crédit",
            "risk manager",
            "actuaire",
            "agent assurance",
        ],
        "weak": [
            "banque",
            "banking",
            "assurance",
            "insurance",
            "credit",
            "crédit",
            "risque",
        ],
    },

    "ressources_humaines": {
        "strong": [
            "hr manager",
            "responsable rh",
            "recruteur",
            "talent acquisition",
            "gestionnaire paie",
        ],
        "weak": [
            "ressources humaines",
            "rh",
            "recrutement",
            "onboarding",
            "sirh",
            "paie",
        ],
    },

    "marketing_communication": {
        "strong": [
            "marketing manager",
            "community manager",
            "seo specialist",
            "growth marketer",
            "content manager",
        ],
        "weak": [
            "marketing",
            "communication",
            "seo",
            "sem",
            "google ads",
            "facebook ads",
            "analytics",
            "storytelling",
        ],
    },

    "logistique_transport": {
        "strong": [
            "supply chain manager",
            "responsable logistique",
            "dispatcher",
            "coordinateur logistique",
        ],
        "weak": [
            "logistique",
            "transport",
            "stock",
            "inventaire",
            "douane",
            "livraison",
            "entrepot",
            "entrepôt",
        ],
    },

    "sante_medical": {
        "strong": [
            "medecin",
            "médecin",
            "docteur",
            "infirmier",
            "pharmacien",
            "dentiste",
            "chirurgien",
        ],
        "weak": [
            "sante",
            "santé",
            "medical",
            "médical",
            "hopital",
            "hôpital",
            "patient",
            "diagnostic",
        ],
    },

    "education": {
        "strong": [
            "enseignant",
            "professeur",
            "teacher",
            "formateur",
            "trainer",
        ],
        "weak": [
            "education",
            "éducation",
            "pedagogie",
            "pédagogie",
            "universite",
            "université",
            "curriculum",
            "eleve",
            "élève",
        ],
    },

    "droit_juridique": {
        "strong": [
            "juriste",
            "avocat",
            "lawyer",
            "legal counsel",
            "paralegal",
        ],
        "weak": [
            "droit",
            "juridique",
            "legal",
            "contrat",
            "litige",
            "conformite",
            "conformité",
        ],
    },

    "design_creatif": {
        "strong": [
            "ui designer",
            "ux designer",
            "graphiste",
            "motion designer",
            "web designer",
        ],
        "weak": [
            "design",
            "figma",
            "photoshop",
            "illustrator",
            "wireframe",
            "prototype",
            "maquette",
        ],
    },

    "industrie_production": {
        "strong": [
            "responsable production",
            "chef atelier",
            "controleur qualite",
            "contrôleur qualité",
        ],
        "weak": [
            "production",
            "manufacturing",
            "usine",
            "atelier",
            "lean",
            "six sigma",
            "5s",
        ],
    },

    "etudiant_stage": {
        "strong": [
            "etudiant",
            "étudiant",
            "student",
            "stagiaire",
            "intern",
            "apprenti",
            "alternant",
        ],
        "weak": [
            "stage",
            "internship",
            "alternance",
            "master",
            "licence",
            "bts",
            "dut",
            "bac+",
        ],
    },

"responsable_achats": {
    "strong": [
        # Core procurement roles
        "responsable achats",
        "directeur achats",
        "acheteur",
        "acheteur senior",
        "acheteur international",
        "acheteur industriel",
        "acheteur projet",
        "acheteur technique",
        "acheteur public",
        "buyer",
        "senior buyer",
        "lead buyer",
        "technical buyer",
        "strategic buyer",
        "procurement manager",
        "procurement specialist",
        "procurement officer",
        "procurement lead",
        "purchasing manager",
        "purchasing officer",
        "sourcing manager",
        "category manager",
        "commodity manager",
        "supply officer",
        "supply chain buyer",
        "responsable approvisionnement",
        "gestionnaire approvisionnement",
        "supply chain manager",

        # ERP / procurement systems expertise
        "sap mm consultant",
        "sap procurement consultant",
        "oracle procurement consultant",

        # Tendering / contracts
        "gestionnaire contrats fournisseurs",
        "contract manager",
        "appel d'offres manager",
        "tender manager",
    ],

    "weak": [
        # Procurement vocabulary
        "achat",
        "achats",
        "purchasing",
        "procurement",
        "buying",
        "sourcing",
        "strategic sourcing",
        "approvisionnement",
        "supply",
        "supply chain",
        "vendor management",
        "gestion fournisseurs",
        "supplier management",
        "supplier",
        "suppliers",
        "fournisseur",
        "fournisseurs",

        # Negotiation / contracts
        "negociation",
        "négociation",
        "contract",
        "contrat",
        "contrats",
        "appel d'offre",
        "appel d'offres",
        "tender",
        "rfq",
        "rfi",
        "rfp",

        # Logistics / inventory related
        "stock",
        "inventory",
        "warehouse",
        "logistique",
        "transport",
        "distribution",
        "livraison",

        # ERP / tools
        "sap mm",
        "sap",
        "oracle procurement",
        "erp",
        "sage",
        "excel",
        "power bi",

        # Purchasing KPIs
        "cost reduction",
        "cost optimization",
        "budget achats",
        "budget procurement",
        "supplier performance",
        "lead time",
        "forecast",
        "forecasting",

        # International trade
        "import",
        "export",
        "douane",
        "incoterms",
        "freight",
    ],
},
}


# =========================================================
# TEXT NORMALIZATION
# =========================================================

def _normalize(text: str) -> str:
    """
    Normalize text:
        - lowercase
        - remove accents
        - remove punctuation
        - collapse spaces
    """

    text = text.lower()

    # Remove accents
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )

    # Remove punctuation
    text = re.sub(r"[^\w\s\-/]", " ", text)

    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =========================================================
# REGEX HELPERS
# =========================================================

def _keyword_pattern(keyword: str) -> str:
    """
    Create flexible regex pattern.

    Example:
        develop -> develop\\w*
        cyber   -> cyber\\w*
    """

    keyword = keyword.lower().strip()
    keyword = re.escape(keyword)

    return rf"\b{keyword}\w*\b"


# =========================================================
# DOMAIN SCORING
# =========================================================

def _score_domain(
    text: str,
    strong_keywords: list[str],
    weak_keywords: list[str],
) -> float:
    """
    Score a CV against domain keywords.
    """

    score = 0.0

    # Strong keywords → +3
    for keyword in strong_keywords:
        pattern = _keyword_pattern(keyword)
        matches = re.findall(pattern, text)
        score += len(matches) * 3

    # Weak keywords → +1
    for keyword in weak_keywords:
        pattern = _keyword_pattern(keyword)
        matches = re.findall(pattern, text)
        score += len(matches) * 1

    return score


# =========================================================
# MAIN CLASSIFIER
# =========================================================

def classify_cv(text: str) -> Optional[str]:
    """
    Classify a CV into the best matching domain.

    Returns:
        domain name or None
    """

    if not text:
        return None

    normalized_text = _normalize(text)

    scores: dict[str, float] = {}

    # Extended domains
    for domain, keywords in EXTENDED_DOMAINS.items():

        strong_keywords = keywords.get("strong", [])
        weak_keywords = keywords.get("weak", [])

        score = _score_domain(
            normalized_text,
            strong_keywords,
            weak_keywords,
        )

        scores[domain] = score

    # Legacy rules support
    for rule in CLASSIFICATION_RULES:

        domain = rule["domain"]

        if domain not in scores:
            scores[domain] = 0.0

        for keyword in rule.get("keywords", []):

            keyword = _normalize(keyword)

            pattern = _keyword_pattern(keyword)

            matches = re.findall(pattern, normalized_text)

            scores[domain] += len(matches)

    # No scores
    if not scores:
        return None

    # Best domain
    best_domain = max(scores, key=scores.get)
    best_score = scores[best_domain]

    # No meaningful match
    if best_score <= 0:
        return None

    return best_domain


# =========================================================
# DEBUG / TEST
# =========================================================

if __name__ == "__main__":

    sample_cv = """
    Senior Python Backend Developer with FastAPI, Docker,
    PostgreSQL and AWS experience.
    """

    result = classify_cv(sample_cv)

    print("Detected domain:", result)

