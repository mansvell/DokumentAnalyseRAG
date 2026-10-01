#récupérer des PDFs (ex: Bundestag)
#les stocker dans data/raw
#les enregistrer dans SQLite
#téléchargement PDF
#insertion dans documents
#association des documents avec les Vorgänge existants

import requests
import sqlite3
from pathlib import Path
import os

API_KEY = os.getenv("DIP_API_KEY")

BASE_URLS = [
    ("https://search.dip.bundestag.de/api/v1/drucksache", "drucksache",60),
    ("https://search.dip.bundestag.de/api/v1/plenarprotokoll","plenarprotokoll",30 )
]

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "raw"
DB_PATH = BASE_DIR / "db" / "dbsqlite" / "think_ai.db"



def fetch_documents(base_url, cursor="*"):
    params = {
        "apikey": API_KEY,
        "format": "json",
        "rows": 20,
        "cursor": cursor
    }

    response = requests.get(base_url, params=params, timeout=30)
    response.raise_for_status() #Überprüfe, ob die HTTP-Anfrage erfolgreich ausgeführt wurde
    data = response.json()
    return data.get("documents", []), data.get("cursor")


def download_pdf(url, filename):
    filepath = DATA_DIR / filename #data/raw/2101234.pdf
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if filepath.exists():
        return str(filepath)

    r = requests.get(url, timeout=60) #pdf herunterladen
    if r.status_code == 200:
        with open(filepath, "wb") as f:
            f.write(r.content)
        print(f"PDF geladen: {filename}")
        return str(filepath)

    return None

# MODIF: fehlenden Vorgang direkt über seine DIP-ID laden und speichern
def get_or_create_vorgang_id(cursor, vorgang_dip_id):
    cursor.execute("""
        SELECT id FROM vorgaenge WHERE dip_id = ?
    """,
    (vorgang_dip_id,))

    result = cursor.fetchone()

    if result:
        return result[0]

    url = f"https://search.dip.bundestag.de/api/v1/vorgang/{vorgang_dip_id}"

    response = requests.get(
        url,
        params={"apikey": API_KEY, "format": "json"},
        timeout=30
    )
    response.raise_for_status()

    v = response.json()

    cursor.execute("""
        INSERT OR IGNORE INTO vorgaenge
        (dip_id, titel, vorgangstyp, datum_erstellt, datum_aktualisiert)
        VALUES (?, ?, ?, ?, ?)
    """,
    (
        v.get("id"),
        v.get("titel"),
        v.get("vorgangstyp"),
        v.get("datum"),
        v.get("aktualisiert")
    ))

    cursor.execute("""
        SELECT id FROM vorgaenge WHERE dip_id = ?
    """,
    (vorgang_dip_id,))

    result = cursor.fetchone()
    return result[0] if result else None

def run():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # MODIF: Anzahl wird für Drucksachen und Plenarprotokolle getrennt gezählt
    total_count = 0

    for base_url, doc_type_fixed, max_docs in BASE_URLS:
        print(f"\n=== Quelle: {doc_type_fixed} ===")

        # MODIF: bereits gespeicherte Dokumente dieses Typs mitzählen
        cursor.execute("SELECT COUNT(*) FROM documents WHERE doc_type = ?", (doc_type_fixed,))
        count = cursor.fetchone()[0]

        print(f"Bereits vorhanden: {count}/{max_docs} {doc_type_fixed}")

        # MODIF: Seiten solange durchsuchen, bis die Zielanzahl erreicht ist
        cursor_value = "*"

        while count < max_docs:
            docs, next_cursor= fetch_documents(base_url, cursor_value)
            print(f"Batch geladen: {len(docs)} Dokumente | aktuell gespeichert: {count}/{max_docs}") #zeigt, dass der Crawler weiterläuft

            if not docs:
                break

            for doc in docs:
                if count >= max_docs:
                    break

                dip_id = doc.get("id")
                titel = doc.get("titel") or "kein Titel"
                datum = doc.get("datum")
                source_org = doc.get("herausgeber")

                # Vorgang des Dokuments bestimmen
                vorgang_id = None
                vorgangsbezug = doc.get("vorgangsbezug")

                if isinstance(vorgangsbezug, list) and len(vorgangsbezug) > 0:
                    vorgang_dip_id = vorgangsbezug[0].get("id")

                    # MODIF: Vorgang verwenden oder automatisch aus DIP nachladen
                    vorgang_id = get_or_create_vorgang_id(cursor, vorgang_dip_id)

                # MODIF: Dokument nur verwenden, wenn der Vorgang bereits in SQLite existiert
                if vorgang_id is None:
                    continue

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

                # Dokument einfügen oder ignorieren, falls es bereits existiert
                cursor.execute("""
                    INSERT OR IGNORE INTO documents
                    (dip_id, vorgang_id, filename, filepath, titel, datum, doc_type, source_org, pdf_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (dip_id, vorgang_id, filename, filepath, titel, datum,
                 doc_type_fixed, source_org, pdf_url))

                # Nur wirklich neu eingefügte Dokumente zählen
                if cursor.rowcount > 0:
                    count += 1
                    total_count += 1

                # Falls das Dokument bereits existiert, werden seine Metadaten aktualisiert
                cursor.execute("""
                    UPDATE documents
                    SET vorgang_id = ?, titel = ?, datum = ?, doc_type = ?, source_org = ?, pdf_url = ?
                    WHERE filepath = ?
                """,
                (vorgang_id, titel, datum, doc_type_fixed,
                 source_org, pdf_url, filepath))

                # MODIF: Dokument sofort speichern, damit bei einem API-Fehler nichts verloren geht
                conn.commit()

                print(f"[{count}/{max_docs}] "
                    f"{doc_type_fixed}: {titel}"
                )

                # MODIF: nächste API-Seite laden
                if not next_cursor or next_cursor == cursor_value:
                       break
                cursor_value = next_cursor

        print(
            f"{doc_type_fixed}: "
            f"{count}/{max_docs} Dokumente gespeichert"
        )

    conn.commit()
    conn.close()

    print("\nCrawler fertig!")
    print(f"Gesamt: {total_count}/90 Dokumente")


if __name__ == "__main__":
    run()