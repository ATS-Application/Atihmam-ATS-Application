# backend/app/services/cv_extractor.py
"""
Module d'Extraction de CV - Atihmam ATS
Responsable de la lecture physique des documents (PDF)
et de l'extraction structurée brute des données textuelles.
"""

from __future__ import annotations

import io
import logging

import pdfplumber

logger = logging.getLogger(__name__)

MAX_PROMPT_TEXT_LENGTH = 8_000


class CVExtractor:
    MAX_PAGES = 30

    @staticmethod
    def clean_text(text: str) -> str:
        """Nettoie le texte extrait du PDF pour éliminer les caractères parasites."""
        if not text:
            return ""
        text = text.replace("\x00", " ")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    @staticmethod
    def extract_text_from_bytes(pdf_bytes: bytes) -> str:
        """Extrait en toute sécurité le texte brut des octets d'un PDF."""
        if not pdf_bytes:
            return ""

        text_parts: list[str] = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                total_pages = min(len(pdf.pages), CVExtractor.MAX_PAGES)
                for i in range(total_pages):
                    page = pdf.pages[i]
                    try:
                        page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
                        if page_text:
                            cleaned = CVExtractor.clean_text(page_text)
                            if cleaned:
                                text_parts.append(cleaned)
                    except Exception as exc:
                        logger.warning(
                            "Erreur lors de l'extraction de la page %d: %s", i + 1, exc
                        )
        except Exception as exc:
            logger.error("Erreur lors de l'ouverture du PDF: %s", exc)

        return "\n".join(text_parts)

    @staticmethod
    def build_strict_extraction_prompt(raw_text: str) -> str:
        """Génère le prompt strict interdisant toute interprétation ou ajout par l'IA."""
        safe_text = raw_text[:MAX_PROMPT_TEXT_LENGTH]
        return f"""
Tu es un moteur de parsing technique de CV ultra-rigoureux.
Ta tâche est de transcrire les données textuelles brutes du CV en un format JSON structuré et propre.

### CONSIGNES DE SÉCURITÉ ET DE RIGUEUR (STRICTES) :
1. Ne déduis PAS de compétences sous-jacentes. Si le candidat écrit "Python" mais n'écrit pas "FastAPI", tu ne dois pas ajouter "FastAPI".
2. N'interprète PAS l'expérience. Extrais uniquement les informations de manière littérale.
3. Ne propose pas de poste alternatif, de reconversion ou de domaine d'activité.
4. Si un champ est absent ou vide, mets une liste vide [] ou null.

### TEXTE BRUT DU CV DU CANDIDAT :
{safe_text}

### SCHÉMA DE SORTIE JSON ATTENDU :
{{
    "full_name": "Nom complet du candidat (ou null)",
    "email": "Adresse email détectée (ou null)",
    "phone": "Numéro de téléphone détecté (ou null)",
    "current_position": "Intitulé exact du poste actuel ou principal écrit sur le CV (ou null)",
    "experience_years": 0.0,
    "summary": "Résumé professionnel tel qu'écrit sur le CV (ou null)",
    "skills": ["compétence_1_du_cv", "compétence_2_du_cv"],
    "work_history": [
        {{
            "title": "Intitulé du poste",
            "company": "Entreprise",
            "start_date": "YYYY-MM ou null",
            "end_date": "YYYY-MM ou null",
            "duration_months": null,
            "description": "Description littérale des missions"
        }}
    ],
    "projects": [],
    "certifications": ["certification_1", "certification_2"],
    "education": [
        {{
            "degree": "Diplôme",
            "institution": "Établissement",
            "year": null
        }}
    ],
    "languages": []
}}

Réponds UNIQUEMENT avec le bloc JSON valide, sans markdown additionnel.
"""


def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """Compatibilité avec cv_parser / cv_processing."""
    return CVExtractor.extract_text_from_bytes(pdf_bytes)


def extract_text_from_path(file_path: str) -> str:
    """Extrait le texte d'un PDF local."""
    try:
        with open(file_path, "rb") as handle:
            return extract_text_from_bytes(handle.read())
    except OSError as exc:
        logger.error("Impossible d'ouvrir le PDF %s: %s", file_path, exc)
        return ""
