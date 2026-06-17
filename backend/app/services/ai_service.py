# backend/app/services/ai_service.py
"""
AI Service — multi-provider with fallback chain.
Version finale restreinte avec consignes strictes d'extraction (zéro autonomie d'interprétation).
"""
from __future__ import annotations

import json
import re
import logging
from typing import Any, Dict, List

import requests
import google.generativeai as genai

from app.config import get_settings
from app.services.scoring_service import compute_candidate_score
from app.services.cv_extractor import CVExtractor
from app.services.cv_evaluator import CVEvaluator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict:
    """
    Nettoie et parse de façon robuste les réponses JSON de l'IA,
    notamment en retirant les délimiteurs markdown de bloc de code.
    """
    if not text:
        raise ValueError("Réponse de l'IA vide")

    # Suppression des balises markdown ```json ou ``` au début et ``` à la fin