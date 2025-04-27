# main.py

import io
import json
import re
import zipfile
import tempfile
import subprocess

import httpx
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from docxtpl import DocxTemplate

app = FastAPI(title="Hireform CV Services")

# ---- Security ----
api_key_header = APIKeyHeader(name="api-key", auto_error=True)
def validate_api_key(key: str = Depends(api_key_header)):
    if not key.startswith("sk-"):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return key

# ---- 2) generate-template-cv ----
@app.post("/generate-template-cv/")
async def generate_template_cv(
    model_file: UploadFile = File(..., description="`.docx` modèle entreprise"),
    json_file:  UploadFile = File(..., description="JSON structuré issu de `/extract-cv`"),
    api_key:    str        = Depends(validate_api_key)
):
    """
    Injecte des balises Jinja2 dans un .docx existant, sans toucher à la mise en forme.
    """
    # Load JSON
    try:
        data = json.loads(await json_file.read())
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")

    # Read the .docx as a zip
    in_bytes = await model_file.read()
    zin = zipfile.ZipFile(io.BytesIO(in_bytes), 'r')
    xml = zin.read('word/document.xml').decode('utf-8')
    zin.close()

    # Prepare first items
    exp0  = data.get('experience', [{}])[0]
    edu0  = data.get('education',   [{}])[0]
    cert0 = data.get('certifications', [{}])[0]
    lang0, lvl0 = next(iter(data.get('languages', {}).items()), ("",""))

    # Map static → Jinja2
    mapping = {
        exp0.get('start_date',''):     '{{ experience.start_date }}',
        exp0.get('end_date',''):       '{{ experience.end_date }}',
        exp0.get('role',''):           '{{ experience.role }}',
        exp0.get('company',''):        '{{ experience.company }}',
        edu0.get('degree',''):         '{{ edu.degree }}',
        edu0.get('institution',''):    '{{ edu.institution }}',
        cert0.get('name',''):          '{{ cert.name }}',
        cert0.get('issuer',''):        '{{ cert.issuer }}',
        f"{lang0} : {lvl0}":           '{{ lang }} : {{ level }}',
    }
    for orig, tpl in mapping.items():
        if orig:
            xml = xml.replace(orig, tpl)

    # Function to inject loops around first occurrence
    def inject_loop(xml: str, marker: str, open_tag: str, close_tag: str) -> str:
        pattern = rf'(<w:p[^>]*?>.*?{re.escape(marker)}.*?</w:p>)'
        m = re.search(pattern, xml, flags=re.DOTALL)
        if m:
            p = m.group(1)
            xml = xml.replace(p, f"{open_tag}\n{p}\n{close_tag}")
        return xml

    xml = inject_loop(xml,
        '{{ experience.start_date }}',
        '{% for experience in experience %}',
        '{% endfor %}'
    )
    xml = inject_loop(xml,
        '{{ edu.degree }}',
        '{% for edu in education %}',
        '{% endfor %}'
    )
    xml = inject_loop(xml,
        '{{ cert.name }}',
        '{% for cert in certifications %}',
        '{% endfor %}'
    )
    xml = inject_loop(xml,
        '{{ lang }} : {{ level }}',
        '{% for lang, level in languages.items() %}',
        '{% endfor %}'
    )

    # Reassemble .docx in memory
    out_io = io.BytesIO()
    zin = zipfile.ZipFile(io.BytesIO(in_bytes), 'r')
    zout = zipfile.ZipFile(out_io, 'w')
    for item in zin.infolist():
        if item.filename == 'word/document.xml':
            zout.writestr(item, xml.encode('utf-8'))
        else:
            zout.writestr(item, zin.read(item.filename))
    zin.close()
    zout.close()
    out_io.seek(0)

    return StreamingResponse(
        out_io,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=template_cv.docx"}
    )

# ---- 3) generate-cv ----
@app.post("/generate-cv/")
async def generate_cv(
    template_file: UploadFile = File(..., description="`.docx` template Jinja2"),
    json_file:     UploadFile = File(..., description="JSON structuré du CV"),
    as_pdf:        bool       = Query(False, description="True pour PDF, False pour DOCX"),
    api_key:       str        = Depends(validate_api_key)
):
    """
    Rend le template .docx avec les données JSON, retourne DOCX ou PDF.
    """
    data = json.loads(await json_file.read())

    # Write template to temp file
    tmp_dir = tempfile.mkdtemp()
    tpl_path = os.path.join(tmp_dir, "template.docx")
    with open(tpl_path, "wb") as f:
        f.write(await template_file.read())

    # Render with docxtpl
    doc = DocxTemplate(tpl_path)
    doc.render(data)
    out_docx = os.path.join(tmp_dir, "filled.docx")
    doc.save(out_docx)

    if not as_pdf:
        return StreamingResponse(
            open(out_docx, "rb"),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": "attachment; filename=final_cv.docx"}
        )

    # Convert to PDF via LibreOffice headless
    subprocess.run([
        "libreoffice", "--headless", "--convert-to", "pdf",
        "--outdir", tmp_dir, out_docx
    ], check=True)
    out_pdf = os.path.join(tmp_dir, "filled.pdf")
    return StreamingResponse(
        open(out_pdf, "rb"),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=final_cv.pdf"}
    )

# ---- 4) transform-cv ----
@app.post("/transform-cv/")
async def transform_cv(
    cv_file:     UploadFile = File(..., description="CV brut (.pdf ou .docx)"),
    model_file:  UploadFile = File(..., description="Modèle entreprise `.docx`"),
    as_pdf:      bool       = Query(False, description="True pour PDF, False pour DOCX"),
    api_key:     str        = Depends(validate_api_key)
):
    """
    Orchestrateur :
      1) /extract-cv      → JSON
      2) /generate-template-cv → template `.docx`
      3) /generate-cv     → final `.docx` ou `.pdf`
    """
    # 1) extract-cv
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8000/extract-cv/",
            files={"file": (cv_file.filename, await cv_file.read(), cv_file.content_type)},
            headers={"api-key": api_key}
        )
        if resp.status_code != 200:
            raise HTTPException(502, f"extract-cv failed: {resp.text}")
        cv_json = resp.json()

    # 2) generate-template-cv
    async with httpx.AsyncClient() as client:
        model_bytes = await model_file.read()
        files = {
            "model_file": (model_file.filename, model_bytes, model_file.content_type),
            "json_file":  ("cv.json", json.dumps(cv_json), "application/json")
        }
        resp2 = await client.post(
            "http://localhost:8000/generate-template-cv/",
            files=files,
            headers={"api-key": api_key}
        )
        if resp2.status_code != 200:
            raise HTTPException(502, f"generate-template-cv failed: {resp2.text}")
        template_bytes = await resp2.aread()

    # 3) generate-cv
    async with httpx.AsyncClient() as client:
        files = {
            "template_file": ("template.docx", template_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            "json_file":     ("cv.json",     json.dumps(cv_json),        "application/json")
        }
        params = {"as_pdf": as_pdf}
        resp3 = await client.post(
            "http://localhost:8000/generate-cv/",
            files=files,
            params=params,
            headers={"api-key": api_key}
        )
        if resp3.status_code != 200:
            raise HTTPException(502, f"generate-cv failed: {resp3.text}")
        content = await resp3.aread()
        content_type = resp3.headers.get("content-type")
        disposition = resp3.headers.get("content-disposition")

    return StreamingResponse(
        io.BytesIO(content),
        media_type=content_type,
        headers={"Content-Disposition": disposition}
    )
