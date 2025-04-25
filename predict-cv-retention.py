from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from dateutil.parser import parse as parse_date
from esco import LocalDB
import pandas as pd
import numpy as np
import joblib
import json

app = FastAPI(title="Hireform CV Retention Predictor")

# --- Sécurité simple par clé API (OpenAI-style sk-…)
api_key_header = APIKeyHeader(name="api-key", auto_error=True)
def validate_key(key: str = Depends(api_key_header)):
    if not key.startswith("sk-"):
        raise HTTPException(401, "API key invalide")
    return key

# --- Chargement ML model
model = joblib.load("cv_retention_model.pkl")  # modèle scikit-learn entraîné au préalable

# --- Initialisation ESCO local DB
esco_db = LocalDB()  # charge les JSON embarqués  [oai_citation:5‡PyPI](https://pypi.org/project/pyEscoAPI/?utm_source=chatgpt.com)

# --- Fonction d’alignement ESCO
def map_to_esco(label: str) -> int:
    """
    Recherche l’item ESCO le plus proche pour un label (intitulé poste ou skill).
    Retourne 1 si trouvé, 0 sinon (on peut aussi retourner l’ID).
    """
    results = esco_db.search_products({label})
    return 1 if not results.empty else 0  # binaire pour simplifier

# --- Endpoint principal
@app.post("/predict-cv-retention/", dependencies=[Depends(validate_key)])
async def predict_cv_retention(request: Request):
    try:
        cv = await request.json()
    except:
        raise HTTPException(400, "JSON invalide")

    # 1) Parcours des expériences pour extraire biodata
    exp = cv.get("experience", [])
    if not isinstance(exp, list) or len(exp) == 0:
        raise HTTPException(400, "Pas d'expériences dans le CV")

    periods = []
    for e in exp:
        start = parse_date(e["start_date"])
        end = parse_date(e["end_date"])
        periods.append((start, end))
    # Trier par date
    periods.sort(key=lambda x: x[0])
    # Durée moyenne (en mois)
    durations = [(e[1] - e[0]).days / 30 for e in periods]
    avg_tenure = np.mean(durations)
    # Nombre de postes (biodata item)
    num_positions = len(periods)
    # Nombre de pauses (breaks > 3 mois)
    breaks = sum(
        1 
        for (s0, e0), (s1, e1) in zip(periods, periods[1:])
        if (s1 - e0).days / 30 > 3
    )

    # 2) Compétences et ESCO
    skills = cv.get("skills", [])
    num_skills = len(skills)
    esco_skills = sum(map_to_esco(s) for s in skills)  # count skills alignés  [oai_citation:6‡GitHub](https://github.com/par-tec/esco-playground?utm_source=chatgpt.com)

    # 3) Intitulés de postes ESCO
    num_esco_titles = sum(map_to_esco(e.get("role", "")) for e in exp)

    # 4) Construction du vecteur de features
    X = np.array([[avg_tenure, num_positions, breaks, num_skills, esco_skills, num_esco_titles]])

    # 5) Prédiction de probabilité
    try:
        prob = float(model.predict_proba(X)[0][1])
    except Exception as e:
        raise HTTPException(500, f"Erreur modèle : {e}")

    # 6) Catégorisation
    category = "High risk" if prob > 0.5 else "Low risk"

    return {
        "risk_score": round(prob, 3),
        "risk_category": category,
        "features": {
            "avg_tenure_months": round(avg_tenure, 1),
            "num_positions": num_positions,
            "num_breaks": breaks,
            "num_skills": num_skills,
            "esco_skills_mapped": esco_skills,
            "esco_titles_mapped": num_esco_titles
        }
    }
