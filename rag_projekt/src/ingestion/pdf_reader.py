from pathlib import Path
import fitz


def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """Liest ein PDF und gibt pro Seite Text zurück."""
    doc = fitz.open(pdf_path)
    pages = []
    for page_num, page in enumerate(doc, start=1):
        pages.append({
            "page": page_num,
            "text": page.get_text("text")
        })
    return pages


def list_pdfs(raw_dir: str) -> list[Path]:
    return sorted(Path(raw_dir).glob("*.pdf"))
