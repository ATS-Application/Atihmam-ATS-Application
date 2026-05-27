# backend/app/services/cv_classifier.py
#
# Improved classifier:
#   - Scoring system: counts ALL keyword hits across the full text
#   - Stem/prefix matching: "develop" matches "developer", "développ" matches "développeur"
#   - Weighted keywords: strong job-title signals score 3x, generic terms score 1x
#   - Returns the domain with the highest score (not the first match)
#   - Falls back to "autres" only if every domain scores 0

import re
from typing import Optional
from app.config.classification_rules import CLASSIFICATION_RULES


# ─────────────────────────────────────────────────────────────
# EXTENDED KEYWORD MAP
# Each domain gets: strong_keywords (weight=3) + weak_keywords (weight=1)
# Strong = specific job titles / certifications
# Weak   = general field terms that help confirm but can appear anywhere
# ─────────────────────────────────────────────────────────────

EXTENDED_DOMAINS: dict = {
    "informatique_dev": {
        "strong": [
            # Job titles
            "software engineer", "software developer", "ingénieur logiciel",
            "développeur", "developpeur", "developer",
            "data scientist", "ml engineer", "ai engineer", "data engineer",
            "data analyst", "bi developer", "bi analyst", "business intelligence",
            "frontend developer", "frontend engineer", "front-end developer",
            "backend developer", "backend engineer", "back-end developer",
            "fullstack developer", "full stack developer", "full-stack developer",
            "web developer", "web dev", "développeur web",
            "mobile developer", "android developer", "ios developer",
            "devops engineer", "cloud engineer", "cloud architect",
            "database administrator", "dba", "qa engineer", "test engineer",
            "software architect", "tech lead", "lead developer",
            "scrum master", "agile coach", "it support", "technicien informatique",
            "sysadmin", "system administrator", "site reliability",
            # Specialisations
            "machine learning", "deep learning", "nlp", "computer vision",
            "flutter developer", "react developer", "angular developer",
            "python developer", "java developer", "php developer",
            "node developer", "nodejs developer",
        ],
        "weak": [
            # Frameworks / languages (alone they're weak signals)
            "react", "angular", "vue", "nextjs", "node", "nodejs",
            "python", "java", "php", "javascript", "typescript",
            "django", "fastapi", "spring", "laravel", "rails",
            "docker", "kubernetes", "terraform", "ansible",
            "aws", "azure", "gcp", "cloud",
            "git", "github", "gitlab", "ci/cd",
            "sql", "nosql", "mongodb", "postgresql", "mysql",
            "html", "css", "sass", "tailwind",
            "agile", "scrum", "jira", "confluence",
            "api", "rest", "graphql", "microservices",
            # Degrees / education
            "computer science", "informatique", "génie informatique",
            "software", "programmation", "algorithme",
        ],
    },

    "reseaux_cyber": {
        "strong": [
            "cybersécurité", "cybersecurity", "security analyst", "security engineer",
            "network engineer", "network administrator", "administrateur réseau",
            "soc analyst", "noc engineer", "pentest", "penetration test",
            "ethical hacker", "firewall engineer", "telecom engineer",
            "ingénieur réseau", "ingénieur télécom",
        ],
        "weak": [
            "réseau", "network", "télécom", "telecom", "firewall",
            "vpn", "ccna", "ccnp", "cisco", "juniper",
            "ids", "ips", "siem", "soc", "noc",
            "cryptographie", "cryptography", "zero trust",
            "wireshark", "nmap", "kali",
        ],
    },

    "construction_btp": {
        "strong": [
            "génie civil", "civil engineer", "ingénieur génie civil",
            "conducteur de travaux", "chef de chantier", "ingénieur btp",
            "architecte", "topographe", "dessinateur btp", "projeteur btp",
            "maçon", "électricien bâtiment", "plombier", "charpentier",
            "ingénieur structure", "ingénieur travaux",
        ],
        "weak": [
            "btp", "construction", "chantier", "bâtiment", "travaux",
            "béton", "structure", "fondation", "autocad", "revit",
            "plan de masse", "permis de construire", "vrd",
            "peintre", "carreleur", "menuisier",
        ],
    },

    "ingenierie": {
        "strong": [
            "ingénieur mécanique", "mechanical engineer",
            "electrical engineer", "ingénieur électrique",
            "industrial engineer", "process engineer",
            "quality engineer", "ingénieur qualité",
            "maintenance engineer", "ingénieur maintenance",
            "project engineer", "ingénieur projet",
            "automation engineer", "ingénieur automatisme",
        ],
        "weak": [
            "mécanique", "electromécanique", "automatisme", "robotique",
            "solidworks", "catia", "autocad mécanique", "ansys",
            "lean manufacturing", "kaizen", "iso 9001",
            "bureau d'études", "r&d", "recherche développement",
        ],
    },

    "finance_comptabilite": {
        "strong": [
            "comptable", "accountant", "chef comptable",
            "analyste financier", "financial analyst",
            "contrôleur de gestion", "cfo", "directeur financier",
            "auditeur", "auditor", "trésorier", "tax consultant",
            "expert comptable", "responsable financier",
        ],
        "weak": [
            "finance", "comptabilité", "audit", "bilan", "fiscalité",
            "sage", "sap fi", "oracle financials", "budget",
            "reporting financier", "clôture comptable", "tva",
            "amortissement", "consolidation", "ifrs", "syscohada",
        ],
    },

    "banque_assurance": {
        "strong": [
            "chargé de clientèle", "conseiller bancaire",
            "analyste crédit", "risk manager", "actuaire",
            "gestionnaire sinistres", "agent d'assurance",
            "responsable agence bancaire", "compliance officer",
            "ingénieur financier",
        ],
        "weak": [
            "banque", "banking", "assurance", "insurance",
            "crédit", "prêt", "portefeuille client",
            "bâle", "solvabilité", "risque opérationnel",
        ],
    },

    "ressources_humaines": {
        "strong": [
            "responsable rh", "hr manager", "directeur des ressources humaines",
            "recruteur", "talent acquisition", "chargé de recrutement",
            "gestionnaire paie", "payroll manager", "hr business partner",
            "responsable formation",
        ],
        "weak": [
            "ressources humaines", "rh", "hr", "recrutement", "onboarding",
            "paie", "gestion des talents", "gpec", "sirh",
            "entretien annuel", "fiches de poste",
        ],
    },

    "marketing_communication": {
        "strong": [
            "responsable marketing", "marketing manager", "directeur marketing",
            "community manager", "brand manager", "content manager",
            "traffic manager", "seo specialist", "sem specialist",
            "growth hacker", "growth marketer", "digital marketing manager",
            "chargé de communication", "attaché de presse",
        ],
        "weak": [
            "marketing", "communication", "seo", "sem", "ads",
            "google ads", "facebook ads", "emailing", "newsletter",
            "inbound", "funnel", "kpi marketing", "analytics",
            "brand", "identité visuelle", "storytelling",
        ],
    },

    "logistique_transport": {
        "strong": [
            "responsable logistique", "supply chain manager",
            "gestionnaire de stock", "chef magasinier",
            "responsable transport", "dispatcher",
            "coordinateur logistique", "freight forwarder",
        ],
        "weak": [
            "logistique", "supply chain", "transport", "entrepôt",
            "stock", "inventaire", "incoterms", "douane",
            "livraison", "chauffeur", "livreur", "camion",
            "wms", "erp logistique",
        ],
    },

    "sante_medical": {
        "strong": [
            "médecin", "docteur", "infirmier", "infirmière",
            "pharmacien", "dentiste", "chirurgien",
            "sage-femme", "kinésithérapeute", "radiologue",
            "médecin généraliste", "médecin spécialiste",
        ],
        "weak": [
            "santé", "médical", "health", "clinique", "hôpital",
            "patient", "soin", "thérapie", "diagnostic",
            "ordonnance", "anam", "urgences",
        ],
    },

    "education": {
        "strong": [
            "enseignant", "professeur", "teacher", "formateur",
            "directeur d'école", "proviseur", "éducateur",
            "instructeur", "trainer", "coach professionnel",
            "responsable pédagogique",
        ],
        "weak": [
            "éducation", "formation", "pédagogie", "programme scolaire",
            "lycée", "université", "e-learning", "lms",
            "curriculum", "élève", "étudiant encadrement",
        ],
    },

    "droit_juridique": {
        "strong": [
            "juriste", "avocat", "lawyer", "notaire",
            "magistrat", "huissier", "conseiller juridique",
            "compliance officer", "legal counsel", "paralegal",
        ],
        "weak": [
            "droit", "juridique", "legal", "contrat", "litige",
            "contentieux", "réglementation", "code civil",
            "rgpd", "conformité", "due diligence",
        ],
    },

    "design_creatif": {
        "strong": [
            "ui designer", "ux designer", "ui/ux designer",
            "graphiste", "directeur artistique", "motion designer",
            "designer graphique", "brand designer",
            "product designer", "web designer",
        ],
        "weak": [
            "design", "figma", "adobe xd", "sketch", "illustrator",
            "photoshop", "indesign", "after effects", "premiere",
            "maquette", "prototype", "wireframe", "charte graphique",
            "typographie", "mise en page", "créatif",
        ],
    },

    "industrie_production": {
        "strong": [
            "responsable de production", "chef d'atelier",
            "technicien de production", "opérateur de production",
            "contrôleur qualité", "responsable qualité production",
            "lean manager", "responsable maintenance industrielle",
        ],
        "weak": [
            "production", "manufacturing", "usine", "atelier",
            "lean", "six sigma", "5s", "tpm", "gamme de production",
            "opérateur", "ligne de production",
        ],
    },

    "etudiant_stage": {
        "strong": [
            "étudiant en", "student in", "stagiaire",
            "intern", "apprenti", "alternant",
            "en cours de formation", "currently studying",
        ],
        "weak": [
            "stage", "internship", "alternance", "apprentissage",
            "école d'ingénieur", "master", "licence", "bts", "dut",
            "bac+", "grande école",
        ],
    },
}


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, remove punctuation except hyphens."""
    text = text.lower()
    text = re.sub(r"[^\w\s\-/]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _score_domain(text: str, strong_kws: list, weak_kws: list) -> float:
    """
    Score a domain against normalized CV text.
    - Strong keyword hit  → +3
    - Weak keyword hit    → +1
    Uses word-boundary aware matching so "java" doesn't match "javascript".
    """
    score = 0.0

    for kw in strong_kws:
        pattern = r"\b" + re.escape(kw) + r"\b"
        matches = re.findall(pattern, text)
        score += len(matches) * 3

    for kw in weak_kws:
        pattern = r"\b" + re.escape(kw) + r"\b"
        matches = re.findall(pattern, text)
        score += len(matches) * 1

    return score


# ─────────────────────────────────────────────────────────────
# MAIN CLASSIFIER
# ─────────────────────────────────────────────────────────────

def classify_cv(text: str) -> Optional[str]:
    """
    Classify a CV into a domain using weighted keyword scoring.

    Returns the domain string (e.g. "informatique_dev") or None if
    every domain scores 0 (caller should fallback to detect_domain).
    """
    if not text:
        return None

    normalized = _normalize(text)

    scores: dict[str, float] = {}

    for domain, kw_sets in EXTENDED_DOMAINS.items():
        strong = kw_sets.get("strong", [])
        weak   = kw_sets.get("weak", [])
        scores[domain] = _score_domain(normalized, strong, weak)

    # Also run legacy rules from CLASSIFICATION_RULES (treated as weak)
    for rule in CLASSIFICATION_RULES:
        domain = rule["domain"]
        for kw in rule.get("keywords", []):
            pattern = r"\b" + re.escape(kw.lower()) + r"\b"
            matches = re.findall(pattern, normalized)
            scores[domain] = scores.get(domain, 0.0) + len(matches) * 1

    best_domain = max(scores, key=lambda d: scores[d])
    best_score  = scores[best_domain]

    if best_score == 0:
        return None  # Caller will use fallback

    return best_domain