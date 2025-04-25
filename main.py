import logging
from fastapi import FastAPI, File, UploadFile, Header, HTTPException
import pdfplumber
import openai
import tempfile
import os
import json

# --- 0. Configuration du logging DEBUG
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI(title="CV Extractor API")

# --- 1. Schéma JSON pour function-calling
extract_cv_schema = {
    "name": "extract_cv",
    "description": "Extract all information from a CV into a structured JSON",
    "parameters": {
        "type": "object",
        "properties": {
            "personal_information": {
                "type": "object",
                "properties": {
                    "name":     {"type": "string"},
                    "title":    {"type": "string"},
                    "email":    {"type": "string"},
                    "phone":    {"type": "string"},
                    "location": {"type": "string"}
                },
                "required": ["name", "email"]
            },
            "experience": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role":            {"type": "string"},
                        "company":         {"type": "string"},
                        "start_date":      {"type": "string"},
                        "end_date":        {"type": "string"},
                        "responsibilities":{"type": "array", "items": {"type": "string"}},
                        "environment":     {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["role", "company", "start_date", "end_date"]
                }
            },
            "certifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":   {"type": "string"},
                        "issuer": {"type": "string"}
                    },
                    "required": ["name"]
                }
            },
            "education": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "degree":      {"type": "string"},
                        "institution": {"type": "string"}
                    },
                    "required": ["degree", "institution"]
                }
            },
            "skills": {
                "type": "object",
                "additionalProperties": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "languages": {
                "type": "object",
                "additionalProperties": {"type": "string"}
            }
        },
        "required": ["personal_information", "experience", "skills", "languages"]
    }
}

# --- 2. Extraction PDF avec gestion de colonnes
def extract_text_columns(pdf_path: str) -> str:
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=True)
            if not words:
                continue
            xs = sorted(w["x0"] for w in words)
            x_mid = xs[len(xs) // 2]
            left  = [w for w in words if w["x0"] < x_mid]
            right = [w for w in words if w["x0"] >= x_mid]

            def reconstruct(col_words):
                col_words = sorted(col_words, key=lambda w: (w["top"], w["x0"]))
                paras, line, cur_top = [], [], None
                for w in col_words:
                    if cur_top and abs(w["top"] - cur_top) > 8:
                        paras.append(" ".join(line))
                        line = []
                    line.append(w["text"])
                    cur_top = w["top"]
                if line:
                    paras.append(" ".join(line))
                return "\n".join(paras)

            pages_text.append(reconstruct(left) + "\n" + reconstruct(right))
    return "\n\n".join(pages_text)

# --- 3. Endpoint /extract-cv/ avec header api-key et debug logging
@app.post("/extract-cv/")
async def extract_cv(
    file: UploadFile = File(...),
    api_key: str = Header(..., alias="api-key")  # <-- api-key passé ici
):
    logger.debug("=== /extract-cv/ called ===")
    logger.debug(f"Received api-key: {api_key[:5]}... (length={len(api_key)})")
    if not api_key.startswith("sk-"):
        logger.error("API key invalide ou manquante")
        raise HTTPException(status_code=401, detail="Clé API invalide ou manquante")

    openai.api_key = api_key

    # Sauvegarde temporaire du PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        content = await file.read()
        tmp.write(content)
        temp_path = tmp.name
    logger.debug(f"PDF temporaire enregistré sous {temp_path} ({len(content)} bytes)")

    try:
        # Extraction du texte
        raw_text = extract_text_columns(temp_path)
        logger.debug(f"Raw text extrait (premiers 200 chars): {raw_text[:200]!r}")

        # Appel API OpenAI : syntaxe `openai.chat.completions.create(...)`
        logger.info("Appel openai.chat.completions.create() …")
        try:
            response = openai.chat.completions.create(
                model="gpt-4-0613",
                messages=[
                    {"role": "system", "content": "Tu es un assistant d’extraction de CV. Réponds seulement via la fonction extract_cv."},
                    {"role": "user",   "content": raw_text}
                ],
                functions=[extract_cv_schema],
                function_call={"name": "extract_cv"}
            )
        except Exception as e:
            logger.exception("Erreur lors de l'appel à OpenAI")
            raise HTTPException(status_code=502, detail=f"Erreur OpenAI: {e}")

        logger.info("Réponse reçue de l'API OpenAI")
        msg = response.choices[0].message
        if not hasattr(msg, "function_call"):
            logger.error("Aucun function_call dans la réponse")
            raise HTTPException(status_code=500, detail="OpenAI n’a pas renvoyé de function_call")

        args = msg.function_call.arguments
        logger.debug(f"function_call.arguments (type={type(args)}): {args!r}")

        # Parsing JSON
        if isinstance(args, str):
            data = json.loads(args)
        else:
            data = args

        logger.debug("Extraction JSON réussie, renvoi du résultat")
        return data

    finally:
        os.remove(temp_path)
        logger.debug(f"PDF temporaire supprimé : {temp_path}")
