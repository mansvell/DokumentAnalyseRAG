from typing import List,  Optional
from pydantic import BaseModel, Field
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
import sqlite3
import time
import csv # Evaluationsergebnisse in einer Csv-Datei schreiben
import os

class E5Embeddings(HuggingFaceEmbeddings):
    def embed_documents(self, texts):
        texts = [f"passage: {text}" for text in texts]
        return super().embed_documents(texts)
    def embed_query(self, text):
        return super().embed_query(f"query: {text}")

class Pipeline:
    class Valves(BaseModel):
        EMBEDDING_MODEL: str = Field(
            default="intfloat/multilingual-e5-base", #all-MiniLM-L6-v2",
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
            default=4,
            description="Anzahl der abgerufenen Chunks in Document_QA"
        )
        SQLITE_DB_PATH: str = Field(  #Vorgg
            default="/app/db/dbsqlite/think_ai.db",
            description="Pfad zur SQLite-Datenbank im Container"
        )

        DOCUMENT_QA_RETRIEVAL: str = Field(
            default="similarity", #1-similarity, 2-mmr,3-sore,4-hybrid
            description="Retrieval für Dokumentfragen: similarity, score, mmr oder hybrid"
        )
        VORGANG_CHUNK_RETRIEVAL: str = Field(
            default="mmr_filtered",
            description="Chunk-Retrieval für Vorgänge: similarity_filtered oder mmr_filtered"
        )

        DOCUMENT_QA_SCORE_THRESHOLD: Optional[float] = Field(
            default=10,
            description="Distanzschwelle für score-basierte Similarity Search in Doc_QA"
        )

        EVALUATION_ENABLED: bool = Field( #aktiviert oder deaktiviert die Speicherung der Evaluationsergebnisse (WARM-UP)
            default=True,
            description="Evaluationsergebnisse in CSV speichern"
        )

        EVALUATION_QUESTION_ID: str = Field( #aktuell getestete Evaluationsfrage(DQ01 oder V01)
            default="DQ03",
            description="ID der aktuellen Evaluationsfrage"
        )

        EVALUATION_CSV_PATH: str = Field(  #speicherort Retrieval-Ergebnissen
            default="/app/evaluation/retrieval_results.csv",
            description="Pfad zur CSV-Datei für die Retrieval-Evaluation"
        )

    def __init__(self):
        self.name = "Think AI"
        self.valves = self.Valves()
        self.embedding = None
        self.db = None
        self.llm = None

    def _init_components(self): ##Initialisiert Embedding, Chroma und LLM nur bei Bedarf
        self.embedding = E5Embeddings(
            model_name=self.valves.EMBEDDING_MODEL,
            encode_kwargs={"normalize_embeddings": True}
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

    # MODIF: Speichert genau eine Retrieval-Zeile in der Evaluations-CSV
    def _append_evaluation_row(self, question_id, scenario, strategy, run, retrieval_time, rank, chunk_id,
                               document_id, page_number, vorgang_id=""):

        path = self.valves.EVALUATION_CSV_PATH

        # Erstellt den Zielordner automatisch, falls er noch nicht existiert
        os.makedirs(os.path.dirname(path), exist_ok=True)

        file_exists = os.path.exists(path)

        fieldnames = [
            "question_id",
            "scenario",
            "strategy",
            "run",
            "retrieval_time_s",
            "rank",
            "chunk_id",
            "document_id",
            "page_number",
            "vorgang_id"
        ]

        # MODIF: Öffnet die CSV im Append-Modus, damit bestehende Ergebnisse erhalten bleiben
        with open(path, "a", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames
            )

            # MODIF: Schreibt die Spaltennamen nur beim ersten Erstellen der Datei
            if not file_exists:
                writer.writeheader()

            writer.writerow({
                "question_id": question_id,
                "scenario": scenario,
                "strategy": strategy,
                "run": run,
                "retrieval_time_s": round(retrieval_time, 6),
                "rank": rank,
                "chunk_id": chunk_id,
                "document_id": document_id,
                "page_number": page_number,
                "vorgang_id": vorgang_id
            })

    # bestimmt automatisch die nächste Run-Nummer für Frage, Szenario und Strategie
    def _get_next_evaluation_run(self, question_id, scenario, strategy):

        path = self.valves.EVALUATION_CSV_PATH

        # Wenn noch keine CSV existiert, beginnt die erste Messung mit Run 1
        if not os.path.exists(path):
            return 1

        max_run = 0

        # ucht den höchsten bereits gespeicherten Run derselben Kombination
        with open(path, "r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            for row in reader:
                if (
                        row.get("question_id") == question_id
                        and row.get("scenario") == scenario
                        and row.get("strategy") == strategy
                ):
                    try:
                        max_run = max(
                            max_run,
                            int(row.get("run", 0))
                        )
                    except ValueError:
                        continue

        # der nächste Durchlauf erhält die folgende Run-Nummer
        return max_run + 1


    def _find_vorgang_semantic(self, user_message: str):
        #Suche nach den 3 besten Vorgängen via vector_db
        results = self.vorgang_db.similarity_search_with_score(user_message, k=3)

        if not results:
            return None

        best_vorgang, best_score= results[0]  #beste Ergebnisse
        second_score =results[1][1] if len( results) > 1 else None

        print("===== VORGANG SEARCH DEBUG =====")
        for titel, score in results:
            print("Score:", score)
            print("Titel:", titel.metadata.get("titel"))
            print("-------------------------------")

        #MAX_DISTANCE = 0.75
        #RELAXED_MAX_DISTANCE = 0.92 #0.95|0.10 läuft nicht im Fall:Unterfinanzierung der Bundesfeuersperrung| best= 0.946692(falsch Antw), second= 1.048964
        #MIN_GAP_TO_SECOND = 0.12
        MAX_DISTANCE = 0.3
        RELAXED_MAX_DISTANCE = 0.4
        MIN_GAP_TO_SECOND = 0.02

        accepted= False
        if best_score <= MAX_DISTANCE:
            accepted = True
        elif ( second_score is not None and best_score <= RELAXED_MAX_DISTANCE and (second_score - best_score) >= MIN_GAP_TO_SECOND ):
           accepted = True

        if not accepted  : #vermeide ,dass ein falscher Vorgang zurückgegeben wird, falls die Top3 alle falsch sind
            print(f"Kein sicherer Vorgang gefunden. Bester Score: {best_score}")
            return None

        metadata = best_vorgang.metadata

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



    #das sucht die relevantesten Chunks für die Nutzerfrage aber nur innerhalb der Dokumente des gefundenen Vorgangs
    def _get_relevant_chunks_for_vorgang(self, user_message: str, document_ids: List[int], k: int = 12):
        if not document_ids:
            return []

        strategy = self.valves.VORGANG_CHUNK_RETRIEVAL.strip().lower()
        metadata_filter = {"document_id": {"$in": document_ids}}

        print("===== VORGANG CHUNK RETRIEVAL =====")
        print("Strategie:", strategy)
        print("verwendete Dokument-IDs:", document_ids)
        print("k:", k)

        if strategy == "similarity_filtered":
            results = self.db.similarity_search(
                user_message,
                k=k,
                filter=metadata_filter
            )

        elif strategy == "mmr_filtered":
            results = self.db.max_marginal_relevance_search(
                user_message,
                k=k,
                fetch_k=40,
                filter=metadata_filter
            )
        else:
            raise ValueError(
                f"Unbekannte VORGANG_CHUNK_RETRIEVAL-Strategie: {strategy}"
            )

        for r in results:
            metadata = r.metadata if hasattr(r, "metadata") else {}
            print(
                "doc_id:", metadata.get("document_id"),
                "| page:", metadata.get("page_number"),
                "| chunk:", metadata.get("chunk_id")
            )

        return results

    #baut aus den Dokumenten + Chunks eine Vorgangs-Zusammenfassung
    def _handle_vorgang_request(self, user_message: str):
        total_start= time.time()
        t0= time.time()
        vorgang= self._find_vorgang_semantic(user_message)
        print(f"VORGANG SEARCH TIME:{time.time() - t0:.2f} s")

        if not vorgang :
            print(f"TOTAL TIME: {time.time() - total_start:.2f} s")
            return "Ich konnte leider keinen passenden Vorgang in der Datenbank finden"

        vorgang_id,dip_id,titel, vorgangstyp,datum_erstellt, datum_aktualisiert = vorgang

        t0= time.time()
        documents =self._get_documents_for_vorgang(vorgang_id)  #Zugehörige Dokumente laden
        print(f"VORG-DOCUMENT TIME: {time.time() - t0:.2f} s")
        print(f" {len(documents)} Dokumente wurden geladen")

        if not documents:
            print(f"TOTAL TIME : {time.time() - total_start:.2f} s")
            return f"Zum Vorgang '{titel}' wurden keine verknüpften Dokumente gefunden"


        if len(documents) == 1:
            analyse_mode = "single_document"
        else:
            analyse_mode = "timeline"

        document_ids  =[doc_id for doc_id, _, _, _, _ in documents]  #IDs der Dokumente sammeln [12,15]
        retrieval_start= time.perf_counter() #t0= time.time()
        relevant_chunks = self._get_relevant_chunks_for_vorgang(user_message,document_ids, k=6) #Alle Chunks dieser Dokumente laden
        retrieval_time =time.perf_counter() - retrieval_start #reine Retrieval-Zeit ohne Vorgangssuche und LLM
        print(f"CHUNKS RETRIVIAL TIME:",round(retrieval_time,2) ,"s")
        print(f"{len(relevant_chunks)} relevante Chunks gefunden")

        if self.valves.EVALUATION_ENABLED and self.valves.EVALUATION_QUESTION_ID.strip(): #Speichert die Retrieval-Ergebnisse nur bei aktivierter VORGANG-Evaluation

            question_id = self.valves.EVALUATION_QUESTION_ID.strip()
            strategy = self.valves.VORGANG_CHUNK_RETRIEVAL

            run = self._get_next_evaluation_run(question_id,"VORGANG",strategy )

            #Speichert jeden gefundenen Chunk mit Rang, Dokument und Vorgang
            for rank, result in enumerate(relevant_chunks, start=1):
                metadata = getattr(result, "metadata", {})
                self._append_evaluation_row(
                    question_id=question_id,
                    scenario="VORGANG",
                    strategy=strategy,
                    run=run,
                    retrieval_time=retrieval_time,
                    rank=rank,
                    chunk_id=metadata.get("chunk_id", ""),
                    document_id=metadata.get("document_id", ""),
                    page_number=metadata.get("page_number", ""),
                    vorgang_id=vorgang_id
                )

            if not relevant_chunks:
                self._append_evaluation_row(
                    question_id=question_id,
                    scenario="VORGANG",
                    strategy=strategy,
                    run=run,
                    retrieval_time=retrieval_time,
                    rank="",
                    chunk_id="",
                    document_id="",
                    page_number="",
                    vorgang_id=vorgang_id
                )

        #Chunks pro Dok-id gruppieren [{"chunk_index": 0, "content": "...", "page_number": 1}, ...],
        t0=time.time()
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

            if len(documents) == 1 or len(documents) == 2: #Block des 10min
                selected_chunks = doc_chunks[:3] ##nur die 3 ersten besten Chunks pro Dokument
                max_chars_per_doc = 2500
            elif len(documents) == 3:
                selected_chunks = doc_chunks[:2] #3Dok->2besten Chunks pro Dok
                max_chars_per_doc = 1600
            else:
                selected_chunks = doc_chunks[:2]  #>4 ,4Dok =4800Chunks
                max_chars_per_doc = 1200

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
                continue #um zu vermeiden ,dass alles kaputtgeht ,wenn ein Dok kein Chunks hat

            combined_text = combined_text[:max_chars_per_doc]

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

        if not timeline_parts:
            return "kein relevanter Inhalt für dieses Dokument gefunden"

        timeline_context= "\n\n".join(timeline_parts) #chronologisch sortiert: bloc doc1, bloc doc2, ...
        print(f"KONTEXT BUILD TIME: {time.time() - t0:.2f} s")
        print(f"Kontextgröße: {len(timeline_context)}")


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
        - Verwende NUR Informationen aus den Dokumenten und keine Nummerierung.
        - Berücksichtige alle relevanten bereitgestellten Dokumente.
        - Erfinde keine zusätzlichen Abschnitte.
        """
            structure_instruction = """
        Strukturiere deine Antwort wie folgt:
        
        1. BEGINN
        Beschreibe hier ausschließlich den Start des Vorgangs.
        
        2. ENTWICKLUNG
        Beschreibe die chronologische Entwicklung Schritt für Schritt.
        
        3. VERÄNDERUNGEN
        Beschreibe nur inhaltliche Änderungen, Ergänzungen oder Ausschlüsse.
        
        4. AKTUELLER STAND
        Beschreibe hier ausschließlich den aktuellen Stand basierend auf dem letzten Dokument"""

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
        print(f"Promptgröße: {len(prompt)}")

        t0=time.time()
        response = self.llm.invoke(prompt)
        print(f"LLM TIME: {time.time() -t0:.2f} s")

        unique_sources = []  #Doppelte Quellen entfernen
        seen = set()

        for source in sources:
            if source not in seen:
                seen.add(source)
                unique_sources.append(source)
        if unique_sources:
            response += "\n\nQuellen:\n- " + "\n- ".join(unique_sources)

        print(f"--TOTAL TIME--: {time.time()- total_start:.2f} s")
        return response



    def _retrieval_document_qa(self, user_message: str, k: int):
        strategy = self.valves.DOCUMENT_QA_RETRIEVAL.strip().lower()

        print("===== DOCUMENT QA RETRIEVAL =====")
        print("Strategie:", strategy)
        print("k:", k)

        if strategy== "similarity":
            return self.db.similarity_search(
                user_message,
                k=k
            )

        elif strategy =="score":
            threshold =self.valves.DOCUMENT_QA_SCORE_THRESHOLD

            if threshold is None:
                raise ValueError(
                    "Für die score-basierte Similarity Search muss "
                    "DOCUMENT_QA_SCORE_THRESHOLD festgelegt werden."
                )

            scored_results= self.db.similarity_search_with_score(user_message,k=k)
            results = []

            for document, score in scored_results:
                print(
                    "Score:",score,
                    "| Titel:",document.metadata.get("titel"),
                    "| Seite:",document.metadata.get("page_number")
                )

                if score <= threshold:
                    results.append(document)

            print("Score-Threshold:", threshold)
            print("Akzeptierte Treffer:", len(results))

            return results

        elif strategy == "mmr":
            return self.db.max_marginal_relevance_search(
                user_message,
                k=k,
                fetch_k=20,
                lambda_mult=0.9
            )

        elif strategy == "hybrid":
            raise NotImplementedError(
                "Hybrid Retrieval wird im nächsten Schritt ergänzt."
            )

        else:
            raise ValueError(
                f"Unbekannte DOCUMENT_QA_RETRIEVAL-Strategie: {strategy}"
            )


    def _classify_intent(self, user_message: str) -> str:
        classify_start = time.perf_counter()
        text = user_message.lower()

        system_keywords = [
            "ich brauche hilfe", "was kannst du", "wer bist du", "wozu dienst du", "wozu du dienst", "dein ziel" , "deine rolle", "deine hilfe",
            "wie funktionierst du","wie du funktionierst", "wie kann ich dich benutzen", "dich benutzen", "kannst du mir helfen", "hilf mir",
            "deine kernfunktion", "deine funktionen", "deine hauptfunktion"
        ]

        summary_keywords= [
            "zusammenfassung", "fasse kurz", "fasse" "zusammenfassen", "die wichtigen Inhalten", "die wichtigen Punkte", "die relevanten Punkte" ,
            "kurz zusammen", "resümee", "fasse zusammen", "fasse dieses Dokuments zusammen", "wichtigsten Inhalten", "wichtigsten Punkte" , "relevantesten Punkte"
        ]

        vorgang_keywords =[
            "vorgang", "vorgangs", "verlauf", "entwicklung", "timeline", "wie hat sich das thema","wie sich das thema" ,
            "verfolge", "im zeitverlauf","aktuelle stand" "aktueller stand", "chronologisch","im laufe der zeit", "timeline"

        ]

        if any(k in text for k in system_keywords):
            return "SYSTEM_HELP"

        if any(k in text for k in summary_keywords):
            return "ZUSAMMENFASSUNG"

        if any(k in text for k in vorgang_keywords):
            return "VORGANG"

        #Fallback
        print("INTENT LLM TIME:", round(time.perf_counter() - classify_start, 2), "s")
        return "DOCUMENT_QA"


    def pipe(self, user_message: str, model_id: str, messages: List[dict], body: dict):
        try:
            total_start = time.perf_counter()
            if self.embedding is None or self.db is None or self.llm is None:
                self._init_components()

            if user_message.strip().startswith("### Task:"):   #Bloc usermessage von OPENWBUI
                return ""

            if body.get("stream") is False: #vermeide, dass pipe() 2mal aufgerufen wird und 2 mal ergebnisse in docker logs liefert
                return ""

            intent_start = time.perf_counter()
            intent = self._classify_intent(user_message)
            print("INTENT TIME:", round(time.perf_counter() - intent_start, 2), "s")
            print("USER MESSAGE:", user_message)
            print("CLASSIFIED INTENT:", intent)
            print("EVALUATION:",self.valves.EVALUATION_ENABLED,"| QUESTION_ID:",self.valves.EVALUATION_QUESTION_ID,"| CSV:",self.valves.EVALUATION_CSV_PATH)

            if intent == "SYSTEM_HELP":     #Hilfe für Nutzer
                return """
                    Ich bin ein KI-Assistent für politische Dokumentenanalyse.

                    Ich kann Ihnen helfen bei:
                    - Fragen zu politischen Dokumenten (z.B: Was wurde über Energiewirtschaftsgesetz gesagt ?)
                    - Zusammenfassungen von Dokumenten (z.B:Fasse die wichtigsten Punkte dieses Dokuments zusammen)
                    - dem Verfolgen politischer Vorgänge im Zeitverlauf (z.B:Verfolge den Vorgang zum Gas- und Wasserstoff-Binnenmarktpaket)
                """

            if intent == "VORGANG":      #vorgg
                return self._handle_vorgang_request(user_message)

            if intent =="ZUSAMMENFASSUNG":
                kk= 6
            else:
                kk = self.valves.TOP_K

            #results = self.db.similarity_search(user_message, k=kk)
            retrieval_start = time.perf_counter()
            results = self._retrieval_document_qa(
                    user_message,
                    k=kk
            )

            retrieval_time= time.perf_counter() - retrieval_start
            print("RETRIEVAL TIME:",round(retrieval_time, 2), "s")

            #Speichert Retrieval-Ergebnisse nur bei aktivierter DOCUMENT_QA-Evaluation
            if intent== "DOCUMENT_QA" and self.valves.EVALUATION_ENABLED and self.valves.EVALUATION_QUESTION_ID.strip():

                question_id = self.valves.EVALUATION_QUESTION_ID.strip()
                strategy = self.valves.DOCUMENT_QA_RETRIEVAL

                #Bestimmt einmal die Run-Nummer für den gesamten Retrieval-Durchlauf
                run = self._get_next_evaluation_run(
                    question_id,
                    "DOCUMENT_QA",
                    strategy
                )

                #Speichert jeden zurückgegebenen Chunk mit seinem Retrieval-Rang
                for rank, result in enumerate(results, start=1):
                    metadata = getattr(result, "metadata", {})

                    self._append_evaluation_row(
                        question_id=question_id,
                        scenario="DOCUMENT_QA",
                        strategy=strategy,
                        run=run,
                        retrieval_time=retrieval_time,
                        rank=rank,
                        chunk_id=metadata.get("chunk_id", ""),
                        document_id=metadata.get("document_id", ""),
                        page_number=metadata.get("page_number", "")
                    )

                #Speichert auch einen Durchlauf, bei dem kein Chunk gefunden wurde
                if not results:
                    self._append_evaluation_row(
                        question_id=question_id,
                        scenario="DOCUMENT_QA",
                        strategy=strategy,
                        run=run,
                        retrieval_time=retrieval_time,
                        rank="",
                        chunk_id="",
                        document_id="",
                        page_number=""
                    )

            print("===== RETRIEVAL DEBUG =====")
            #Die Chunks werden nummeriert, damit das LLM diejenigen angeben kann, die es verwendet
            context_start = time.perf_counter()
            numbered_context_parts = []
            for i, r in enumerate(results, start=1):
                #content = r.page_content if hasattr(r, "page_content") else str(r)
                #numbered_context_parts.append(f"[Quelle {i}]\n{content}")
                content = r.page_content if hasattr(r, "page_content") else str(r)
                metadata = r.metadata if hasattr(r, "metadata") else {}
                #content_l = content[:850]
                titel = metadata.get("titel", "Ohne Titel")
                page_number = metadata.get("page_number", "unbekannt")

                print(f"\n--- RESULT {i} ---")
                print("Titel:", metadata.get("titel"))
                print("Seite:", metadata.get("page_number"))
                print(content)

                # So kann das LLM besser erkennen, welche Quelle zu welchem Inhalt gehört.
                numbered_context_parts.append(f"""
                [Quelle {i}] Titel: {titel} Seite: {page_number}\n Inhalt: {content}
                """)

            context = "\n\n".join(numbered_context_parts)
            print("CONTEXT BUILD TIME:", round(time.perf_counter() - context_start, 2), "s")

            if intent == "ZUSAMMENFASSUNG":
                prompt = f"""
            Du bist ein KI-Assistent für politische Dokumentenanalyse.

            Deine Aufgabe ist es, das relevante Dokument kurz und klar zusammenzufassen.

            Strukturiere deine Antwort wie folgt:

            1. Thema des Dokuments
            2. Wichtige Inhalte
            3. Ziel oder Zweck des Dokuments

            Wichtig:
            - Verwende nur die Informationen aus dem Kontext.
            - Erfinde nichts.
            - Wenn der Kontext nicht direkt auf die Frage antwortet, antworte genau:
            "Ich kann die gewünschte Zusammenfassung zu diesem Thema nicht erstellen, da der vorliegende Kontext keine spezifischen Informationen zu diesem Thema enthält. 
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
                - Antworte kurz und auf Deutsch.
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

            print("PROMPT LENGTH:", len(prompt))

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

