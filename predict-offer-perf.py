from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.security import APIKeyHeader
import json
from openai import OpenAI
from typing import Optional

app = FastAPI(title="Hireform Job Ad Performance Predictor")

# On récupère la clé OpenAI depuis le header "api-key"
api_key_header = APIKeyHeader(name="api-key", auto_error=True)

@app.post("/predict-offer-perf/")
async def predict_offer_perf(
    request: Request,
    openai_key: str = Depends(api_key_header),
    target_lang: Optional[str] = Header("EN", alias="target-lang")
):
    # Validation basique du format de la clé
    if not openai_key.startswith("sk-"):
        raise HTTPException(status_code=401, detail="OpenAI API key invalide")

    # Lecture dynamique du JSON de l'annonce
    try:
        ad = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalide")

    # Instanciation du client OpenAI avec la clé reçue
    client = OpenAI(api_key=openai_key)

    # Prompt exactement comme souhaité
    prompt = f"""
Vous êtes un expert en marketing RH et publicité digitale, formé sur des données Indeed et LinkedIn.
Analysez l'annonce ci-dessous et renvoyez un objet JSON avec :
1. score (0–100) : optimisation globale basée sur les meilleures pratiques PPC et recrutement.
2. category : "Faible", "Moyen", "Bon" ou "Excellent" selon le score.
3. click_probability : probabilité estimée de clic (float 0–1).
4. apply_probability : probabilité estimée de candidature (float 0–1).
5. suggestions : {{
     "title": string,       # comment améliorer le titre
     "keywords": [string],  # mots-clés à ajouter ou renforcer
     "structure": string    # conseils sur la mise en forme (sections, bullet points…)
}}

**Annonce à analyser** (JSON) :
{json.dumps(ad, ensure_ascii=False, indent=2)}

**Règles à suivre** :
- Basez-vous sur la psychologie du candidat : clarté, bénéfices, CTA explicite.  [oai_citation:6‡Level Agency](https://www.level.agency/perspectives/use-chatgpt-to-write-crazy-effective-google-ads-copy/?utm_source=chatgpt.com)  
- Utilisez des KPI standards (CTR, conversion) pour calculer click_probability et apply_probability.  [oai_citation:7‡AI pour le Travail](https://www.aiforwork.co/prompt-articles/chatgpt-prompt-paid-social-media-specialist-marketing-create-an-ad-performance-analysis-document?utm_source=chatgpt.com)  
- Proposez un titre optimisé de 5 à 8 mots maximum.  [oai_citation:8‡nurturebox.ai](https://www.nurturebox.ai/blog/the-ultimate-guide-to-posting-jobs-chatgpt-prompts?utm_source=chatgpt.com)  
- Suggérez 3–5 mots-clés métiers et soft skills adaptés.  [oai_citation:9‡occupop.com](https://www.occupop.com/chatgpt-prompts-for-recruitment?utm_source=chatgpt.com)  
- Formatez la structure en 3 sections : Contexte, Responsabilités, Avantages.  [oai_citation:10‡Blog PromoNavigator](https://blog.promonavigator.com/chatgpt-prompts-for-ppc-ads/?utm_source=chatgpt.com)  
- Répondez uniquement en JSON, sans autre texte.
"""

    # Appel à l’API GPT-4.1
    try:
        response = await client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Vous êtes un assistant expert en marketing RH."},
                {"role": "user", "content": prompt}
            ]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur OpenAI : {e}")

    # Retour direct du JSON généré
    content = response.choices[0].message["content"]
    return json.loads(content)
