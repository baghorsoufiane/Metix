from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Union
import re

app = FastAPI(title="Hireform Blind Hiring API")

# Modèle de CV structuré
class Education(BaseModel):
    school: str
    degree: Optional[str]

class Experience(BaseModel):
    company: str
    role: str
    start_date: Optional[str]
    end_date: Optional[str]
    description: Optional[str]

class CV(BaseModel):
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    photo: Optional[Union[str, None]]
    education: List[Education]
    experience: List[Experience]
    skills: Optional[List[str]]

@app.post("/anonymize-cv/")
async def anonymize_cv(
    cv: CV,
    api_key: str = Header(..., alias="api-key")
):
    if not api_key.startswith("sk-"):
        raise HTTPException(status_code=401, detail="Clé API invalide")

    # Anonymisation
    anonymized = cv.dict()
    anonymized.update({
        "name": None,
        "email": None,
        "phone": None,
        "photo": None
    })

    # Masquer les écoles (ex : "HEC Paris" → "[École masquée]")
    for edu in anonymized.get("education", []):
        edu["school"] = "[École masquée]"

    return anonymized
