from fastapi import FastAPI, Request, UploadFile, File, Query, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from docxtpl import DocxTemplate
import tempfile
import subprocess
import io
import os

app = FastAPI(title="Hireform CV Formatter")

# Auth via header api-key
api_key_header = APIKeyHeader(name="api-key", auto_error=True)
def validate_api_key(api_key: str = Depends(api_key_header)):
    if not api_key.startswith("sk-"):
        raise HTTPException(status_code=401, detail="Clé API invalide")
    return api_key

@app.post("/format-cv-template")
async def format_cv_template(
    request: Request,
    template_file: UploadFile = File(...),
    as_pdf: bool = Query(False, description="True pour générer un PDF"),
    api_key: str = Depends(validate_api_key)
):
    # Lecture du JSON de données
    try:
        data = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Données JSON invalides")

    # Lecture du template Word
    template_content = await template_file.read()
    template = DocxTemplate(io.BytesIO(template_content))

    # Injection des données dans le template
    try:
        template.render(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'injection : {e}")

    # Génération du fichier DOCX
    docx_io = io.BytesIO()
    template.save(docx_io)
    docx_io.seek(0)

    # Retour immédiat si DOCX
    if not as_pdf:
        return StreamingResponse(
            docx_io,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": "attachment; filename=cv_formatted.docx"}
        )

    # Conversion en PDF via LibreOffice headless
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_docx_path = os.path.join(tmpdir, "cv.docx")
        tmp_pdf_path = os.path.join(tmpdir, "cv.pdf")

        with open(tmp_docx_path, "wb") as f:
            f.write(docx_io.getvalue())

        subprocess.run([
            "libreoffice", "--headless", "--convert-to", "pdf", "--outdir", tmpdir, tmp_docx_path
        ], check=True)

        pdf_file = open(tmp_pdf_path, "rb")
        return StreamingResponse(
            pdf_file,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=cv_formatted.pdf"}
        )
