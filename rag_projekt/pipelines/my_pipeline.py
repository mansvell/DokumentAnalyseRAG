from typing import List
from pydantic import BaseModel, Field
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
import sqlite3
import time

class Pipeline:
    class Valves(BaseModel):
        EMBEDDING_MODEL: str = Field(
            default="all-MiniLM-L6-v2",
            description="Embedding-Modell für die Vektorsuche"
        )
        VECTOR_DB_DIR: str = Field(
            default="/app/db/vector_store",
            description="Pfad zur Chroma-Vektordatenbank im Container"
        )
        LLM_MODEL: str = Field(
            default="gemma4:e2b" ,  # qwen3.5:0.8b llama3.2:3b, gemma4:e2b gemma3n:e2b
            description="Ollama-Modellname"
        )
        OLLAMA_BASE_URL: str = Field(
            default="http://host.docker.internal:11434",
            description="Ollama-Basis-URL aus dem Container"
        )
        TOP_K: int = Field(
            default=5,
            description="Anzahl der abgerufenen Chunks"
        )
        SQLITE_DB_PATH: str = Field(  #Vorgg
            default="/app/db/dbsqlite/think_ai.db",
            description="Pfad zur SQLite-Datenbank im Container"
        )

    def __init__(self):
        self.name = "Think AI"
        self.valves = self.Valves()
        self.embedding = None
        self.db = None
        self.llm = None

    def _init_components(self): ##Initialisiert Embedding, Chroma und LLM nur bei Bedarf
        self.embedding = HuggingFaceEmbeddings(
            model_name=self.valves.EMBEDDING_MODEL
        )

        self.db = Chroma(
            persist_directory=self.valves.VECTOR_DB_DIR,
            embedding_function=self.embedding
        )

        self.llm = OllamaLLM(
            model=self.valves.LLM_MODEL,
            base_url=self.valves.OLLAMA_BASE_URL,
        )
        self.vorgang_db = Chroma(
            persist_directory="/app/db/vector_store_vorgaenge",
            embedding_function=self.embedding
        )

    async def on_startup(self):
        print(f"on_startup: {__name__}")

    async def on_shutdown(self):
        print(f"on_shutdown: {__name__}")

    async def on_valves_updated(self):
        print(f"on_valves_updated: {__name__}")
        self.embedding = None
        self.db = None
        self.llm = None

    def pipelines(self) -> List[dict]:
        return [
            {
                "id": "politik-rag",
                "name": "Think AI",
            }
        ]

    def _is_vorgang_request (self, user_message: str) -> bool:
        #Prüft grob, ob der Nutzer einen Vorgang im Zeitverlauf verfolgen möchte
        text = user_message.lower()

        keywords = [  #  Vorgang aufdecken
            "vorgang",
            "verfolge",
            "verlauf",
            "verlaufen",
            "im zeitverlauf",
            "entwicklung",
            "im laufe der zeit",
            "timeline",
            "entwickelt",
            "verfolgung"
        ]
        return any(keyword in text for keyword in keywords)
            #return True
        #try:
            #results = self.vorgang_db.similarity_search(user_message, k=1)
            #if results:
             #   return True
        #except:
         #   pass
        #return False'''

    def _find_vorgang_semantic(self, user_message: str):
        #Suche nach den 3 besten Vorgängen via vector_db
        results = self.vorgang_db.similarity_search(user_message, k=3)

        if not results:
            return None

        best = results[0]  #beste Ergebnisse

        metadata = best.metadata

        return (     #Metadaten aufrufen
            metadata.get("vorgang_id"),
            metadata.get("dip_id"),
            metadata.get("titel"),
            metadata.get("vorgangstyp"),
            metadata.get("datum_erstellt"),
            metadata.get("datum_aktualisiert"),
        )

    def _get_documents_for_vorgang(self, vorgang_id: int):
        #Holt alle Dokumente, die mit einem Vorgang verbunden sind,und sortiert sie chronologisch nach Datum.
        conn = sqlite3.connect(self.valves.SQLITE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, titel, datum, doc_type, pdf_url
            FROM documents
            WHERE vorgang_id = ?
            ORDER BY datum ASC
        """, (vorgang_id,))

        results = cursor.fetchall()
        conn.close()
        return results

    def _get_chunks_for_document_ids(self, document_ids: List[int]): #holt alle Chunks zu einer Liste von Dokument-IDs
        if not document_ids:
            return []

        conn = sqlite3.connect(self.valves.SQLITE_DB_PATH)
        cursor = conn.cursor()

        placeholders = ",".join(["?"] * len(document_ids)) #?,?,? abhängig von der Länge der Liste von Doks

        cursor.execute(f"""
            SELECT document_id, chunk_index, content, page_number
            FROM chunks
            WHERE document_id IN ({placeholders})
            ORDER BY document_id ASC, chunk_index ASC
        """, document_ids)

        results = cursor.fetchall()
        conn.close()
        return results

    #Sucht die relevantesten Chunks für die Nutzerfrage aber nur innerhalb der Dokumente des gefundenen Vorgangs
    def _get_relevant_chunks_for_vorgang(self, user_message: str, document_ids: List[int], k: int = 15):
        if not document_ids:
            return []

        results = self.db.similarity_search(user_message, k=20) #20 tout Dok confondu

        filtered_results = []

        for r in results:
            metadata = r.metadata if hasattr(r, "metadata") else {}
            doc_id = metadata.get("document_id")

            if doc_id in document_ids: #Filterung , Behaltung der chunks von entsprechendem Vorgang
                filtered_results.append(r)

            if len(filtered_results) >= k: #man stopt wenn man schon 8 hat
                break

        return filtered_results

    #baut aus den Dokumenten + Chunks eine Vorgangs-Zusammenfassung
    def _handle_vorgang_request(self, user_message: str):
        vorgang= self._find_vorgang_semantic(user_message)

        if not vorgang :
            return "Ich konnte leider keinen passenden Vorgang in der Datenbank finden"

        vorgang_id,dip_id,titel, vorgangstyp,datum_erstellt, datum_aktualisiert = vorgang

        documents =self._get_documents_for_vorgang(vorgang_id)  #Zugehörige Dokumente laden

        if not documents:
            return f"Zum Vorgang '{titel}' wurden keine verknüpften Dokumente gefunden"
        print(f"2. {len(documents)} Dokumente geladen")

        if len(documents) == 1:
            analyse_mode = "single_document"
        else:
            analyse_mode = "timeline"

        document_ids  =[doc_id for doc_id, _, _, _, _ in documents]  #IDs der Dokumente sammeln [12,15]
        relevant_chunks = self._get_relevant_chunks_for_vorgang(user_message,document_ids, k=12) #Alle Chunks dieser Dokumente laden
        print(f"3. {len(relevant_chunks)} relevante Chunks gefunden")

        #Chunks pro Dok-id gruppieren [{"chunk_index": 0, "content": "...", "page_number": 1}, ...],
        chunks_by_doc = {}

        for r in relevant_chunks:
            metadata = r.metadata if hasattr(r, "metadata") else {}

            document_id = metadata.get("document_id")
            page_number = metadata.get("page_number")
            content = r.page_content if hasattr(r, "page_content") else ""

            if document_id is None:
                continue

            if document_id not in chunks_by_doc:
                chunks_by_doc[document_id] = []

            chunks_by_doc[document_id].append({
                "content": content,
                "page_number": page_number
            })

        timeline_parts = [] #enthält die an das LLM gesendeten Textblöcke
        sources = []

        #Für jedes Dokument einen kompakten Inhaltsblock bauen
        for doc_id, doc_titel, datum, doc_type, pdf_url in documents:
            doc_chunks = chunks_by_doc.get(doc_id, [])

            selected_chunks = doc_chunks[:5] #nur die 3 ersten besten Chunks pro Dokument, damit der Prompt nicht zu lang wird
            content_parts = []
            used_pages = set()

            for chunk in selected_chunks: #für jedes chunks pagenr und Inhalt lesen
                page_number = chunk["page_number"]
                text = chunk["content"]

                if page_number is not None:
                    used_pages.add(page_number)
                content_parts.append(text)

            combined_text = "\n\n".join(content_parts).strip() #Chunks zu einem kompakten Inhaltsblock verbinden

            if not combined_text:
                return "kein relevanter Inhalt für dieses Dokument gefunden"

            #combined_text = combined_text[:2500] #1200 auch 3 Chunks können lang sein. auf 2500 Zeichen begrenzen

            timeline_parts.append( #ein Block für jedes Dok erstellen
                f"""
                Dokument:
                - Datum: {datum or 'unbekannt'}
                - Typ: {doc_type or 'unbekannt'}
                - Titel: {doc_titel or 'Ohne Titel'}
                
                Relevanter Inhalt:
                {combined_text}
                """ )

            pages_text    = ", ".join(str(p) for p in sorted(used_pages)) if used_pages else "unbekannt"
            source_text = (
                f"Titel: {doc_titel or 'Ohne Titel'} | "
                f"Datum: {datum or 'kein Datum'} | "
                f"Typ: {doc_type or 'unbekannt'} | "
                f"Seiten: {pages_text}"
            )
            if pdf_url:
                source_text += f" | PDF: {pdf_url}"

            sources.append(source_text)

        timeline_context= "\n\n".join(timeline_parts) #chronologisch sortiert: bloc doc1, bloc doc2, ...

        if analyse_mode == "single_document":
            mode_instruction = """
        Wichtig:
        Zu diesem Vorgang liegt nur ein Dokument vor.
        Deshalb darfst du keine vollständige zeitliche Entwicklung behaupten.
        
        Beschreibe stattdessen:
        - den Inhalt des Dokuments
        - die wichtigsten Punkte
        - und weise klar darauf hin, dass keine zeitliche Entwicklung erkennbar ist.
                """
            structure_instruction= """
        Strukturiere deine Antwort wie folgt:
        1. Inhalt des Dokuments
        2. Wichtige Punkte
        3. Einschätzung 

        Wichtig:
        Es gibt keine zeitliche Entwicklung.
                    """
        else:
            mode_instruction = """
        Wichtig:
        Zu diesem Vorgang liegen mehrere Dokumente vor.
        Ordne die Informationen strikt chronologisch nach Datum.
        - Verwende NUR Informationen aus den Dokumenten.
        - Verwende ALLE bereitgestellten Dokumente.
        - Jedes Dokument muss mindestens einmal in der Antwort vorkommen.
        """
            structure_instruction = """
        Deine Antwort MUSS folgende Punkte enthalten:
        
        - Beginn: Wie und wann hat der Vorgang begonnen ?
           
        - Entwicklung: Beschreibe die weiteren Dokumente chronologisch Schritt für Schritt: Zuerst, Dann,Anschließend).
        
        - Veränderungen: Welche Inhalte, Auschlüsse oder Regelungen im Vorgang haben sich geändert ?
        
        - Aktueller Stand: Was ist der aktuelle Stand des Vorgangs basierend auf dem letzten Dokument ? 
        """

        prompt = f"""
        Du bist ein KI-Assistent für politische Dokumentenanalyse.
    
        Der Nutzer möchte einen politischen Vorgang im Zeitverlauf verstehen.
        
        {mode_instruction}
        
        Nutze nur die folgende chronologisch sortierte Liste von Dokumenten und ihren Inhalten.
        
        {structure_instruction}
        
        Wenn die Informationen nicht ausreichen, sage das klar.
        Antworte auf Deutsch.
        
        Vorgang:
        Titel: {titel}
        Typ: {vorgangstyp or 'unbekannt'}
        Erstellt: {datum_erstellt or 'unbekannt'}
        Aktualisiert: {datum_aktualisiert or 'unbekannt'}
        
        Chronologische Dokumente:
        {timeline_context}
        
        Frage:
        {user_message}
        
        Antwort:
        """
        print(" Prompt wird an LLM geschickt")
        response = self.llm.invoke(prompt)
        print(" LLM Antwort erhalten")

        unique_sources = []  #Doppelte Quellen entfernen
        seen = set()

        for source in sources:
            if source not in seen:
                seen.add(source)
                unique_sources.append(source)
        if unique_sources:
            response += "\n\nQuellen:\n- " + "\n- ".join(unique_sources)
        return response


    def _classify_intent(self, user_message: str) -> str: #Klassifiziert die Nutzerfrage, bevor Retrieval ausgeführt wird
        classify_start = time.perf_counter()

        prompt = f"""
        Klassifiziere die folgende Nutzerfrage in genau eine Kategorie.

        Kategorien:

        SYSTEM_HELP:
        Frage über dich, deine Rolle oder deine Funktionen.
        
        DOCUMENT_QA:
        Alle normalen inhaltlichen Fragen zu Dokumenten, Parteien, Positionen, Bundestag, Gesetzen oder Themen.
        Auch Fragen wie:
        - Wie positioniert sich die SPD ...?
        - Was sagt die Bundesregierung zu ...?
        - Welche Forderungen stellt die Fraktion ...?

        VORGANG:
        Nur wenn der Nutzer ausdrücklich einen Verlauf, eine Entwicklung oder einen politischen Vorgang im Zeitverlauf verstehen möchte.
        Beispiele:
        - Verfolge den Vorgang ...
        - Wie hat sich das Thema entwickelt?
        - Zeige den Verlauf dieses Vorgangs
        - Was ist der aktuelle Stand nach mehreren Dokumenten?
        
        ZUSAMMENFASSUNG:
        Der Nutzer möchte ein Dokument zusammenfassen.
        Beispiele:
        - Fasse dieses Dokument zusammen
        - Gib mir eine Zusammenfassung

        Wichtig:
        Wenn keine zeitliche Entwicklung ausdrücklich verlangt wird, wähle DOCUMENT_QA.

        Antworte nur mit:
        SYSTEM_HELP, DOCUMENT_QA, VORGANG oder ZUSAMMENFASSUNG.

        Frage:
        {user_message}
        """

        try:
            intent = self.llm.invoke(prompt).strip().upper()
            print("INTENT LLM TIME:", round(time.perf_counter() - classify_start, 2), "s")

            if "SYSTEM_HELP" in intent:
                return "SYSTEM_HELP"
            if "VORGANG" in intent:
                return "VORGANG"
            if "DOCUMENT_QA" in intent:
                return "DOCUMENT_QA"
            if "ZUSAMMENFASSUNG" in intent:
                return "ZUSAMMENFASSUNG"

        except Exception:
            pass

        print("INTENT LLM TIME:", round(time.perf_counter() - classify_start, 2), "s")
        return "DOCUMENT_QA"


    def pipe(self, user_message: str, model_id: str, messages: List[dict], body: dict):
        try:
            total_start = time.perf_counter()
            if self.embedding is None or self.db is None or self.llm is None:
                self._init_components()

            if user_message.strip().startswith("### Task:"):   #Bloc usermessage von OPENWBUI
                return ""

            intent_start = time.perf_counter()
            intent = self._classify_intent(user_message)
            print("INTENT TIME:", round(time.perf_counter() - intent_start, 2), "s")
            print("USER MESSAGE:", user_message)
            print("CLASSIFIED INTENT:", intent)

            if intent == "SYSTEM_HELP":     #Hilfe für Nutzer
                return """
                    Ich bin ein KI-Assistent für politische Dokumentenanalyse.

                    Ich kann Ihnen helfen bei:
                    - Fragen zu politischen Dokumenten (Was wurde über Energiewirtschaftsgesetz gesagt?)
                    - Zusammenfassungen von Dokumenten (Fasse die wichtigsten Punkte dieses Dokuments zusammen)
                    - dem Verfolgen politischer Vorgänge im Zeitverlauf (Verfolge den Vorgang zum Gas- und Wasserstoff-Binnenmarktpaket)
                """

            if intent == "VORGANG":      #vorgg
                return self._handle_vorgang_request(user_message)

            if intent =="ZUSAMMENFASSUNG":
                kk= 7
            else:
                kk = self.valves.TOP_K

            #results = self.db.similarity_search(user_message, k=kk)
            retrieval_start = time.perf_counter()
            results = self.db.max_marginal_relevance_search(
                user_message,
                k=kk,
                fetch_k=40,
                lambda_mult=0.9
            )
            print("RETRIEVAL TIME:", round(time.perf_counter() - retrieval_start, 2), "s")

            print("===== RETRIEVAL DEBUG =====")
            for i, r in enumerate(results, start=1):
                metadata = r.metadata if hasattr(r, "metadata") else {}
                content = r.page_content if hasattr(r, "page_content") else ""

                print(f"\n--- RESULT {i} ---")
                print("Titel:", metadata.get("titel"))
                print("Seite:", metadata.get("page_number"))
                print(content[:800])

            #Die Chunks werden nummeriert, damit das LLM diejenigen angeben kann, die es verwendet
            context_start = time.perf_counter()
            numbered_context_parts = []
            for i, r in enumerate(results, start=1):
                #content = r.page_content if hasattr(r, "page_content") else str(r)
                #numbered_context_parts.append(f"[Quelle {i}]\n{content}")
                content = r.page_content if hasattr(r, "page_content") else str(r)
                metadata = r.metadata if hasattr(r, "metadata") else {}

                titel = metadata.get("titel", "Ohne Titel")
                datum = metadata.get("datum", "kein Datum")
                doc_type = metadata.get("doc_type", "unbekannt")
                page_number = metadata.get("page_number", "unbekannt")
                pdf_url = metadata.get("pdf_url", "")

                # So kann das LLM besser erkennen, welche Quelle zu welchem Inhalt gehört.
                numbered_context_parts.append(f"""
                [Quelle {i}]
                Titel: {titel}
                Datum: {datum}
                Typ: {doc_type}
                Seite: {page_number}
                PDF: {pdf_url}

                Inhalt:
                {content}
                """)

            context = "\n\n".join(numbered_context_parts)
            print("CONTEXT BUILD TIME:", round(time.perf_counter() - context_start, 2), "s")

            if intent == "ZUSAMMENFASSUNG":
                prompt = f"""
            Du bist ein KI-Assistent für politische Dokumentenanalyse.

            Deine Aufgabe ist es, das relevante Dokument bzw. die relevanten Dokumentstellen kurz und klar zusammenzufassen.

            Strukturiere deine Antwort wie folgt:

            1. Thema des Dokuments
            2. Wichtige Inhalte
            3. Ziel oder Zweck des Dokuments

            Wichtig:
            - Verwende nur die Informationen aus dem Kontext.
            - Erfinde nichts.
            - Schreibe klar und verständlich.
            - Gib am Ende genau dieses Format zurück:
            GENUTZTE_QUELLEN: [Nummern]
            - Beispiel: GENUTZTE_QUELLEN: 1,3
            - Nenne nur Quellen, die du wirklich verwendet hast.

            Kontext:
            {context}

            Anfrage:
            {user_message}

            Antwort:
            """
            else :
                prompt = f"""
                Du bist ein KI-Assistent für politische Dokumentenanalyse.

                AUFGABE:
                Beantworte die Frage ausschließlich auf Basis des bereitgestellten Kontexts.

                WICHTIGE REGELN:
                - Verwende keine Informationen außerhalb des Kontexts.
                - Wenn der Kontext die Frage nicht direkt beantwortet, antworte genau:
                "Ich habe im bereitgestellten Kontext keine ausreichende Information gefunden."
                - Verwende nur Quellen, deren Inhalt die Antwort direkt belegt.
                - Achte besonders auf Titel, Seite und Inhalt der Quelle.
                - Wenn mehrere Quellen thematisch ähnlich sind, wähle nur die wirklich passende Quelle.
                - Antworte kurz, präzise und auf Deutsch.
                - Du MUSST immer eine Antwort UND GENUTZTE_QUELLEN zurückgeben.
                
                AUSGABEFORMAT:
                
                ANTWORT:
                [Antwort steht hier]
                
                GENUTZTE_QUELLEN: [Nummern]
                Beispiel:
                GENUTZTE_QUELLEN: 2,4 

                KONTEXT:
                {context}

                FRAGE:
                {user_message}

                ANTWORT:
                """
            llm_start = time.perf_counter()
            response = self.llm.invoke(prompt)
            print("LLM TIME:", round(time.perf_counter() - llm_start, 2), "s")
            print("===== RAW LLM RESPONSE =====")
            print(response)

            #ich extrahiere die Verwendeten Quellennummern aus der Antwort
            source_start = time.perf_counter()
            used_indices = []

            marker = "GENUTZTE_QUELLEN:"
            if marker in response:
                parts = response.split(marker)
                answer_text = parts[0].strip() #parts[0] = "Die E-Auto-Förderung beträgt bis zu 6000 Euro.\n" strip entferne Zeilenumbruch\n
                raw_sources = parts[1].strip() #parts[1] = " 2,3\n"

                #"1,2" -> [1, 2]
                for part in raw_sources.split(","):
                    part = part.strip()
                    if part.isdigit():
                        idx = int(part)
                        if 1 <= idx <= len(results):
                            used_indices.append(idx)

                response = answer_text.replace("ANTWORT:", "").strip()

                if not response: #Falls das Modell keine Antwort erzeugt:
                    response = "Die Information wurde im Kontext gefunden, aber das Modell konnte keine klare Antwort formulieren."

                if "keine ausreichende information" in response.lower():
                    return response
            else:
                #Sollte das Modell das Format nicht einhalten, nichts anzeigen
                used_indices = []

            if "keine ausreichende information" in response.lower(): #falls das LLM nicht den Marker schreibt
                return response

            if not used_indices:
                return response

            grouped_sources = {}

            for idx in used_indices:
                r = results[idx - 1]
                metadata = r.metadata if hasattr(r, "metadata") else {}

                titel = metadata.get("titel", "Ohne Titel")
                datum = metadata.get("datum", "kein Datum")
                doc_type = metadata.get("doc_type", "unbekannt")
                page_number = metadata.get("page_number", "unbekannt")
                pdf_url = metadata.get("pdf_url", "")

                unique_key = (titel, datum, doc_type, pdf_url) #pro Dok grupp

                if unique_key not in grouped_sources:
                        grouped_sources[unique_key] = set()
                    #seen_sources.add(unique_key)
                if page_number is not None:
                    grouped_sources[unique_key].add(str(page_number))
            sources = []

            for (titel, datum, doc_type, pdf_url), pages in grouped_sources.items():
                pages_sorted = sorted(pages, key=lambda x: int(x) if x.isdigit() else x)

                pages_text = ", ".join(pages_sorted) if pages else "unbekannt" #Seite zusamlgen

                source_text = (
                        f"Titel: {titel} | "
                        f"Datum: {datum} | "
                        f"Typ: {doc_type} | "
                        f"Seite: {pages_text}"
                    )

                if pdf_url:
                        source_text += f" | PDF: {pdf_url}"

                sources.append(source_text)
            if sources:
                response += "\n\nQuellen:\n- " + "\n- ".join(sources)

            print("SOURCE PROCESSING TIME:", round(time.perf_counter() - source_start, 2), "s")
            print("TOTAL TIME:", round(time.perf_counter() - total_start, 2), "s")
            return response

        except Exception as e:
            return f"Fehler im Pipeline-Modell: {str(e)}"