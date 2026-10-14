import fitz
#test um zu prüfen , ob leere Seiten den Inhalt von nächsten Seite bein Chunking erhalten. Alles ist OK , es ist nicht der Fall

pdf_path = r"C:\Users\Nkwanga\OneDrive\Desktop\6.sem\Praxis\RAG_Projekt\rag_projekt\data\raw\2106135.pdf"

pdf = fitz.open(pdf_path)

print("Nombre de pages :", len(pdf))

for page_number in [6, 23, 24]:
    text = pdf[page_number - 1].get_text().strip()

    print(f"\n===== PAGE {page_number} =====")
    print(repr(text[:500]))

pdf.close()