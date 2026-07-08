# # backend/app/services/cv_extractor.py
# """
# Module d'Extraction de CV - Atihmam ATS
# Responsable de la lecture physique des documents (PDF)
# et de l'extraction structurée brute des données textuelles.
# """

# from __future__ import annotations

# import io
# import logging

# import pdfplumber

# logger = logging.getLogger(__name__)

# MAX_PROMPT_TEXT_LENGTH = 8_000


# class CVExtractor:
#     MAX_PAGES = 30

#     @staticmethod
#     def clean_text(text: str) -> str:
#         """Nettoie le texte extrait du PDF pour éliminer les caractères parasites."""
#         if not text:
#             return ""
#         text = text.replace("\x00", " ")
#         lines = [line.strip() for line in text.splitlines() if line.strip()]
#         return "\n".join(lines)

#     @staticmethod
#     def extract_text_from_bytes(pdf_bytes: bytes) -> str:
#         """Extrait en toute sécurité le texte brut des octets d'un PDF."""
#         if not pdf_bytes:
#             return ""

#         text_parts: list[str] = []
#         try:
#             with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
#                 total_pages = min(len(pdf.pages), CVExtractor.MAX_PAGES)
#                 for i in range(total_pages):
#                     page = pdf.pages[i]
#                     try:
#                         page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
#                         if page_text:
#                             cleaned = CVExtractor.clean_text(page_text)
#                             if cleaned:
#                                 text_parts.append(cleaned)
#                     except Exception as exc:
#                         logger.warning(
#                             "Erreur lors de l'extraction de la page %d: %s", i + 1, exc
#                         )
#         except Exception as exc:
#             logger.error("Erreur lors de l'ouverture du PDF: %s", exc)

#         return "\n".join(text_parts)

#     @staticmethod
#     def build_strict_extraction_prompt(raw_text: str) -> str:
#         """Génère le prompt strict interdisant toute interprétation ou ajout par l'IA."""
#         safe_text = raw_text[:MAX_PROMPT_TEXT_LENGTH]
#         return f"""
# Tu es un moteur de parsing technique de CV ultra-rigoureux.
# Ta tâche est de transcrire les données textuelles brutes du CV en un format JSON structuré et propre.

# ### CONSIGNES DE SÉCURITÉ ET DE RIGUEUR (STRICTES) :
# 1. Ne déduis PAS de compétences sous-jacentes. Si le candidat écrit "Python" mais n'écrit pas "FastAPI", tu ne dois pas ajouter "FastAPI".
# 2. N'interprète PAS l'expérience. Extrais uniquement les informations de manière littérale.
# 3. Ne propose pas de poste alternatif, de reconversion ou de domaine d'activité.
# 4. Si un champ est absent ou vide, mets une liste vide [] ou null.

# ### TEXTE BRUT DU CV DU CANDIDAT :
# {safe_text}

# ### SCHÉMA DE SORTIE JSON ATTENDU :
# {{
#     "full_name": "Nom complet du candidat (ou null)",
#     "email": "Adresse email détectée (ou null)",
#     "phone": "Numéro de téléphone détecté (ou null)",
#     "current_position": "Intitulé exact du poste actuel ou principal écrit sur le CV (ou null)",
#     "experience_years": 0.0,
#     "summary": "Résumé professionnel tel qu'écrit sur le CV (ou null)",
#     "skills": ["compétence_1_du_cv", "compétence_2_du_cv"],
#     "work_history": [
#         {{
#             "title": "Intitulé du poste",
#             "company": "Entreprise",
#             "start_date": "YYYY-MM ou null",
#             "end_date": "YYYY-MM ou null",
#             "duration_months": null,
#             "description": "Description littérale des missions"
#         }}
#     ],
#     "projects": [],
#     "certifications": ["certification_1", "certification_2"],
#     "education": [
#         {{
#             "degree": "Diplôme",
#             "institution": "Établissement",
#             "year": null
#         }}
#     ],
#     "languages": []
# }}

# Réponds UNIQUEMENT avec le bloc JSON valide, sans markdown additionnel.
# """


# def extract_text_from_bytes(pdf_bytes: bytes) -> str:
#     """Compatibilité avec cv_parser / cv_processing."""
#     return CVExtractor.extract_text_from_bytes(pdf_bytes)


# def extract_text_from_path(file_path: str) -> str:
#     """Extrait le texte d'un PDF local."""
#     try:
#         with open(file_path, "rb") as handle:
#             return extract_text_from_bytes(handle.read())
#     except OSError as exc:
#         logger.error("Impossible d'ouvrir le PDF %s: %s", file_path, exc)
#         return ""
# backend/app/services/cv_extractor.py
"""
Module d'Extraction de CV - Atihmam ATS
=========================================
Responsable de la lecture physique et de l'extraction de texte brute de tous types
de documents : PDF natifs, fichiers Microsoft Word (.docx), et images scannées
ou photographiées (.png, .jpeg, .webp) grâce aux capacités multimodales de l'IA.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
import logging

import pdfplumber

logger = logging.getLogger(__name__)

MAX_PROMPT_TEXT_LENGTH = 8_000


class CVExtractor:
    MAX_PAGES = 30

    @staticmethod
    def clean_text(text: str) -> str:
        """Nettoie le texte extrait pour éliminer les caractères parasites."""
        if not text:
            return ""
        text = text.replace("\x00", " ")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    @staticmethod
    def _extract_from_pdf(pdf_bytes: bytes) -> str:
        """Extrait en toute sécurité le texte brut des octets d'un PDF."""
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
                    except Exception as e:
                        logger.error(f"[Extractor] Erreur lors de l'extraction de la page PDF {i}: {e}")
        except Exception as e:
            logger.error(f"[Extractor] Erreur lors de l'ouverture du document PDF: {e}")
        return "\n".join(text_parts)

    @staticmethod
    def _extract_from_docx(docx_bytes: bytes) -> str:
        """
        Extrait nativement et sans dépendance externe le texte structuré
        d'un document Microsoft Word (.docx) en analysant son fichier XML interne.
        """
        try:
            paragraphs = []
            with zipfile.ZipFile(io.BytesIO(docx_bytes)) as docx:
                # Lecture du fichier XML principal contenant le texte
                xml_content = docx.read('word/document.xml')
                root = ET.fromstring(xml_content)
                
                # Namespaces Word XML pour localiser les paragraphes <w:p> et le texte <w:t>
                ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                
                for p in root.findall('.//w:p', ns):
                    p_text = "".join([t.text for t in p.findall('.//w:t', ns) if t.text])
                    if p_text.strip():
                        paragraphs.append(p_text.strip())
                        
            text = "\n".join(paragraphs)
            logger.info(f"[Extractor] Extraction DOCX réussie ({len(text)} caractères extraits).")
            return CVExtractor.clean_text(text)
        except Exception as e:
            logger.error(f"[Extractor] Erreur lors de la lecture du fichier Word DOCX : {e}")
            return ""

    @staticmethod
    def _extract_from_image_via_gemini(image_bytes: bytes, mime_type: str) -> str:
        """
        Analyse une image de CV (photographiée ou scannée) et utilise la vision
        de Gemini pour en faire une retranscription OCR ultra-fidèle.

        Logique de secours multi-modèles (Failover) :
        En cas de quota épuisé (ResourceExhausted), passe automatiquement
        au modèle suivant dans GEMINI_MODELS_TO_TRY.
        """
        # Liste ordonnée des modèles Vision à essayer (identique à ai_service)
        GEMINI_MODELS_TO_TRY = [
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]

        try:
            from app.config import get_settings
            settings = get_settings()
            api_key = settings.gemini_api_key or ""

            if not api_key:
                logger.error("[Extractor] Clé API Gemini manquante pour l'extraction OCR d'image.")
                return ""

            from google import genai as new_genai
            from google.genai import types as genai_types
            from google.api_core.exceptions import ResourceExhausted

            client = new_genai.Client(api_key=api_key)

            prompt = (
                "Tu es un lecteur de document (OCR) de très haute précision pour un ATS de recrutement.\n"
                "Transcris fidèlement et textuellement l'intégralité du contenu visible de cette image de CV.\n"
                "Conserve l'organisation logique du document (expériences, formations, compétences).\n"
                "Ne fais aucun résumé ni commentaire, retourne UNIQUEMENT les textes présents réels."
            )

            last_exc: Exception | None = None

            for model_name in GEMINI_MODELS_TO_TRY:
                try:
                    logger.info(
                        "[Extractor] Tentative OCR avec le modèle '%s' pour image (%s)...",
                        model_name, mime_type,
                    )
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[
                            genai_types.Part.from_text(text=prompt),
                            genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        ],
                    )

                    if response and response.text:
                        print(f"Modèle utilisé avec succès : {model_name}")
                        logger.info(
                            "[Extractor] Transcription OCR réussie avec le modèle '%s'.",
                            model_name,
                        )
                        return CVExtractor.clean_text(response.text)

                    # Réponse vide mais pas d'exception → on continue avec le modèle suivant
                    logger.warning("[Extractor] Réponse vide du modèle '%s', passage au suivant.", model_name)

                except ResourceExhausted as exc:
                    logger.warning(
                        "[Extractor] Quota épuisé pour le modèle OCR '%s' — passage au suivant. Détail : %s",
                        model_name, exc,
                    )
                    last_exc = exc
                except Exception:
                    # Toute autre erreur non-quota est propagée immédiatement
                    raise

            logger.error(
                "[Extractor] Tous les modèles Gemini sont saturés pour l'OCR. Dernière erreur : %s",
                last_exc,
            )
            return ""

        except Exception as e:
            logger.error(f"[Extractor] Erreur critique lors de la transcription OCR de l'image : {e}")
            return ""

    @staticmethod
    def extract_text_from_bytes(file_bytes: bytes) -> str:
        """
        Point d'entrée principal. Détecte dynamiquement la signature du fichier
        (Magic Bytes) pour l'orienter vers la bonne méthode d'extraction.
        """
        if not file_bytes:
            return ""

        # 1. Détection du format PDF
        if file_bytes.startswith(b'%PDF'):
            logger.info("[Extractor] Type de document détecté : PDF.")
            return CVExtractor._extract_from_pdf(file_bytes)
            
        # 2. Détection du format Microsoft Word (.docx) - Signature d'archive Zip
        elif file_bytes.startswith(b'PK\x03\x04'):
            logger.info("[Extractor] Type de document détecté : Word DOCX.")
            return CVExtractor._extract_from_docx(file_bytes)
            
        # 3. Détection des formats d'images
        elif file_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
            logger.info("[Extractor] Type de document détecté : Image PNG. Activation de l'OCR Vision...")
            return CVExtractor._extract_from_image_via_gemini(file_bytes, "image/png")
            
        elif file_bytes.startswith(b'\xff\xd8\xff'):
            logger.info("[Extractor] Type de document détecté : Image JPEG. Activation de l'OCR Vision...")
            return CVExtractor._extract_from_image_via_gemini(file_bytes, "image/jpeg")
            
        elif file_bytes.startswith(b'RIFF') and b'WEBP' in file_bytes[8:12]:
            logger.info("[Extractor] Type de document détecté : Image WEBP. Activation de l'OCR Vision...")
            return CVExtractor._extract_from_image_via_gemini(file_bytes, "image/webp")
            
        else:
            # Fallback par défaut si aucune signature d'image ou word n'est évidente
            logger.warning("[Extractor] Format brut non identifié de prime abord. Tentative de lecture PDF standard...")
            try:
                return CVExtractor._extract_from_pdf(file_bytes)
            except Exception:
                logger.error("[Extractor] Impossible de lire le fichier brut.")
                return ""

    @staticmethod
    def build_strict_extraction_prompt(raw_text: str) -> str:
        """Génère le prompt d'extraction strict interdisant l'interprétation par l'IA."""
        return f"""
Tu es un moteur de parsing de CV ultra-rigoureux. 
Ta tâche est de transcrire les données textuelles brutes du CV en un format JSON structuré et propre.

### CONSIGNES DE SÉCURITÉ ET DE RIGUEUR (STRICTES) :
1. Ne déduis PAS de compétences sous-jacentes. Si le candidat écrit "Python" mais n'écrit pas "FastAPI", tu ne dois pas ajouter "FastAPI".
2. N'interprète PAS l'expérience. Extrais uniquement les informations de manière littérale.
3. Ne propose pas de poste alternatif, de reconversion ou de domaine d'activité.
4. Si un champ est absent ou vide, mets une liste vide [] ou null.

### TEXTE BRUT DU CV DU CANDIDAT :
{raw_text}

### SCHÉMA DE SORTIE JSON ATTENDU :
{{
    "full_name": "Nom complet du candidat (ou 'Inconnu')",
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
    """Lit un fichier local et extrait son texte brut."""
    try:
        with open(file_path, "rb") as f:
            return CVExtractor.extract_text_from_bytes(f.read())
    except Exception as e:
        logger.error(f"[Extractor] Erreur lors de la lecture du fichier {file_path} : {e}")
        return ""