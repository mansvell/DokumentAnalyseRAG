import requests
import sqlite3
from pathlib import Path
import os


API_KEY = os.getenv("DIP_API_KEY")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "raw"
DB_PATH = BASE_DIR / "db" / "dbsqlite" / "think_ai.db"

# Ziel:
# - mindestens 10 Vorgänge mit >= 2 Dokumenten
# - davon 2 Vorgänge mit möglichst 4 Dokumenten
TARGET_MULTI_VORGAENGE = 10
TARGET_RICH_VORGAENGE = 2
TARGET_DOCS_PER_RICH = 4


BASE_URLS = [
    ("https://search.dip.bundestag.de/api/v1/drucksache", "drucksache"),
    ("https://search.dip.bundestag.de/api/v1/plenarprotokoll", "plenarprotokoll")
]


def count_multi_vorgaenge(cursor):
    cursor.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT vorgang_id
            FROM documents
            WHERE vorgang_id IS NOT NULL
            GROUP BY vorgang_id
            HAVING COUNT(*) >= 2
        )
    """)

    return cursor.fetchone()[0]


def count_rich_vorgaenge(cursor):
    cursor.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT vorgang_id
            FROM documents
            WHERE vorgang_id IS NOT NULL
            GROUP BY vorgang_id
            HAVING COUNT(*) >= 3
        )
    """)

    return cursor.fetchone()[0]


def get_document_count(cursor, vorgang_id):
    cursor.execute("""
        SELECT COUNT(*)
        FROM documents
        WHERE vorgang_id = ?
    """,
    (vorgang_id,))

    return cursor.fetchone()[0]


def get_vorgang_id(cursor, vorgang_dip_id):
    cursor.execute("""
        SELECT id
        FROM vorgaenge
        WHERE dip_id = ?
    """,
    (vorgang_dip_id,))

    result = cursor.fetchone()

    return result[0] if result else None


def document_exists(cursor, dip_id):
    cursor.execute("""
        SELECT id
        FROM documents
        WHERE dip_id = ?
    """,
    (dip_id,))

    return cursor.fetchone() is not None


def find_replacement_document(cursor, doc_type, target_vorgang_id):
    """
    Sucht ein Dokument desselben Typs, dessen Vorgang nur dieses
    eine Dokument besitzt.

    Dadurch bleiben 60 Drucksachen und 30 Plenarprotokolle erhalten.
    """

    cursor.execute("""
        SELECT d.id, d.filepath, d.vorgang_id
        FROM documents d
        WHERE d.doc_type = ?
          AND d.vorgang_id != ?
          AND (
              SELECT COUNT(*)
              FROM documents d2
              WHERE d2.vorgang_id = d.vorgang_id
          ) = 1
        LIMIT 1
    """,
    (doc_type, target_vorgang_id))

    return cursor.fetchone()


def download_pdf(url, filename):
    filepath = DATA_DIR / filename
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if filepath.exists():
        return str(filepath)

    response = requests.get(url, timeout=60)
    response.raise_for_status()

    with open(filepath, "wb") as f:
        f.write(response.content)

    print(f"PDF geladen: {filename}")

    return str(filepath)


def fetch_documents(base_url, cursor_value="*"):
    params = {
        "apikey": API_KEY,
        "format": "json",
        "rows": 100,
        "cursor": cursor_value
    }

    response = requests.get(
        base_url,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    return data.get("documents", []), data.get("cursor")


def replace_singleton_with_document(
        conn,
        cursor,
        doc,
        doc_type,
        vorgang_id
):
    """
    Fügt ein neues Dokument zu einem ausgewählten Vorgang hinzu und
    entfernt dafür ein Singleton-Dokument desselben Typs.

    Gesamtzahl der Dokumente bleibt dadurch unverändert.
    """

    dip_id = doc.get("id")

    fundstelle = doc.get("fundstelle")

    if not isinstance(fundstelle, dict):
        return False

    pdf_url = fundstelle.get("pdf_url")

    if not pdf_url:
        return False

    replacement = find_replacement_document(
        cursor,
        doc_type,
        vorgang_id
    )

    if not replacement:
        return False

    replacement_id, replacement_filepath, _ = replacement

    filename = pdf_url.split("/")[-1]

    try:
        filepath = download_pdf(
            pdf_url,
            filename
        )
    except Exception as e:
        print(f"Download fehlgeschlagen: {e}")
        return False

    titel = doc.get("titel") or "kein Titel"
    datum = doc.get("datum")
    source_org = doc.get("herausgeber")

    cursor.execute("""
        INSERT INTO documents
        (
            dip_id,
            vorgang_id,
            filename,
            filepath,
            titel,
            datum,
            doc_type,
            source_org,
            pdf_url
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        dip_id,
        vorgang_id,
        filename,
        filepath,
        titel,
        datum,
        doc_type,
        source_org,
        pdf_url
    ))

    # Falls bereits Chunks vorhanden sein sollten
    cursor.execute("""
        DELETE FROM chunks
        WHERE document_id = ?
    """,
    (replacement_id,))

    cursor.execute("""
        DELETE FROM documents
        WHERE id = ?
    """,
    (replacement_id,))

    # Direkt speichern
    conn.commit()

    old_file = Path(replacement_filepath)

    if old_file.exists():
        try:
            old_file.unlink()
        except OSError:
            print(
                f"Altes PDF konnte nicht gelöscht werden: "
                f"{old_file}"
            )

    print(f"Neues Dokument: {titel}")

    return True


# ============================================================
# PHASE 1
# 3/10 -> 10/10 Vorgänge mit mindestens zwei Dokumenten
# ============================================================

def enrich_to_ten_multi(conn, cursor):
    current_multi = count_multi_vorgaenge(cursor)

    print("\n==========================================")
    print("PHASE 1: Multi-Dokument-Vorgänge erzeugen")
    print("==========================================")

    print(
        f"Aktuell: "
        f"{current_multi}/{TARGET_MULTI_VORGAENGE}"
    )

    if current_multi >= TARGET_MULTI_VORGAENGE:
        print("Phase 1 bereits abgeschlossen.")
        return

    for base_url, doc_type in BASE_URLS:

        if current_multi >= TARGET_MULTI_VORGAENGE:
            break

        print(f"\n=== Suche in {doc_type} ===")

        cursor_value = "*"

        while current_multi < TARGET_MULTI_VORGAENGE:

            docs, next_cursor = fetch_documents(
                base_url,
                cursor_value
            )

            print(
                f"Batch geladen: {len(docs)} Dokumente | "
                f"Multi-Vorgänge: "
                f"{current_multi}/{TARGET_MULTI_VORGAENGE}"
            )

            if not docs:
                break

            for doc in docs:

                if current_multi >= TARGET_MULTI_VORGAENGE:
                    break

                dip_id = doc.get("id")

                if not dip_id:
                    continue

                if document_exists(cursor, dip_id):
                    continue

                vorgangsbezug = doc.get("vorgangsbezug")

                if (
                    not isinstance(vorgangsbezug, list)
                    or len(vorgangsbezug) == 0
                ):
                    continue

                vorgang_dip_id = vorgangsbezug[0].get("id")

                if not vorgang_dip_id:
                    continue

                vorgang_id = get_vorgang_id(
                    cursor,
                    vorgang_dip_id
                )

                if vorgang_id is None:
                    continue

                # PHASE 1:
                # Nur Vorgänge mit genau einem Dokument
                if get_document_count(cursor, vorgang_id) != 1:
                    continue

                success = replace_singleton_with_document(
                    conn,
                    cursor,
                    doc,
                    doc_type,
                    vorgang_id
                )

                if not success:
                    continue

                current_multi = count_multi_vorgaenge(cursor)

                print(
                    f"Vorgang-ID: {vorgang_id} | "
                    f"Dokumente: "
                    f"{get_document_count(cursor, vorgang_id)} | "
                    f"Stand: "
                    f"{current_multi}/{TARGET_MULTI_VORGAENGE}"
                )

            if (
                not next_cursor
                or next_cursor == cursor_value
            ):
                break

            cursor_value = next_cursor


# ============================================================
# PHASE 2
# Zwei Vorgänge von >=2 auf möglichst 4 Dokumente erweitern
# ============================================================

def enrich_to_three_or_four(conn, cursor):
    print("\n==========================================")
    print("PHASE 2: Vorgänge auf 3–4 Dokumente erweitern")
    print("==========================================")

    # Bereits vorhandene Vorgänge mit >=3 Dokumenten bevorzugen
    cursor.execute("""
        SELECT vorgang_id
        FROM documents
        WHERE vorgang_id IS NOT NULL
        GROUP BY vorgang_id
        HAVING COUNT(*) >= 3
        ORDER BY COUNT(*) DESC
        LIMIT ?
    """,
    (TARGET_RICH_VORGAENGE,))

    selected_targets = {
        row[0]
        for row in cursor.fetchall()
    }

    # Prüfen, ob Ziel bereits vollständig erreicht wurde
    if len(selected_targets) >= TARGET_RICH_VORGAENGE:

        finished = all(
            get_document_count(cursor, vorgang_id)
            >= TARGET_DOCS_PER_RICH
            for vorgang_id in selected_targets
        )

        if finished:
            print(
                "Phase 2 bereits abgeschlossen: "
                "2 Vorgänge besitzen jeweils mindestens "
                f"{TARGET_DOCS_PER_RICH} Dokumente."
            )
            return

    for base_url, doc_type in BASE_URLS:

        cursor_value = "*"

        while True:

            docs, next_cursor = fetch_documents(
                base_url,
                cursor_value
            )

            print(
                f"Batch geladen: {len(docs)} Dokumente | "
                f"Vorgänge >=3 Docs: "
                f"{count_rich_vorgaenge(cursor)}/"
                f"{TARGET_RICH_VORGAENGE}"
            )

            if not docs:
                break

            for doc in docs:

                dip_id = doc.get("id")

                if not dip_id:
                    continue

                if document_exists(cursor, dip_id):
                    continue

                vorgangsbezug = doc.get("vorgangsbezug")

                if (
                    not isinstance(vorgangsbezug, list)
                    or not vorgangsbezug
                ):
                    continue

                vorgang_dip_id = vorgangsbezug[0].get("id")

                if not vorgang_dip_id:
                    continue

                vorgang_id = get_vorgang_id(
                    cursor,
                    vorgang_dip_id
                )

                if vorgang_id is None:
                    continue

                document_count = get_document_count(
                    cursor,
                    vorgang_id
                )

                # Nur bestehende Multi-Dokument-Vorgänge
                if document_count < 2:
                    continue

                # Maximal 4 Dokumente
                if document_count >= TARGET_DOCS_PER_RICH:
                    continue

                # Sobald zwei Ziel-Vorgänge feststehen,
                # werden nur noch diese beiden erweitert
                if (
                    vorgang_id not in selected_targets
                    and
                    len(selected_targets)
                    >= TARGET_RICH_VORGAENGE
                ):
                    continue

                success = replace_singleton_with_document(
                    conn,
                    cursor,
                    doc,
                    doc_type,
                    vorgang_id
                )

                if not success:
                    continue

                selected_targets.add(vorgang_id)

                new_count = get_document_count(
                    cursor,
                    vorgang_id
                )

                print(
                    f"Vorgang-ID: {vorgang_id} | "
                    f"Dokumente: {new_count}"
                )

                # Sind zwei Ziel-Vorgänge auf 4 Dokumenten?
                if len(selected_targets) >= TARGET_RICH_VORGAENGE:

                    finished = all(
                        get_document_count(cursor, target_id)
                        >= TARGET_DOCS_PER_RICH
                        for target_id in selected_targets
                    )

                    if finished:
                        return

            if (
                not next_cursor
                or next_cursor == cursor_value
            ):
                break

            cursor_value = next_cursor


def print_final_status(cursor):
    print("\n==============================")
    print("FINALER DOKUMENTBESTAND")
    print("==============================")

    cursor.execute("""
        SELECT doc_type, COUNT(*)
        FROM documents
        GROUP BY doc_type
    """)

    for doc_type, count in cursor.fetchall():
        print(f"{doc_type}: {count}")

    print(
        f"Multi-Dokument-Vorgänge >=2: "
        f"{count_multi_vorgaenge(cursor)}"
    )

    print(
        f"Multi-Dokument-Vorgänge >=3: "
        f"{count_rich_vorgaenge(cursor)}"
    )

    print("\nVerteilung:")

    cursor.execute("""
        SELECT vorgang_id, COUNT(*) AS anzahl
        FROM documents
        WHERE vorgang_id IS NOT NULL
        GROUP BY vorgang_id
        HAVING COUNT(*) >= 2
        ORDER BY anzahl DESC
    """)

    for vorgang_id, anzahl in cursor.fetchall():
        print(
            f"Vorgang {vorgang_id}: "
            f"{anzahl} Dokumente"
        )


def run():
    if not API_KEY:
        raise RuntimeError(
            "DIP_API_KEY wurde nicht gefunden."
        )

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # PHASE 1:
    # z.B. 3 Multi-Vorgänge -> 10 Multi-Vorgänge
    enrich_to_ten_multi(
        conn,
        cursor
    )

    # Phase 2 nur starten, wenn Phase 1 erfolgreich war
    if count_multi_vorgaenge(cursor) >= TARGET_MULTI_VORGAENGE:

        # PHASE 2:
        # 2 der Multi-Vorgänge auf möglichst 4 Dokumente erweitern
        enrich_to_three_or_four(
            conn,
            cursor
        )

    else:
        print(
            "\nPhase 2 wurde nicht gestartet, "
            "da noch keine 10 Multi-Dokument-Vorgänge "
            "vorhanden sind."
        )

    print_final_status(cursor)

    # Finaler Commit bleibt ebenfalls erhalten
    conn.commit()
    conn.close()


if __name__ == "__main__":
    run()