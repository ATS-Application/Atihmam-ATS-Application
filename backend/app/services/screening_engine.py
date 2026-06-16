DEGREE_ORDER = {
    "": 0,
    "bachelor": 1,
    "master": 2,
    "phd": 3,
}


# ═════════════════════════════════════════════════════════════════════════
# MATRICE DE COMPATIBILITÉ DOMAINES — v2.1 COMPLÈTE ET INTELLIGENTE
# ═════════════════════════════════════════════════════════════════════════
# Définit les domaines candidat acceptables pour chaque catégorie de poste.
# Les transitions similaires (ex: logistique → ingénierie) sont autorisées,
# mais les transitions inappropriées (ex: logistique → construction BTP) sont
# rejetées AVANT le scoring pour économiser ressources et éviter faux positifs.
# ═════════════════════════════════════════════════════════════════════════

DOMAIN_COMPATIBILITY = {
    # INFORMATIQUE & TECH
    "informatique_dev": [
        "informatique_dev",
        "reseaux_cyber",
        "ingenierie",          # Ingénierie sys/automation compatible
    ],
    "reseaux_cyber": [
        "reseaux_cyber",
        "informatique_dev",    # Dev → Cyber transition acceptable
        "ingenierie",
    ],

    # CONSTRUCTION & INGÉNIERIE GÉNÉRALE
    "construction_btp": [
        "construction_btp",
        "ingenierie",          # Ingé mécanique/industrie → BTP
        "industrie_production",
    ],
    "ingenierie": [
        "ingenierie",
        "construction_btp",
        "industrie_production",
        "informatique_dev",    # DevOps/cloud eng peut faire infrastructure
    ],
    "industrie_production": [
        "industrie_production",
        "ingenierie",
        "construction_btp",
    ],

    # FINANCE & BANQUE
    "finance_comptabilite": [
        "finance_comptabilite",
        "banque_assurance",    # Trésorier → Banque acceptable
    ],
    "banque_assurance": [
        "banque_assurance",
        "finance_comptabilite",
    ],

    # RH & ADMINISTRATION
    "ressources_humaines": [
        "ressources_humaines",
    ],

    # MARKETING & COMMUNICATION
    "marketing_communication": [
        "marketing_communication",
        "design_creatif",      # Designer → Marketing content
    ],
    "design_creatif": [
        "design_creatif",
        "marketing_communication",
    ],

    # LOGISTIQUE — STRICTEMENT LOGISTIQUE
    # (Responsable logistique ≠ ingénieur BTP)
    "logistique_transport": [
        "logistique_transport",
    ],

    # SANTÉ — STRICTEMENT SANTÉ
    "sante_medical": [
        "sante_medical",
    ],

    # ÉDUCATION
    "education": [
        "education",
    ],

    # JURIDIQUE
    "droit_juridique": [
        "droit_juridique",
    ],

    # ÉTUDIANT / STAGE (flexible — peut commencer n'importe où)
    "etudiant_stage": [
        "etudiant_stage",
        "informatique_dev",
        "ingenierie",
        "finance_comptabilite",
        "ressources_humaines",
        "marketing_communication",
        "logistique_transport",
        "droit_juridique",
        "design_creatif",
        "education",
        "sante_medical",
        "construction_btp",
        "industrie_production",
        "reseaux_cyber",
        "banque_assurance",
    ],
}


def domain_match(candidate_domain, job_category):
    """
    Vérifie si le domaine du candidat est compatible avec la catégorie du poste.
    
    COMPORTEMENT STRICT:
    - Si le poste exige un domaine, seuls les candidats de ce domaine (ou compatibles)
      sont acceptés.
    - Les transitions inappropriées (ex: Logistique → BTP) sont REJETÉES.
    - Les étudiants/stagiaires ont accès à tous les domaines.
    
    Retourne True si compatible, False sinon.
    """
    if not job_category:
        # Si aucune catégorie n'est spécifiée, tous les domaines sont acceptés
        return True
    
    allowed = DOMAIN_COMPATIBILITY.get(job_category, [])
    
    # Si la catégorie du poste n'existe pas dans la matrice, la rejeter
    if not allowed and job_category not in DOMAIN_COMPATIBILITY:
        return False
    
    return candidate_domain in allowed


def passes_screening(candidate, job):
    screening = job.screening_questions or {}

    # DOMAIN CHECK
    if not domain_match(candidate.domain, job.category):
        return False

    # EXPERIENCE
    minimum_experience = screening.get("minimum_experience", 0)

    if candidate.years_experience < minimum_experience:
        return False

    # DEGREE
    required_degree = screening.get("minimum_degree", "")

    candidate_degree_level = DEGREE_ORDER.get(
        candidate.highest_degree or "",
        0,
    )
    required_degree_level = DEGREE_ORDER.get(
        required_degree,
        0,
    )

    if candidate_degree_level < required_degree_level:
        return False

    # CERTIFICATIONS
    required_certs = screening.get(
        "required_certifications",
        [],
    )

    if required_certs:
        candidate_certs = [
            cert.lower()
            for cert in (candidate.certifications or [])
        ]
        for cert in required_certs:
            if cert.lower() not in candidate_certs:
                return False

    return True