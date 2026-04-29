def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    """Teilt Text in einfache überlappende Chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += max(1, chunk_size - overlap)
    return chunks
