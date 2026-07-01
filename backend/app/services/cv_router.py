# backend/app/services/cv_router.py
"""
Module de Routage de CV - Atihmam ATS
Associe un candidat à un domaine métier issu de CLASSIFICATION_RULES.
"""

from __future__ import annotations

import re
import unicodedata

from app.config.classification_rules import CLASSIFICATION_RULES

TITLE_WEIGHT = 10.0
BODY_WEIGHT = 1.0
DEFAULT_DOMAIN = "autres"


class CVRouter:
    @staticmethod
    def normalize(text: str) -> str:
        """Normalise le texte pour les comparaisons : minuscules, sans accent ni ponctuation."""
        if not text:
            return ""
        text = text.lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        text = re.sub(r"[^\w\s\-/]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def get_keyword_pattern(keyword: str) -> str:
        """Génère un pattern regex flexible pour l'accord des mots-clés."""
        keyword = keyword.lower().strip()
        keyword = re.escape(keyword)
        return rf"\b{keyword}\w*\b"

    @staticmethod
    def _score_text(normalized_text: str, weight: float, domain_scores: dict[str, float]) -> None:
        if not normalized_text:
            return
        for rule in CLASSIFICATION_RULES:
            domain = rule["domain"]
            domain_scores.setdefault(domain, 0.0)
            for keyword in rule.get("keywords", []):
                keyword_norm = CVRouter.normalize(keyword)
                pattern = CVRouter.get_keyword_pattern(keyword_norm)
                matches = re.findall(pattern, normalized_text)
                domain_scores[domain] += len(matches) * weight

    @staticmethod
    def assign_domain_strictly(extracted_title: str, full_text: str) -> str:
        """
        Assigne un domaine basé sur l'intitulé (poids fort) puis le corps du CV (poids faible).
        Renvoie 'autres' si aucune correspondance.
        """
        if not extracted_title and not full_text:
            return DEFAULT_DOMAIN

        normalized_title = CVRouter.normalize(extracted_title)
        normalized_text = CVRouter.normalize(full_text)
        domain_scores: dict[str, float] = {}

        CVRouter._score_text(normalized_title, TITLE_WEIGHT, domain_scores)
        CVRouter._score_text(normalized_text, BODY_WEIGHT, domain_scores)

        if not domain_scores or max(domain_scores.values()) == 0.0:
            return DEFAULT_DOMAIN

        return max(domain_scores, key=lambda domain: (domain_scores[domain], domain))
backend/app/services/cv_router.py
