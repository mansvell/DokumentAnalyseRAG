import requests
import sqlite3
from pathlib import Path

API_KEY = "OSOegLs.PR2lwJ1dwCeje9vTj7FPOt3hvpYKtwKkhw"

BASE_URL = "https://search.dip.bundestag.de/api/v1/vorgang"

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "vorgang"
DB_PATH = BASE_DIR / "db" / "dbsqlite" / "think_ai.db"


def fetch_vorgaenge(): #Vorgänge aufrufen
    params = {
        "apikey": API_KEY,
        "format": "json",
        "rows": 20
    }

    response = requests.get(BASE_URL, params=params) #schickt Getanfrage an API von DIP - 200
    response.raise_for_status()
    data = response.json()

    return data.get("documents", [])


def run():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()  #Erstellung von Cursor,um Anfragen auszuführen

    vorgaenge = fetch_vorgaenge()

    for v in vorgaenge: #Extrahiere die Felder jedes Vorgangs
        dip_id = v.get("id")
        titel = v.get("titel")
        vorgangstyp = v.get("vorgangstyp")
        datum_erstellt = v.get("datum")
        datum_aktualisiert = v.get("aktualisiert")

        if not dip_id:
            continue

        cursor.execute("""
            INSERT OR IGNORE INTO vorgaenge
            (dip_id, titel, vorgangstyp, datum_erstellt, datum_aktualisiert)
            VALUES (?, ?, ?, ?, ?)
        """, (
            dip_id,
            titel,
            vorgangstyp,
            datum_erstellt,
            datum_aktualisiert
        ))

        cursor.execute("""
            UPDATE vorgaenge
            SET titel = ?,
                vorgangstyp = ?,
                datum_erstellt = ?,
                datum_aktualisiert = ?
            WHERE dip_id = ?
        """, (
            titel,
            vorgangstyp,
            datum_erstellt,
            datum_aktualisiert,
            dip_id
        ))

        print(f"Vorgang gespeichert: {titel}")

    conn.commit()    #Änderung speichern - Verbindung schließen
    conn.close()


if __name__ == "__main__":
    run()