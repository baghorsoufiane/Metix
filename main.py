from fastapi import FastAPI, File, UploadFile, Header, HTTPException
import openai
import tempfile
import os
import time

app = FastAPI()

@app.post("/upload-cv/")
async def upload_cv(
    file: UploadFile = File(...),
    authorization: str = Header(...)
):
    # 1. Récupérer la clé API depuis l'en-tête Authorization
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization header must be in the format: Bearer sk-...")
    
    api_key = authorization[7:].strip()
    openai.api_key = api_key

    # 2. Sauvegarde temporaire du fichier PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        temp_path = tmp.name

    try:
        # 3. Upload du fichier vers OpenAI
        uploaded_file = openai.files.create(
            file=open(temp_path, "rb"),
            purpose="assistants"
        )

        # 4. Création de l'assistant avec instructions
        assistant = openai.beta.assistants.create(
            name="CV Extractor",
            instructions="""
            Tu es un assistant expert en lecture de CV. Analyse le fichier PDF fourni et retourne un JSON avec :
            - Informations personnelles
            - Expériences pro (dates, entreprise, poste, missions, compétences)
            - Éducation (écoles, diplômes)
            - Certifications
            - Compétences techniques et personnelles
            - Langues
            - Années d’expérience
            - Périodes d’inactivité
            """,
            model="gpt-4-turbo"
        )

        # 5. Créer un thread et y envoyer le message avec le fichier
        thread = openai.beta.threads.create()
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Merci d’extraire les informations du CV joint en JSON structuré.",
            file_ids=[uploaded_file.id]
        )

        # 6. Lancer la tâche
        run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id
        )

        # 7. Poller jusqu’à complétion
        while True:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run_status.status == "completed":
                break
            elif run_status.status in ["failed", "cancelled", "expired"]:
                raise HTTPException(status_code=500, detail=f"Run failed: {run_status.status}")
            time.sleep(2)

        # 8. Récupérer le message final
        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        final_message = messages.data[0].content[0].text.value

        return {"result": final_message}

    finally:
        os.remove(temp_path)
