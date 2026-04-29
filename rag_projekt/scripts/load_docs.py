import fitz # PyMuPDF
import os

folder = "data/raw"
print("Benutzte Datei :", os.path.abspath(folder))
print("Inhalt :", os.listdir(folder))

for file in os.listdir(folder):
    if file.lower().endswith(".pdf"):
        path = os.path.join(folder, file)
        print("Lesen von :", path)

        doc = fitz.open(path)
        text = ""

        for page in doc:
            text += page.get_text()

        print(f"\n--- {file} ---")
        print(text[:1000])