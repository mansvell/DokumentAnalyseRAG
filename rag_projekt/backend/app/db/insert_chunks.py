#créer et enregistrer les chunks dans SQLite
#lire chaque PDF déjà enregistré dans documents
#effectuer les chunks et speichern en DB
import sqlite3
from pathlib import Path
import fitz
from langchain_text_splitters import RecursiveCharacterTextSplitter

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DB_PATH = BASE_DIR / "db" / "dbsqlite" / "think_ai.db"


def extract_text_by_page(pdf_path: str):
    pdf = fitz.open(pdf_path)
    pages = []

    for page_number, page in enumerate(pdf, start=1):
        text = page.get_text().strip()
        if text:
            pages.append((page_number, text))

    pdf.close()
    return pages


def insert_chunks():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )

    cursor.execute("SELECT id, filepath FROM documents")
    documents = cursor.fetchall()

    inserted_chunks = 0

    for document_id, filepath in documents:
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE document_id = ?", (document_id,))
        already_exists = cursor.fetchone()[0]

        if already_exists > 0: #wenn das erste Ergebnis(Chunks) exist, dann das gesamte Dok überspringen
            continue

        pages = extract_text_by_page(filepath)

        for page_number, page_text in pages:
            chunks = text_splitter.split_text(page_text)

            for chunk_index, chunk in enumerate(chunks):
                cursor.execute("""
                    INSERT INTO chunks (document_id, chunk_index, content, page_number)
                    VALUES (?, ?, ?, ?)
                """, (document_id, chunk_index, chunk, page_number))
                inserted_chunks += 1

    conn.commit()
    conn.close()

    print(f"{inserted_chunks} Chunks wurden eingefügt!")


if __name__ == "__main__":
    insert_chunks()