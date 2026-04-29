#Platzhalter:Preprocessing+ Chunking+ Embedding + Vektor-DB
#Text in Zahlen (Vektoren) verwandeln, damit der Computer Bedeutung vergleichen kann
#1.Die PDF-Dateien werden gelesen und ihr Text extrahiert.
#2.Der Text wird in kleine Abschnitte (Chunks) unterteilt.
#3.Jeder Abschnitt wird in einen Vektor (Embedding) umgewandelt.
#4.Die Vektoren werden in einer Datenbank (Chroma) gespeichert.
#5.Erstellung der Vektoren-DB(index)  #6. Speicherung der V-DB

from langchain_community.vectorstores import Chroma #Vektoren speichern
from langchain_huggingface import HuggingFaceEmbeddings

#Werkzeug zum Schneiden der texte in Stücken
from langchain_text_splitters import RecursiveCharacterTextSplitter

import fitz  #pdf lesen
import os

# Fonction pour lire tous les PDFs d'un dossier
def load_pdfs(folder):
    documts = []

    #Alle Dateien im Ordner durchgehen
    for file in os.listdir(folder):
        if file.lower().endswith(".pdf"):
            path = os.path.join(folder, file)

            pdf = fitz.open(path) #pdf öffnen
            text = ""

            #sämtliche Seiten lesen
            for page in pdf:
                text += page.get_text()

            #Text und Dateiname speichern
            documts.append({
                "source": file,
                "text": text
            })

    return documts


#Doks laden
documents = load_pdfs("data/raw")


text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)

all_chunks = []
all_metadatas = []

#
for doc in documents:
    chunks = text_splitter.split_text(doc["text"])

    for chunk in chunks:
        all_chunks.append(chunk)
        all_metadatas.append({"source": doc["source"]})


#Emb-Modell laden
embedding = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")  #BAAI/bge-base-en-v1.5

#5
db = Chroma.from_texts(
    texts=all_chunks,
    embedding=embedding,
    metadatas=all_metadatas,
    persist_directory="db/vector_store_prototyp"
)

db.persist() #6

print("Index avec chunks créé")
print(f"Nombre total de chunks : {len(all_chunks)}")