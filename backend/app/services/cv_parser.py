# backend/app/services/cv_parser.py

import io
import pdfplumber

from app.services.cv_classifier import classify_cv
from app.services.domain_classifier import detect_domain
from app.config.classification_rules import CLASSIFICATION_RULES


MAX_PAGES = 30


# ─────────────────────────────────────────────────────────────
# TEXT CLEANING
# ─────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """
    Cleans extracted PDF text.
    """
    if not text:
        return ""

    text = text.replace("\x00", " ")

    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# PDF EXTRACTION
# ─────────────────────────────────────────────────────────────

def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """
    Extract text from PDF bytes safely.
    """
    if not pdf_bytes:
        return ""

    text_parts: list[str] = []

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:

            total_pages = min(len(pdf.pages), MAX_PAGES)

            for i in range(total_pages):
                page = pdf.pages[i]

                try:
                    page_text = page.extract_text(
                        x_tolerance=2,
                        y_tolerance=2,
                    )

                    if page_text:
                        cleaned = clean_text(page_text)
                        if cleaned:
                            text_parts.append(cleaned)

                except Exception as e:
                    print(f"[PDF WARNING] Page {i + 1}: {e}")

    except Exception as e:
        print(f"[PDF ERROR] Failed to parse PDF: {e}")
        return ""

    return "\n\n".join(text_parts)


# ─────────────────────────────────────────────────────────────
# LOCAL FILE SUPPORT
# ─────────────────────────────────────────────────────────────

def extract_text_from_path(file_path: str) -> str:
    """
    Extract text from a local PDF file path.
    """
    try:
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()

        return extract_text_from_bytes(pdf_bytes)

    except Exception as e:
        print(f"[FILE ERROR] Could not open PDF: {e}")
        return ""


# ─────────────────────────────────────────────────────────────
# DOMAIN VALUE MAP
# Maps detect_domain() enum .value strings → internal domain keys
# Update these if your Domain enum values differ.
# Run to check: python -c "from app.services.scoring_service import Domain; [print(d.value) for d in Domain]"
# ─────────────────────────────────────────────────────────────

DOMAIN_VALUE_MAP: dict[str, str] = {
    "Informatique & Développement logiciel": "informatique_dev",
    "Réseaux & Cybersécurité":               "reseaux_cyber",
    "Construction & BTP":                    "construction_btp",
    "Ingénierie":                            "ingenierie",
    "Finance & Comptabilité":                "finance_comptabilite",
    "Banque & Assurance":                    "banque_assurance",
    "Ressources Humaines":                   "ressources_humaines",
    "Marketing & Communication":             "marketing_communication",
    "Logistique & Transport":                "logistique_transport",
    "Santé & Médical":                       "sante_medical",
    "Éducation":                             "education",
    "Droit & Juridique":                     "droit_juridique",
    "Design & Créatif":                      "design_creatif",
    "Industrie & Production":                "industrie_production",
    "Étudiant / Stage":                      "etudiant_stage",
}


# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────

def process_candidate_resume(candidate, extracted_text: str):
    """
    Full CV processing pipeline:
      1. Primary classifier  → weighted keyword scoring (cv_classifier.py)
      2. Fallback            → detect_domain() from scoring_service, mapped to internal key
      3. Last resort         → "autres"
    """
    if not extracted_text:
        print("[PIPELINE] Empty text — assigning 'autres'")
        candidate.domain = "autres"
        candidate.folder = "📁 Autres"
        return candidate

    # 1. Primary classifier — returns a clean key e.g. "construction_btp"
    domain = classify_cv(extracted_text)

    if domain:
        print(f"[PIPELINE] Primary classifier → {domain}")
    else:
        # 2. Fallback — detect_domain returns an enum .value string
        raw = detect_domain(extracted_text)
        print(f"[PIPELINE] Fallback detect_domain → '{raw}'")

        domain = DOMAIN_VALUE_MAP.get(raw)

        if domain:
            print(f"[PIPELINE] Mapped to → {domain}")
        else:
            print(f"[PIPELINE] No mapping found for '{raw}' — assigning 'autres'")

    # 3. Assign
    candidate.domain = domain or "autres"
    candidate.folder = candidate.domain

    return candidate