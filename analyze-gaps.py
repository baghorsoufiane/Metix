from fastapi import FastAPI, Query, Header, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from dateutil.relativedelta import relativedelta

app = FastAPI(title="Hireform Career Gaps Detector")

class Experience(BaseModel):
    company: str
    role: str
    start_date: str  # format "YYYY-MM"
    end_date: str    # format "YYYY-MM"

class CV(BaseModel):
    experience: List[Experience]

def parse_date(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%Y-%m")
    except Exception:
        raise ValueError(f"Format invalide pour la date : {date_str}")

def detect_career_gaps(experiences: List[Experience], threshold_months: int):
    sorted_exp = sorted(experiences, key=lambda x: parse_date(x.start_date), reverse=True)
    gaps = []

    for i in range(len(sorted_exp) - 1):
        end_current = parse_date(sorted_exp[i].end_date)
        start_next = parse_date(sorted_exp[i + 1].start_date)

        diff = relativedelta(start_next, end_current)
        months_gap = diff.years * 12 + diff.months

        if months_gap > threshold_months:
            gaps.append({
                "start": sorted_exp[i].end_date,
                "end": sorted_exp[i + 1].start_date,
                "duration_months": months_gap,
                "description": f"Inactivité de {months_gap} mois entre {start_next.strftime('%B %Y')} et {end_current.strftime('%B %Y')}"
            })

    return gaps

@app.post("/analyze-gaps/")
def analyze_gaps(
    cv: CV,
    gap_threshold: int = Query(3, description="Seuil de détection en mois", alias="gap_threshold"),
    api_key: str = Header(..., alias="api-key")
):
    if not api_key.startswith("sk-"):
        raise HTTPException(status_code=401, detail="Clé API invalide")

    gaps = detect_career_gaps(cv.experience, gap_threshold)
    result = cv.dict()
    result["career_gaps"] = gaps
    return result
