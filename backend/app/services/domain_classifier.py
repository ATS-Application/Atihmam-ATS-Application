# backend/app/services/domain_classifier.py
"""
Thin adapter — delegates to the canonical domain classifier in scoring_service.
"""
from app.services.scoring_service import Domain, classify_domain


def detect_domain(
    cv_text: str = "",
    job_title: str = "",
    job_requirements: str = "",
) -> str:
    """
    Returns the domain label string (e.g. 'tech', 'finance').
    Returns 'uncategorized' only when all three inputs are empty.
    """
    if not any([cv_text, job_title, job_requirements]):
        return "uncategorized"

    combined_title = job_title or cv_text
    combined_description = job_requirements or cv_text
    return classify_domain(combined_title, combined_description)
