# backend/app/config/classification_rules.py

from typing import Dict, List


CLASSIFICATION_RULES: List[Dict] = [
    # ── Informatique & Développement logiciel ───────────────────────────────
    {
        "domain": "informatique_dev",
        "keywords": [
            "data scientist", "data science", "machine learning", "deep learning",
            "ml engineer", "ai engineer", "intelligence artificielle",
            "nlp", "computer vision", "data analyst", "data engineer",
            "business intelligence", "bi developer", "bi analyst",
            "frontend", "front-end", "front end",
            "backend", "back-end", "back end",
            "fullstack", "full-stack", "full stack",
            "développeur", "developpeur", "developer",
            "software engineer", "ingénieur logiciel", "ingenieur logiciel",
            "web developer", "développeur web", "web dev",
            "react", "angular", "vue", "nextjs", "node", "nodejs",
            "python developer", "java developer", "php developer",
            "mobile developer", "android developer", "ios developer", "flutter",
            "devops", "sre", "site reliability",
            "cloud engineer", "cloud architect",
            "database administrator", "dba",
            "qa engineer", "quality assurance", "test engineer",
            "scrum master", "agile coach",
            "it support", "technicien informatique",
            "sysadmin", "system administrator",
            "software architect",
            "computer science", "computer engineer"
        ],
    },

    # ── Réseaux & Cybersécurité ─────────────────────────────────────────────
    {
        "domain": "reseaux_cyber",
        "keywords": [
            "cybersécurité", "cybersecurity", "security analyst",
            "réseau", "network engineer", "network administrator",
            "télécom", "telecom",
            "firewall", "pentest", "ethical hacker",
            "ccna", "ccnp", "cisco",
            "soc analyst", "noc engineer"
        ],
    },

    # ── Construction & BTP ──────────────────────────────────────────────────
    {
        "domain": "construction_btp",
        "keywords": [
            "génie civil", "civil engineer",
            "conducteur de travaux", "chef de chantier",
            "ingénieur btp", "architecte",
            "topographe", "maçon", "electricien",
            "plombier", "charpentier", "peintre",
            "btp", "construction", "chantier",
            "projeteur btp", "dessinateur btp"
        ],
    },

    # ── Ingénierie ──────────────────────────────────────────────────────────
    {
        "domain": "ingenierie",
        "keywords": [
            "ingénieur mécanique", "mechanical engineer",
            "electrical engineer", "industrial engineer",
            "process engineer", "quality engineer",
            "maintenance engineer", "project engineer",
            "automation", "mécanique", "electromécanique"
        ],
    },

    # ── Finance ──────────────────────────────────────────────────────────────
    {
        "domain": "finance_comptabilite",
        "keywords": [
            "comptable", "accountant", "finance",
            "analyste financier", "financial analyst",
            "audit", "auditor", "contrôleur de gestion",
            "cfo", "trésorier", "tax"
        ],
    },

    # ── Banque & Assurance ──────────────────────────────────────────────────
    {
        "domain": "banque_assurance",
        "keywords": [
            "banque", "banking", "assurance", "insurance",
            "actuaire", "risk manager",
            "chargé de clientèle", "conseiller bancaire"
        ],
    },

    # ── RH ───────────────────────────────────────────────────────────────────
    {
        "domain": "ressources_humaines",
        "keywords": [
            "ressources humaines", "hr", "recruteur",
            "talent acquisition", "hr manager", "payroll"
        ],
    },

    # ── Marketing ───────────────────────────────────────────────────────────
    {
        "domain": "marketing_communication",
        "keywords": [
            "marketing", "communication", "seo", "sem",
            "community manager", "brand manager",
            "content creator", "growth marketing"
        ],
    },

    # ── Logistique ──────────────────────────────────────────────────────────
    {
        "domain": "logistique_transport",
        "keywords": [
            "logistique", "supply chain", "transport",
            "chauffeur", "livreur", "warehouse",
            "gestionnaire stock"
        ],
    },

    # ── Santé ───────────────────────────────────────────────────────────────
    {
        "domain": "sante_medical",
        "keywords": [
            "médecin", "nurse", "infirmier",
            "pharmacien", "dentiste", "santé",
            "medical", "health"
        ],
    },

    # ── Éducation ───────────────────────────────────────────────────────────
    {
        "domain": "education",
        "keywords": [
            "enseignant", "professeur", "teacher",
            "formateur", "education", "trainer"
        ],
    },

    # ── Juridique ───────────────────────────────────────────────────────────
    {
        "domain": "droit_juridique",
        "keywords": [
            "juriste", "avocat", "lawyer",
            "legal", "notaire", "compliance"
        ],
    },

    # ── Design ───────────────────────────────────────────────────────────────
    {
        "domain": "design_creatif",
        "keywords": [
            "designer", "ui designer", "ux designer",
            "graphiste", "motion designer",
            "art director", "creative"
        ],
    },

    # ── Industrie ────────────────────────────────────────────────────────────
    {
        "domain": "industrie_production",
        "keywords": [
            "production", "manufacturing", "usine",
            "opérateur", "technicien de production",
            "lean", "six sigma"
        ],
    },

    # ── Étudiant / Stage ────────────────────────────────────────────────────
    {
        "domain": "etudiant_stage",
        "keywords": [
            "étudiant", "student", "stagiaire",
            "intern", "stage", "apprenti"
        ],
    },
]