from fastapi import FastAPI, File, UploadFile, Header, HTTPException
import pdfplumber
import re
import tempfile
import os
import openai
import json

app = FastAPI()

# --- 1. Schéma JSON de sortie pour function-calling
extract_cv_schema = {
    "name": "extract_cv",
    "description": "Extract all information from a CV into a structured JSON",
    "parameters": {
        "type": "object",
        "properties": {
            "personal_information": { "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "title": {"type": "string"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                    "location": {"type": "string"}
                }
            },
            "experience": {
                "type": "array",
                "items": {"type":"object",
                    "properties": {
                        "role": {"type":"string"},
                        "company": {"type":"string"},
                        "start_date": {"type":"string"},
                        "end_date": {"type":"string"},
                        "responsibilities": {
                            "type":"array","items":{"type":"string"}
                        },
                        "environment": {
                            "type":"array","items":{"type":"string"}
                        }
                    }
                }
            },
            # … autres sections (education, certifications, skills, languages)
        },
        "required": ["personal_information", "experience"]
    }
}

# --- 2. Extraction texte en colonnes + reconstruction
def extract_text_columns(path):
    text_pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=True)
            # calcul médiane
            mids = sorted([w["x0"] for w in words])
            x_mid = mids[len(mids)//2]
            left = [w for w in words if w["x0"] < x_mid]
            right= [w for w in words if w["x0"] >= x_mid]
            def reconstruct(col):
                col_sorted = sorted(col, key=lambda w: (w["top"], w["x0"]))
                paras, line, cur_top = [], [], None
                for w in col_sorted:
                    if cur_top and abs(w["top"]-cur_top)>8:
                        paras.append(" ".join(line))
                        line=[]
                    line.append(w["text"]); cur_top=w["top"]
                if line: paras.append(" ".join(line))
                return "\n".join(paras)
            text_pages.append(reconstruct(left) + "\n" + reconstruct(right))
    return "\n\n".join(text_pages)

# --- 3. FastAPI endpoint
@app.post("/extract-cv/")
async def extract_cv(file: UploadFile = File(...), api_key: str = Header(default=None)):
    if not api_key.startswith("sk-"):
        raise HTTPException(401, "API key missing or invalid")
    openai.api_key = api_key

    # étape A : extraire le texte du PDF en conservant l'ordre de lecture
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(await file.read()); tmp.close()
    raw_text = extract_text_columns(tmp.name)
    os.unlink(tmp.name)

    # étape B : appel GPT-4 avec function-calling
    resp = openai.ChatCompletion.create(
        model="gpt-4.1",
        messages=[
            {"role":"system","content":
             "Vous êtes un assistant d'extraction de CV. Répondez UNIQUEMENT par un appel de fonction `extract_cv`."},
            {"role":"user","content": raw_text}
        ],
        functions=[extract_cv_schema],
        function_call={"name":"extract_cv"}
    )

    args = resp.choices[0].message.function_call.arguments
    data = json.loads(args)
    return data
