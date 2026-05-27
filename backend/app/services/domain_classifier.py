# backend/app/services/domain_classifier.py
"""
Thin adapter — delegates to the canonical domain classifier in scoring_service.
Import `detect_domain` from here for backward compatibility; prefer importing
`classify_domain` / `Domain` directly from scoring_service in new code.
"""
from app.services.scoring_service import Domain, classify_domain


def detect_domain(cv_text: str = "", job_title: str = "", job_requirements: str = "") -> str:
    """
    Returns the domain label string (e.g. 'Informatique & Développement logiciel').
    Returns 'uncategorized' only when all three inputs are empty.
    """
    if not any([cv_text, job_title, job_requirements]):
        return "uncategorized"

    return classify_domain(cv_text, job_title, job_requirements).value