from fastapi import FastAPI
from pydantic import BaseModel

from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM

from fastapi.middleware.cors import CORSMiddleware #sinon Vue peut bloquer l’appel.
import time

# FastAPI Anwendung erstellen
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str


embedding = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

db = Chroma(
    persist_directory="db/vector_store_prototyp",
    embedding_function=embedding
)

llm = OllamaLLM(model="llama3.2:3b") #llama3:8b


@app.get("/")
def root():
    return {"message": "Backend läuft"}

@app.post("/query")
def ask_question(request: QueryRequest):
    start_total = time.perf_counter()

    query = request.query

    t1= time.perf_counter()
    results = db.similarity_search(query, k=3)
    t2= time.perf_counter()

    t3 = time.perf_counter()
    context = "\n\n".join([r.page_content for r in results])
    t4 = time.perf_counter()
    sources = []
    for r in results:
        source_name = r.metadata.get("source", "unbekannt")
        if source_name not in sources:
            sources.append(source_name)


    prompt = f"""
Du bist ein Assistent für politische Dokumentenanalyse.

Beantworte die Frage auf Basis des bereitgestellten Kontexts.
Wenn die Information im Kontext nicht enthalten ist, antworte genau: "Ich habe im bereitgestellten Kontext keine ausreichende Information gefunden." Antworte kurz, präzise und auf Deutsch."

Kontext:
{context}

Frage:
{query}

Antwort:
"""
    t5= time.perf_counter()
    response = llm.invoke(prompt)
    t6 = time.perf_counter()

    end_total = time.perf_counter()

    print("Vector search:", round(t2 - t1, 2), "s")
    print("Context build:", round(t4 - t3, 2), "s")
    print("Context chars:", len(context))
    print("Prompt chars:", len(prompt))
    print("LLM:", round(t6 - t5, 2), "s")
    print("Total:", round(end_total - start_total, 2), "s")


    return {
        "query": query,
        "answer": response,
        "sources": sources
    }