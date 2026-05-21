# app/services/cv_parser.py
import pdfplumber
import io


def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                page_text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if page_text:
                    text_parts.append(page_text)
            except Exception as e:
                print(f"Warning: could not extract page {i}: {e}")
    return "\n\n".join(text_parts)


def extract_text_from_path(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return extract_text_from_bytes(f.read())