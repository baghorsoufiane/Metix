from fastapi import FastAPI, Request, UploadFile, File, Query, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from docxtpl import DocxTemplate
from jinja2 import Environment, FileSystemLoader
import openai, io, os, subprocess, tempfile, json

app = FastAPI()

# Authentification
api_key_header = APIKeyHeader(name="api-key")
def validate_key(key: str = Depends(api_key_header)):
    if key != os.getenv("API_KEY"):
        raise HTTPException(401, "API key invalide")
    return key

@app.post("/format-offer", summary="Formate une offre d'emploi dans différents formats")
async def format_offer(
    hr_json: dict,                                 # JSON standardisé (HR-JSON)  [oai_citation:5‡Microsoft Learn](https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design?utm_source=chatgpt.com)
    template_file: UploadFile = File(None),        # Template .docx Jinja2 pour ATS
    formats: list[str] = Query(..., description="Formats souhaités : ats, linkedin, web"),
    as_pdf: bool = Query(False, description="True pour PDF, False pour DOCX/HTML"),
    api_key: str = Depends(validate_key)
):
    outputs = {}

    # 1) Version LinkedIn via GPT-4 Turbo
    if "linkedin" in formats:
        prompt = f"Formate pour LinkedIn : {hr_json.get('description')}"
        resp = openai.Completion.create(model="gpt-4.1", prompt=prompt, max_tokens=300)
        outputs["linkedin"] = resp.choices[0].text.strip()

    # 2) Version ATS (DOCX/PDF) via python-docx-template
    if "ats" in formats:
        if not template_file:
            raise HTTPException(400, "Template .docx requis pour ats")
        buf = await template_file.read()
        doc = DocxTemplate(io.BytesIO(buf))
        doc.render(hr_json)                                 # {{ title }}, {{ description }}… 
        stream = io.BytesIO(); doc.save(stream); stream.seek(0)
        if as_pdf:
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "x.docx")
                open(path, "wb").write(stream.getvalue())
                subprocess.run(["libreoffice","--headless","--convert-to","pdf",path], check=True)
                outputs["ats"] = ("pdf", open(path.replace(".docx",".pdf"),"rb").read())
        else:
            outputs["ats"] = ("docx", stream.getvalue())

    # 3) Version Web (HTML + JSON-LD)
    if "web" in formats:
        env = Environment(loader=FileSystemLoader("templates"))
        html = env.get_template("web_template.html").render(**hr_json)  # HTML semantique  [oai_citation:6‡Blog](https://blog.dreamfactory.com/best-practices-for-naming-rest-api-endpoints?utm_source=chatgpt.com)
        # Inject JSON-LD schema.org
        jsonld = { "@context":"https://schema.org/","@type":"JobPosting", **{k:hr_json[k] for k in ("title","description","datePosted") if k in hr_json}}
        full_html = html.replace("</body>",
                                 f"<script type='application/ld+json'>\n{json.dumps(jsonld,ensure_ascii=False)}\n</script>\n</body>")
        outputs["web"] = full_html

    return outputs
