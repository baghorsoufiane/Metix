from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import tempfile
import os
from transformers import pipeline
import docx2txt
import pdfplumber

app = FastAPI()

# Initialiser le pipeline NER
ner_pipeline = pipeline("ner", model="dslim/bert-base-NER", grouped_entities=True)

def extract_text(file_path, filename):
    if filename.endswith(".pdf"):
        with pdfplumber.open(file_path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    elif filename.endswith(".docx"):
        return docx2txt.process(file_path)
    else:
        return ""

@app.post("/upload-cv/")
async def upload_cv(file: UploadFile = File(...)):
    try:
        # Sauvegarder le fichier temporairement
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        # Extraire le texte du fichier
        text = extract_text(tmp_path, file.filename)

        # Appliquer le modèle NER
        ner_results = ner_pipeline(text)

        # Organiser les entités extraites
        extracted_data = {}
        for entity in ner_results:
            label = entity['entity_group']
            word = entity['word']
            extracted_data.setdefault(label, []).append(word)

        return JSONResponse(content=extracted_data)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
