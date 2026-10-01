import sqlite3
from pathlib import Path
import uuid
import time
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

#Modif
class E5Embeddings( HuggingFaceEmbeddings ):
    def embed_documents(self, texts):
        texts = [f"passage: {text}" for text in texts] #Ce texte est un document/contenu à rechercher
        return super().embed_documents(texts)
    def embed_query(self, text):
        return super().embed_query(f"query: {text}") #Ce texte est une requête qui cherche quelque chose.

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

DB_PATH = BASE_DIR / "db" / "dbsqlite" / "think_ai.db"
VECTOR_PATH = BASE_DIR / "db" / "vector_store_vorgaenge"

embedding = E5Embeddings(
    model_name="intfloat/multilingual-e5-base",
    encode_kwargs={"normalize_embeddings": True,
                   "batch_size": 32}
)

def build_vorgang_index():
    #Liest alle Vorgänge aus SQLite und speichert sie als Vektoren in Chroma.
    #Jeder Vorgang wird als kurzer Text (Titel + Typ) gespeichert.
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, dip_id, titel, vorgangstyp, datum_erstellt, datum_aktualisiert
        FROM vorgaenge
    """)
    rows = cursor.fetchall()

    if not rows:
        print("Keine Vorgänge gefunden")
        conn.close()
        return

    texts = []
    metadatas = []
    ids = []
    for ( vorgang_id, dip_id, titel, vorgangstyp, datum_erstellt,datum_aktualisiert) in rows:

        text = f"""
        Titel: {titel or ""}
        Typ: {vorgangstyp or ""}
        """
        texts.append(text)

        #Metadaten (damit wir später vorgang_id zurückbekommen)
        metadatas.append({
            "vorgang_id": vorgang_id,
            "dip_id": dip_id or "",
            "titel": titel or "",
            "vorgangstyp": vorgangstyp or "",
            "datum_erstellt": datum_erstellt or "",
            "datum_aktualisiert": datum_aktualisiert or ""
        })
        ids.append(str(uuid.uuid4())) #eindeutige ID für Chroma

    db =Chroma( persist_directory=str(VECTOR_PATH),embedding_function=embedding )

    # MODIF: Vorgänge in kleineren Batches indexieren und Fortschritt anzeigen
    BATCH_SIZE = 100
    total_vorgaenge = len(texts)
    start_time = time.perf_counter()

    print(f"\nIndexierung gestartet: {total_vorgaenge} Vorgänge")

    for i in range(0, total_vorgaenge, BATCH_SIZE):
        batch_texts = texts[i:i + BATCH_SIZE]
        batch_metadatas = metadatas[i:i + BATCH_SIZE]
        batch_ids = ids[i:i + BATCH_SIZE]

        db.add_texts( texts=batch_texts, metadatas=batch_metadatas, ids=batch_ids )

        processed = min(i + BATCH_SIZE, total_vorgaenge) #Restzeit der Ausführung in der Konsole zu haben
        elapsed = time.perf_counter() - start_time
        progress = processed / total_vorgaenge

        remaining = (
            elapsed / progress - elapsed
            if progress > 0
            else 0
        )

        print(
            f"[{processed}/{total_vorgaenge}] "
            f"{progress * 100:.2f}% | "
            f"Vergangen: {elapsed / 60:.1f} min | "
            f"Rest ca.: {remaining / 60:.1f} min"
        )

    conn.close()
    db.persist()
    print(f"{len(rows)} Vorgänge in Vektor-DB gespeichert!")


if __name__ == "__main__":
    build_vorgang_index()