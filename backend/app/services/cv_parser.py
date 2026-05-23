# app/services/cv_parser.py
import io
import pdfplumber


MAX_PAGES = 30


def clean_text(text: str) -> str:
    """
    Cleans extracted PDF text.
    """

    if not text:
        return ""

    text = text.replace("\x00", " ")

    lines = [
        line.strip()
        for line in text.splitlines()
    ]

    lines = [
        line for line in lines
        if line
    ]

    return "\n".join(lines)


def extract_text_from_bytes(
    pdf_bytes: bytes,
) -> str:
    """
    Extract text from PDF bytes safely.
    """

    if not pdf_bytes:
        return ""

    text_parts: list[str] = []

    try:
        with pdfplumber.open(
            io.BytesIO(pdf_bytes)
        ) as pdf:

            total_pages = min(
                len(pdf.pages),
                MAX_PAGES,
            )

            for i in range(total_pages):
                page = pdf.pages[i]

                try:
                    page_text = (
                        page.extract_text(
                            x_tolerance=2,
                            y_tolerance=2,
                        )
                    )

                    if page_text:
                        cleaned = clean_text(
                            page_text
                        )

                        if cleaned:
                            text_parts.append(
                                cleaned
                            )

                except Exception as e:
                    print(
                        f"[PDF WARNING] "
                        f"Page {i + 1}: {e}"
                    )

    except Exception as e:
        print(
            f"[PDF ERROR] "
            f"Failed to parse PDF: {e}"
        )

        return ""

    return "\n\n".join(text_parts)


def extract_text_from_path(
    file_path: str,
) -> str:
    """
    Extract text from local PDF path.
    """

    try:
        with open(
            file_path,
            "rb",
        ) as f:
            pdf_bytes = f.read()

        return extract_text_from_bytes(
            pdf_bytes
        )

    except Exception as e:
        print(
            f"[FILE ERROR] "
            f"Could not open PDF: {e}"
        )

        return ""