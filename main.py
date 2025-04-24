from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
import openai

app = FastAPI()

class CVRequest(BaseModel):
    file_text: str

@app.post("/extract-cv/")
async def extract_cv(
    request: CVRequest,
    authorization: str = Header(default=None),
    x_api_key: str = Header(default=None)
):
    # 1. Extraire la clé depuis Authorization: Bearer ...
    api_key = None
    if authorization and authorization.lower().startswith("bearer "):
        api_key = authorization[7:].strip()
    elif x_api_key:
        api_key = x_api_key.strip()
    
    # 2. Vérifier qu'on a bien une clé
    if not api_key:
        raise HTTPException(status_code=401, detail="API key missing in headers")

    # 3. Configurer OpenAI avec la clé dynamique
    openai.api_key = api_key

    # 4. Construction du prompt
    prompt = f"""
    Extrais les informations suivantes du texte d’un CV :
    - Informations personnelles
    - Expériences professionnelles (dates, entreprise, poste, description, compétences techniques)
    - Formation (universités, écoles)
    - Certifications
    - Compétences techniques et personnelles
    - Langues parlées
    - Nombre total d’années d’expérience
    - Périodes d’inactivité (creuses)

    Retourne un JSON structuré.

    Texte :
    {request.file_text}
    """

    # 5. Appel à OpenAI
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return {"result": response.choices[0].message["content"]}
    except openai.error.AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid OpenAI API Key")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
