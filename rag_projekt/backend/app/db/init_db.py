import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DB_DIR = BASE_DIR / "db" / "dbsqlite"
DB_PATH = DB_DIR / "think_ai.db"

def init_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vorgaenge (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dip_id TEXT UNIQUE,
        titel TEXT NOT NULL,
        vorgangstyp TEXT,
        datum_erstellt TEXT,
        datum_aktualisiert TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dip_id TEXT UNIQUE,
        vorgang_id INTEGER,
        filename TEXT NOT NULL,
        filepath TEXT NOT NULL UNIQUE,
        titel TEXT,
        datum TEXT,
        doc_type TEXT,
        source_org TEXT,
        pdf_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (vorgang_id) REFERENCES vorgaenge(id) ON DELETE SET NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL,
        chunk_index INTEGER NOT NULL,
        content TEXT NOT NULL,
        chroma_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        page_number INTEGER,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    )
    """)

    conn.commit()
    conn.close()
    print(f"SQLite DB erstellt: {DB_PATH}")

if __name__ == "__main__":
    init_db()