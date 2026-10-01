import requests
import sqlite3
from pathlib import Path
import os

API_KEY = os.getenv("DIP_API_KEY")

BASE_URL = "https://search.dip.bundestag.de/api/v1/vorgang"

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "vorgang"
DB_PATH = BASE_DIR / "db" / "dbsqlite" / "think_ai.db"
MAX_VORGAENGE = 500

def fetch_vorgaenge(cursor="*"): #Vorgänge aufrufen
    params = {
        "apikey": API_KEY,
        "format": "json",
        "rows": 20,
        "cursor": cursor
    }

    response = requests.get(BASE_URL, params=params,timeout=30) #schickt Getanfrage an API von DIP - 200
    response.raise_for_status()
    data = response.json()

    return data.get("documents", []), data.get("cursor")


def run():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()  #Erstellung von Cursor,um Anfragen auszuführen
    cursor_value = "*"
    count=0

    while count < MAX_VORGAENGE:  # 2 x 20rows = 40Vorgänge maximum
        vorgaenge, next_cursor = fetch_vorgaenge(cursor_value)

        if not vorgaenge:
            break

        for v in vorgaenge: #Extrahiere die Felder jedes Vorgangs

            if count >= MAX_VORGAENGE:
                break

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

            if cursor.rowcount > 0:
                count += 1

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
        if not next_cursor or next_cursor == cursor_value:
            break
        cursor_value = next_cursor


    conn.commit()    #Änderung speichern - Verbindung schließen
    conn.close()
    print(f"\nCrawler fertig: {count} Vorgänge gespeichert.")

if __name__ == "__main__":
    run()