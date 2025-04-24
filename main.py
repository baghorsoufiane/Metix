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

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        temp_path = tmp.name

    try:
        uploaded_file = openai.files.create(
            file=open(temp_path, "rb"),
            purpose="assistants"
        )

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
            """,
            model="gpt-4-turbo"
        )

        thread = openai.beta.threads.create()

        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Analyse ce CV et renvoie les informations sous forme de JSON.",
            file_ids=[uploaded_file.id]
        )

        run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id
        )

        while True:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run_status.status == "completed":
                break
            elif run_status.status in ["failed", "cancelled", "expired"]:
                raise HTTPException(status_code=500, detail=f"OpenAI run failed: {run_status.status}")
            time.sleep(2)

        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        final_message = messages.data[0].content[0].text.value

        return {"result": final_message}

    finally:
        os.remove(temp_path)
