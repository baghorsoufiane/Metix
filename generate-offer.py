import uuid
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
import openai

app = FastAPI()

# Définition de l'en-tête attendu pour la clé API
api_key_header = APIKeyHeader(name="X-OpenAI-Key", auto_error=True)

# Exemple de json
"""- **Corps de la requête (JSON)** :
{
  "title": "Développeur Python",
  "location": "Paris",
  "employment_type": "CDI",
  "salary": 60000,
  "company_name": "Tech Innovators",
  "company_website": "https://www.techinnovators.com",
  "company_logo": "https://www.techinnovators.com/logo.png",
  "valid_through": "2025-05-31"
}

"""

# Modèle de données pour l'entrée
class JobInput(BaseModel):
    title: str
    location: str
    employment_type: Optional[str] = "CDI"
    salary: Optional[float] = None
    company_name: str
    company_website: Optional[str] = None
    company_logo: Optional[str] = None
    valid_through: Optional[str] = None

# Fonction pour générer la description de l'offre d'emploi
def generate_job_description(job: JobInput, api_key: str) -> str:
    prompt = (
        f"Rédige une offre d'emploi complète pour le poste suivant :\n"
        f"Titre : {job.title}\n"
        f"Lieu : {job.location}\n"
        f"Type de contrat : {job.employment_type}\n"
        f"Salaire : {job.salary if job.salary else 'Non spécifié'}\n"
        f"Entreprise : {job.company_name}\n"
        f"Site web : {job.company_website if job.company_website else 'Non spécifié'}\n"
        f"Logo : {job.company_logo if job.company_logo else 'Non spécifié'}\n"
        f"Date de validité : {job.valid_through if job.valid_through else 'Non spécifiée'}\n\n"
        f"L'offre doit inclure une description du poste, les responsabilités, les qualifications requises et les avantages offerts."
    )

    try:
        openai.api_key = api_key
        response = openai.ChatCompletion.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Tu es un assistant RH expert en rédaction d'offres d'emploi."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint pour générer l'offre d'emploi
@app.post("/generate-offer")
async def generate_offer(job: JobInput, api_key: str = Depends(api_key_header)):
    description = generate_job_description(job, api_key)

    job_id = str(uuid.uuid4())
    today = date.today().isoformat()

    job_posting = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": job.title,
        "description": description,
        "identifier": {
            "@type": "PropertyValue",
            "name": job.company_name,
            "value": job_id
        },
        "datePosted": today,
        "validThrough": job.valid_through,
        "employmentType": job.employment_type,
        "hiringOrganization": {
            "@type": "Organization",
            "name": job.company_name,
            "sameAs": job.company_website,
            "logo": job.company_logo
        },
        "jobLocation": {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": job.location,
                "addressCountry": "FR"
            }
        },
        "baseSalary": {
            "@type": "MonetaryAmount",
            "currency": "EUR",
            "value": {
                "@type": "QuantitativeValue",
                "value": job.salary,
                "unitText": "YEAR"
            }
        } if job.salary else None
    }

    # Suppression des champs avec des valeurs None
    job_posting = {k: v for k, v in job_posting.items() if v is not None}

    return job_posting
