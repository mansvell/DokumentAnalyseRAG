from typing import List
from pydantic import BaseModel, Field
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
import sqlite3

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
            default="llama3.2:3b" ,  # llama3.2:3b", gemma3:1b gemma3n:e2b
            description="Ollama-Modellname"
        )
        OLLAMA_BASE_URL: str = Field(
            default="http://host.docker.internal:11434",
            description="Ollama-Basis-URL aus dem Container"
        )
        TOP_K: int = Field(
            default=3,
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
            base_url=self.valves.OLLAMA_BASE_URL
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
        Erkläre stattdessen den Inhalt des Dokuments und sage klar,
        dass eine echte Entwicklung im Zeitverlauf anhand der vorhandenen Daten nicht erkennbar ist.
        """
        else:
            mode_instruction = """
        Wichtig:
        Zu diesem Vorgang liegen mehrere Dokumente vor.
        Beschreibe die Entwicklung chronologisch anhand der Dokumente.
        """

        prompt = f"""
        Du bist ein KI-Assistent für politische Dokumentenanalyse.
        Entwickelt von Mansvell Nkwanga
        Der Nutzer möchte einen politischen Vorgang im Zeitverlauf verstehen.
        
        {mode_instruction}
        
        Nutze nur die folgende chronologisch sortierte Liste von Dokumenten und ihren Inhalten.
        Beschreibe kurz, sachlich und klar:
        - wie der Vorgang begonnen hat,
        - welche wichtigen Entwicklungen erkennbar sind,
        - ob sich Forderungen, Positionen oder Entscheidungen verändert haben,
        - was der aktuelle Stand ist, soweit aus den Dokumenten erkennbar.
        
        Wenn die Informationen nicht ausreichen, sage das offen.
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

        prompt = f"""
            Klassifiziere die folgende Nutzerfrage in genau eine Kategorie.
        
            Kategorien:
            - SYSTEM_HELP: Frage über dich, deine Rolle, deine Funktionen oder Hilfe.
            - VORGANG: Nutzer möchte einen politischen Vorgang, Verlauf oder eine Entwicklung verfolgen oder wissen, wie sich ein Thema entwickelt hat.
            - DOCUMENT_QA: Nutzer stellt eine inhaltliche Frage zu politischen Dokumenten, Gesetzen oder Bundestag.
        
            Antworte nur mit einer Kategorie: SYSTEM_HELP, VORGANG oder DOCUMENT_QA.
        
            Frage:
            {user_message}
        """

        try:
            intent = self.llm.invoke(prompt).strip().upper()

            if "SYSTEM_HELP" in intent:
                return "SYSTEM_HELP"
            if "VORGANG" in intent:
                return "VORGANG"
            if "DOCUMENT_QA" in intent:
                return "DOCUMENT_QA"

        except Exception:
            pass

        return "DOCUMENT_QA"

    def pipe(self, user_message: str, model_id: str, messages: List[dict], body: dict):
        try:
            if self.embedding is None or self.db is None or self.llm is None:
                self._init_components()

            intent = self._classify_intent(user_message)
            if intent == "SYSTEM_HELP":
                return """
                    Ich bin ein KI-Assistent für politische Dokumentenanalyse.

                    Ich kann Ihnen helfen bei:
                    - Fragen zu politischen Dokumenten (Was wurde über Energiewirtschaftsgesetz gesagt?)
                    - Zusammenfassungen von Dokumenten (Fasse die wichtigsten Punkte dieses Dokuments zusammen)
                    - dem Verfolgen politischer Vorgänge im Zeitverlauf (Verfolge den Vorgang zum Gas- und Wasserstoff-Binnenmarktpaket)
                """

            if intent == "VORGANG":      #vorgg
                return self._handle_vorgang_request(user_message)

            results = self.db.similarity_search(
                user_message,
                k=self.valves.TOP_K
            )


            #Die Chunks werden nummeriert, damit das LLM diejenigen angeben kann, die es verwendet
            numbered_context_parts = []
            for i, r in enumerate(results, start=1):
                content = r.page_content if hasattr(r, "page_content") else str(r)
                numbered_context_parts.append(f"[Quelle {i}]\n{content}")


            context = "\n\n".join(numbered_context_parts)

            prompt = f"""
            Du bist ein KI-Assistent für politische Dokumentenanalyse.
        
            Beantworte die Frage nur auf Basis des bereitgestellten Kontexts.
            Wenn die Information im Kontext nicht enthalten ist, antworte genau:
            "Ich habe im bereitgestellten Kontext keine ausreichende Information gefunden."
            
            - Gib nach deiner Antwort in einer neuen Zeile genau dieses Format zurück:
            GENUTZTE_QUELLEN: [Nummern]
            - Beispiel: GENUTZTE_QUELLEN: 1 oder GENUTZTE_QUELLEN: 1,2
            - Nenne nur die Nummern der Quellen, die du wirklich für die Antwort benutzt hast.
            - Antworte kurz, präzise und auf Deutsch.
        
            Kontext:
            {context}

            Frage:
            {user_message}
        
            Antwort:
            """

            response = self.llm.invoke(prompt)

            #ich extrahiere die Verwendete Quellennummern aus der Antwort
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

                response = answer_text
            else:
                #Sollte das Modell das Format nicht einhalten, nur die erste Quelle nehmen
                used_indices = [1]

            sources = []
            seen_sources = set()

            for idx in used_indices:
                r = results[idx - 1]
                metadata = r.metadata if hasattr(r, "metadata") else {}

                titel = metadata.get("titel", "Ohne Titel")
                datum = metadata.get("datum", "kein Datum")
                doc_type = metadata.get("doc_type", "unbekannt")
                page_number = metadata.get("page_number", "unbekannt")
                pdf_url = metadata.get("pdf_url", "")

                unique_key = (titel, datum, page_number, pdf_url)
                if unique_key not in seen_sources:
                    seen_sources.add(unique_key)

                    source_text = (
                        f"Titel: {titel} | "
                        f"Datum: {datum} | "
                        f"Typ: {doc_type} | "
                        f"Seite: {page_number}"
                    )

                    if pdf_url:
                        source_text += f" | PDF: {pdf_url}"

                    sources.append(source_text)
            if sources:
                response += "\n\nQuellen:\n- " + "\n- ".join(sources)

            return response

        except Exception as e:
            return f"Fehler im Pipeline-Modell: {str(e)}"