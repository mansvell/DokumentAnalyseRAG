#récupérer des PDFs (ex: Bundestag)
#les stocker dans data/raw
#les enregistrer dans SQLite
#téléchargement PDF
#insertion dans documents
#insertion dans vorgaenge

import requests
import sqlite3
from pathlib import Path
from datetime import datetime

API_KEY = "OSOegLs.PR2lwJ1dwCeje9vTj7FPOt3hvpYKtwKkhw"

BASE_URLS = [
    ("https://search.dip.bundestag.de/api/v1/drucksache", "drucksache")

]

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "raw"
DB_PATH = BASE_DIR / "db" / "dbsqlite" / "think_ai.db"
#conn = sqlite3.connect(DB_PATH, timeout=10)
def fetch_documents(base_url, page):
    params = {
        "apikey": API_KEY,
        "format": "json",
        "rows": 15,
        "page": page
    }

    response = requests.get(base_url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("documents", [])


def download_pdf(url, filename):
    filepath = DATA_DIR / filename
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if filepath.exists():
        return str(filepath)

    r = requests.get(url, timeout=60)
    if r.status_code == 200:
        with open(filepath, "wb") as f:
            f.write(r.content)
        print(f"PDF geladen: {filename}")
        return str(filepath)

    return None


def run():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    max_docs = 70
    count = 0
    for base_url, doc_type_fixed in BASE_URLS:
        print(f"\n=== Quelle: {base_url} ===")

        for page in range(1, 5):
            docs = fetch_documents(base_url, page)

            for doc in docs:
                if count >= max_docs:
                    break
                dip_id = doc.get("id")
                titel = doc.get("titel") or "kein Titel"
                datum = doc.get("datum")
                source_org = doc.get("herausgeber")
                pdf_url = None

                fundstelle = doc.get("fundstelle")
                if isinstance(fundstelle, dict):
                    pdf_url = fundstelle.get("pdf_url")

                if not pdf_url:
                    continue

                filename = pdf_url.split("/")[-1]
                filepath = download_pdf(pdf_url, filename)

                if not filepath:
                    continue
                count += 1

                vorgang_id = None

                vorgangsbezug = doc.get("vorgangsbezug")
                if isinstance(vorgangsbezug, list) and len(vorgangsbezug) > 0:
                    vorgang_dip_id = vorgangsbezug[0].get("id")

                    cursor.execute("""
                        SELECT id FROM vorgaenge WHERE dip_id = ?
                    """, (vorgang_dip_id,))

                    result = cursor.fetchone()
                    if result:
                        vorgang_id = result[0]

                cursor.execute("""
                    INSERT OR IGNORE INTO documents
                    (dip_id, vorgang_id, filename, filepath, titel, datum, doc_type, source_org, pdf_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, ( dip_id, vorgang_id, filename, filepath,titel,datum, doc_type_fixed, source_org, pdf_url ))

                cursor.execute("""
                    UPDATE documents
                    SET vorgang_id = ?, titel = ?,datum = ?,doc_type = ?, source_org = ?,pdf_url = ?
                    WHERE filepath = ?
                """, ( vorgang_id,titel, datum, doc_type_fixed,source_org, pdf_url, filepath ))

                print(f"Gespeichert: {titel}")

    conn.commit()
    conn.close()
    print("Crawler fertig !")


if __name__ == "__main__":
    run()