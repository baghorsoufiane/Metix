import os
import time
import openai
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------
# AJOUT ICI : Clé OpenAI directement dans le script
# (à retirer pour la prod, à stocker dans variable d’env)
# ---------------------------------------------------
openai.api_key = "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"

app = FastAPI()

# Middleware CORS (utile pour appels frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Assistant GPT-4 RH unique (créé au premier appel)
assistant_id = None

def init_cv_assistant():
    global assistant_id
    if assistant_id is None:
        assistant = openai.beta.assistants.create(
            name="CV Extractor",
            instructions="""
Tu es un assistant RH spécialisé en analyse de CV. Tu dois extraire les informations suivantes depuis le document fourni (en tenant compte de la structure, du format visuel, des titres et du contenu) et retourner un JSON structuré :

1. Informations personnelles (nom, prénom, email, téléphone, adresse s’il y en a)
2. Expériences professionnelles :
   - intitulé de poste
   - entreprise
   - dates (début et fin)
   - description (en puces)
   - compétences ou environnement technique
3. Formations (écoles/universités, diplômes, dates)
4. Certifications (avec dates)
5. Compétences techniques
6. Compétences personnelles
7. Langues (avec niveau)
8. Nombre total d’années d’expérience
9. Périodes d’inactivité de plus de 6 mois

Donne uniquement un JSON bien formaté, sans explication ou texte autour.
""",
            tools=[{"type": "code_interpreter"}],
            model="gpt-4-turbo"
        )
        assistant_id = assistant.id

init_cv_assistant()


@app.post("/extract_cv/")
async def extract_cv(file: UploadFile = File(...)):
    if not file.filename.endswith((".pdf", ".docx")):
        raise HTTPException(status_code=400, detail="Format de fichier non supporté.")

    try:
        # Lire le fichier uploadé
        contents = await file.read()

        # Upload vers OpenAI
        openai_file = openai.files.create(
            file=(file.filename, contents),
            purpose="assistants"
        )

        # Créer une session de thread
        thread = openai.beta.threads.create()

        # Ajouter un message utilisateur avec le fichier
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Voici un CV. Merci d’en extraire les informations demandées.",
            file_ids=[openai_file.id]
        )

        # Lancer le run de l’assistant
        run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant_id
        )

        # Attente de la réponse
        while True:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run_status.status == "completed":
                break
            elif run_status.status == "failed":
                raise Exception("Échec de l’analyse.")
            time.sleep(2)

        # Récupérer le résultat final
        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        result = messages.data[0].content[0].text.value

        return JSONResponse(content={"extraction": result})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur : {str(e)}")
