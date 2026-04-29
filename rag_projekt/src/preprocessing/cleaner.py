import re


def clean_text(text: str) -> str:
    """Einfache Bereinigung von Text."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"Seite\s+\d+", "", text, flags=re.IGNORECASE)
    return text.strip()
