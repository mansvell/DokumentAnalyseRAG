import sqlite3
from pathlib import Path
import uuid

from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

DB_PATH = BASE_DIR / "db" / "dbsqlite" / "think_ai.db"
VECTOR_PATH = BASE_DIR / "db" / "vector_store_vorgaenge"

embedding = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

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


    db.add_texts( texts=texts, metadatas=metadatas, ids=ids )

    conn.close()
    db.persist()
    print(f"{len(rows)} Vorgänge in Vektor-DB gespeichert!")


if __name__ == "__main__":
    build_vorgang_index()