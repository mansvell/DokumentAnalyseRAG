from pathlib import Path
import json
import yaml

from src.ingestion.pdf_reader import extract_text_from_pdf, list_pdfs
from src.preprocessing.cleaner import clean_text
from src.chunking.chunker import chunk_text


def run_ingestion(config_path: str = "config/settings.yaml") -> None:
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    raw_dir = config["paths"]["raw_dir"]
    processed_dir = Path(config["paths"]["processed_dir"])
    chunks_dir = Path(config["paths"]["chunks_dir"])
    metadata_dir = Path(config["paths"]["metadata_dir"])
    processed_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    pdfs = list_pdfs(raw_dir)
    if not pdfs:
        print("Keine PDFs in data/raw gefunden.")
        return

    for pdf in pdfs:
        pages = extract_text_from_pdf(str(pdf))
        all_chunks = []
        metadata = []

        for page in pages:
            cleaned = clean_text(page["text"])
            text_file = processed_dir / f"{pdf.stem}_page_{page['page']}.txt"
            text_file.write_text(cleaned, encoding="utf-8")

            chunks = chunk_text(
                cleaned,
                chunk_size=config["chunking"]["chunk_size"],
                overlap=config["chunking"]["chunk_overlap"],
            )

            for idx, chunk in enumerate(chunks, start=1):
                chunk_id = f"{pdf.stem}_p{page['page']}_c{idx}"
                all_chunks.append({"chunk_id": chunk_id, "text": chunk})
                metadata.append({
                    "chunk_id": chunk_id,
                    "document": pdf.name,
                    "page": page["page"],
                })

        (chunks_dir / f"{pdf.stem}_chunks.json").write_text(
            json.dumps(all_chunks, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (metadata_dir / f"{pdf.stem}_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"Verarbeitet: {pdf.name}")
