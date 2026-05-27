DEGREE_ORDER = {
    "": 0,
    "bachelor": 1,
    "master": 2,
    "phd": 3,
}


DOMAIN_COMPATIBILITY = {
    "software_engineering": [
        "software_engineering",
        "data_science",
        "devops",
    ],

    "human_resources": [
        "human_resources",
        "recruitment",
    ],
        "marketing": [
        "marketing",
    ],

    "finance": [
        "finance",
    ],

    "design": [
        "design",
    ],
}


def domain_match(candidate_domain, job_category):
    allowed = DOMAIN_COMPATIBILITY.get(job_category, [])
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