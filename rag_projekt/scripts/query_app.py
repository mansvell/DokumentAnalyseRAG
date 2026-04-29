#Embeddings+V-DB+ Retrieval + LLM Query hin
#1.index wird geladen und man stellt eine Frage
#2.die gestellte Frage wird in Vektor umgewandelt
#3.dieser Vektor wird dann mit anderen Vektoren des Chunks aus den PDFs verglichen
#4.Das System gibt die 3 relevantesten Chunks zurück (noch keine richtige erfasste KI-Antwort)

from langchain_community.vectorstores import Chroma # Base vectorielle
from langchain_huggingface import HuggingFaceEmbeddings # Modèle d'embedding

from langchain_ollama import OllamaLLM #2.Teil

embedding= HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2") #BAAI/bge-base-en-v1.5") #das Embedding-modell laden

db =Chroma( persist_directory="db/vector_store_prototyp",embedding_function=embedding) #die erstellte vectorielle Base laden



query= "Was wurde über Ladepunkte an Carsharing-Stellplätzen gesagt?"

#Suche nach den 3 relevantesten Chunks
results = db.similarity_search(query, k=3)






#Anzeige der 400 first caracteres
for i, r in enumerate(results):
    print(f"\n--- Ergebnis {i+1} ---")
    print("Quelle :", r.metadata.get("source", "unbekannt"))
    print(r.page_content[:400])