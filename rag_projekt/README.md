# RAG-Projekt für politische Dokumente

Dieses Projekt dient zur intelligenten Recherche in politischen PDFs wie Sitzungsprotokollen, Vorlagen und Beschlussdokumenten.

## Ziel
Fragen in natürlicher Sprache stellen und Antworten mit Quellenangaben erhalten.

## Pipeline
1. Ingestion: PDF einlesen
2. Preprocessing: Text bereinigen
3. Chunking: Text in sinnvolle Teile aufteilen
4. Embedding: Vektoren erzeugen
5. Retrieval: passende Chunks finden
6. LLM: Antwort erzeugen
7. Quellen: Dokument und Seite anzeigen

## Start
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/run_ingestion.py
```
