from fastapi import FastAPI, File, UploadFile, Header, HTTPException
import openai
import tempfile
import os
import time

app = FastAPI()

@app.post("/extract-cv/")
async def extract_cv(
    file: UploadFile = File(...),
    api_key: str = Header(default=None)
):
    if not api_key or not api_key.lower().startswith("sk-"):
        raise HTTPException(status_code=401, detail="API key must be provided in header 'api-key' and start with sk-...")

    openai.api_key = api_key

    # Enregistrer temporairement le fichier
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        temp_path = tmp.name

    try:
        # Uploader le fichier vers OpenAI
        uploaded_file = openai.files.create(
            file=open(temp_path, "rb"),
            purpose="assistants"
        )
        print("Fichier uploadé :", uploaded_file)

        # Créer l'assistant avec file_search activé
        assistant = openai.beta.assistants.create(
            name="CV Extractor",
            instructions="""
            Tu es un assistant expert en analyse de CV PDF.
            Retourne un JSON structuré avec :
            - Informations personnelles
            - Expériences (dates, entreprise, poste, missions, compétences)
            - Diplômes, formations
            - Certifications
            - Langues
            - Compétences techniques et personnelles
            - Périodes d’inactivité
            - Nombre d'années d'expérience

            Fournis uniquement ces données en JSON, sans texte supplémentaire.
            """,
            model="gpt-4.1",
            tools=[{"type": "file_search"}]
        )

        # Créer un thread de discussion
        thread = openai.beta.threads.create()

        # Ajouter un message utilisateur avec attachement du fichier
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Analyse ce CV et renvoie les informations sous forme de JSON.",
            attachments=[
                {
                    "file_id": uploaded_file.id,
                    "tools": [{"type": "file_search"}]
                }
            ]
        )

        # Lancer le traitement
        run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id
        )

        # Attendre que le traitement se termine avec log en cas d'erreur
        while True:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

            if run_status.status == "completed":
                break
            elif run_status.status in ["failed", "cancelled", "expired"]:
                print("Échec du run OpenAI:")
                print(run_status)
                raise HTTPException(status_code=500, detail=f"OpenAI run failed: {run_status.status}")
            
            time.sleep(2)

        # Récupérer la réponse finale
        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        final_message = messages.data[0].content[0].text.value

        return {"result": final_message}

    finally:
        os.remove(temp_path)
