import sqlite3
from pathlib import Path
import uuid

from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

DB_PATH = BASE_DIR / "db" / "dbsqlite" / "think_ai.db"
VECTOR_PATH = BASE_DIR / "db" / "vector_store"

embedding = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")


def build_index():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            c.id,
            c.content,
            c.document_id,
            c.page_number,
            d.filename,
            d.titel,
            d.datum,
            d.doc_type,
            d.source_org,
            d.pdf_url
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.chroma_id IS NULL
    """)
    rows = cursor.fetchall() #Gibt alle Zeilen des Ergebnisses zurück

    if not rows:
        print("Keine neuen Chunks zu indexieren")
        conn.close()
        return

    texts = []
    metadatas = []
    ids = []

    for (chunk_id, content, document_id, page_number,filename,titel, datum,doc_type,source_org,pdf_url) in rows:

        chroma_id = str(uuid.uuid4()) #generiere ein zufälliges String sichtbar in Chroma_id in sqlite

        texts.append(content)
        metadatas.append({
            "chunk_id": chunk_id,
            "document_id": document_id,
            "page_number": page_number if page_number is not None else "",
            "filename": filename or "",
            "titel": titel or "",
            "datum": datum or "",
            "doc_type": doc_type or "",
            "source_org": source_org or "",
            "pdf_url": pdf_url or ""
        })
        ids.append(chroma_id)

    db = Chroma(
        persist_directory=str(VECTOR_PATH),
        embedding_function=embedding
    )

    BATCH_SIZE = 5000        #ich sende die Chunks in Stücke von 5000 ,um eine Überschreitung zu vermeiden
                            # um nicht alle 74745 auf einmal zu senden. max batch size of 5461
    for i in range(0, len(texts), BATCH_SIZE):
        batch_texts = texts[i:i + BATCH_SIZE]
        batch_metadatas = metadatas[i:i + BATCH_SIZE]
        batch_ids = ids[i:i + BATCH_SIZE]

        db.add_texts(                                # ChromaDB berechnet automatisch die Embeddings und speichert
            texts=batch_texts,
            metadatas=batch_metadatas,
            ids=batch_ids
        )

    for i, (chunk_id, *_rest) in enumerate(rows):     #Chroma_id in sqlite speichern(in jeder Chunk)
        cursor.execute("""
            UPDATE chunks
            SET chroma_id = ?
            WHERE id = ?
        """, (ids[i], chunk_id))

    conn.commit()
    conn.close()

    db.persist()

    print(f"{len(rows)} Chunks in Chroma gespeichert!")


if __name__ == "__main__":
    build_index()