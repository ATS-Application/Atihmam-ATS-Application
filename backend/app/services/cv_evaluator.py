# backend/app/services/cv_evaluator.py
"""
Module d'Évaluation de CV - Atihmam ATS
Scoring déterministe candidat ↔ mots-clés requis pour un poste.
"""

from __future__ import annotations

from typing import Any


class CVEvaluator:
    @staticmethod
    def compute_deterministic_score(
        candidate_skills: list[str],
        required_keywords: list[str],
    ) -> dict[str, Any]:
        """
        Compare les compétences extraites du CV avec les mots-clés requis pour le poste ciblé.
        Cette évaluation est 100% déterministe et n'invente rien.
        """
        if not required_keywords:
            return {
                "score": 0,
                "matched_keywords": [],
                "missing_keywords": [],
                "total_required": 0,
            }

        candidate_set = {skill.lower().strip() for skill in candidate_skills if skill}
        required_set = {kw.lower().strip() for kw in required_keywords if kw}

        matched = list(required_set.intersection(candidate_set))
        missing = list(required_set.difference(candidate_set))
        score = int((len(matched) / len(required_set)) * 100) if required_set else 0

        return {
            "score": score,
            "matched_keywords": matched,
            "missing_keywords": missing,
            "total_required": len(required_set),
        }
