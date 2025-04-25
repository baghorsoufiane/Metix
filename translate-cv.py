from fastapi import FastAPI, Header, HTTPException, Request, Query
from typing import Optional, Union
import httpx
import os

app = FastAPI(title="Hireform CV Translation API")

DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")  # Clé DeepL à définir dans l'environnement

# Clés à exclure de la traduction
EXCLUDED_KEYS = {
    "name", "email", "phone", "institution", "school", "company",
    "start_date", "end_date", "location", "languages", "issuer"
}

# Fonction de traduction texte avec DeepL
async def translate_text(text: str, target_lang: str, glossary_id: Optional[str] = None) -> str:
    url = "https://api-free.deepl.com/v2/translate"
    headers = { "Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}" }
    data = {
        "text": text,
        "target_lang": target_lang.upper(),
    }
    if glossary_id:
        data["glossary_id"] = glossary_id

    async with httpx.AsyncClient() as client:
        response = await client.post(url, data=data, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Erreur DeepL : " + response.text)
        return response.json()["translations"][0]["text"]

# Fonction récursive de traduction JSON
async def translate_json(obj, target_lang: str, glossary_id: Optional[str] = None, parent_key: Optional[str] = None):
    if isinstance(obj, dict):
        return {
            key: await translate_json(value, target_lang, glossary_id, parent_key=key)
            for key, value in obj.items()
        }
    elif isinstance(obj, list):
        return [await translate_json(item, target_lang, glossary_id, parent_key=parent_key) for item in obj]
    elif isinstance(obj, str):
        if parent_key in EXCLUDED_KEYS:
            return obj
        return await translate_text(obj, target_lang, glossary_id)
    else:
        return obj

# Endpoint de traduction
@app.post("/translate-cv/")
async def translate_cv(
    request: Request,
    api_key: str = Header(..., alias="api-key"),
    header_lang: Optional[str] = Header(None, alias="target-lang"),
    query_lang: Optional[str] = Query("EN", alias="target_lang")
):
    if not api_key.startswith("sk-"):
        raise HTTPException(status_code=401, detail="Clé API invalide")
    if not DEEPL_API_KEY:
        raise HTTPException(status_code=500, detail="Clé API DeepL manquante")

    target_lang = header_lang or query_lang

    try:
        raw_json = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Format JSON invalide")

    glossary_id = None  # Optionnel
    translated = await translate_json(raw_json, target_lang, glossary_id)

    return translated
