from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import openai
import json

app = FastAPI(title="Audit RH – Analyse de biais linguistiques")

class DescriptionPayload(BaseModel):
    text: str

@app.post("/audit-bias/")
async def audit_bias(
    payload: DescriptionPayload,
    api_key: str = Header(..., alias="api-key")
):
    if not api_key.startswith("sk-"):
        raise HTTPException(status_code=401, detail="Clé API invalide ou manquante")

    openai.api_key = api_key

    # Prompt expert conforme au droit français et aux bonnes pratiques
    system_prompt = (
        "Tu es un assistant expert en rédaction RH non discriminante. Ton rôle est d’auditer des offres d’emploi "
        "afin de détecter automatiquement tout langage potentiellement biaisé, discriminant ou excluant, selon les critères "
        "juridiques et éthiques du droit français.\n\n"
        "Tu dois :\n"
        "1. Analyser le contenu de l’offre et signaler tout élément sensible.\n"
        "2. Identifier les tournures ou formulations problématiques (langage genré, stéréotypé, discriminant, exclusions implicites).\n"
        "3. Proposer des reformulations neutres, inclusives et conformes à la loi.\n\n"
        "Critères discriminants à détecter :\n"
        "- Le genre (ex. « homme dynamique », « développeur passionné » sans mention H/F ou neutre)\n"
        "- L’origine, la nationalité ou l’accent (ex. « natif allemand », « accent compréhensible »)\n"
        "- L’âge ou des stéréotypes d’âge (ex. « jeune équipe », « expérience senior obligatoire »)\n"
        "- La religion, opinions politiques, orientation sexuelle, situation familiale\n"
        "- La localisation ou le temps de trajet du candidat (ex. « doit habiter proche de… »)\n"
        "- Les formulations excluantes ou élitistes (ex. « profil parfait », « vous vous imposez facilement »)\n"
        "- Les adjectifs à connotation genrée ou non inclusive (ex. « leader né », « forte personnalité »)\n\n"
        "Style de sortie :\n"
        "Renvoie un JSON structuré au format suivant :\n"
        "{\n"
        "  \"impact_estimate\": float,\n"
        "  \"terms_found\": [{ \"term\": \"...\", \"reason\": \"...\", \"location\": \"...\" }],\n"
        "  \"suggestions\": [{ \"original\": \"...\", \"replacement\": \"...\", \"note\": \"...\" }]\n"
        "}\n\n"
        "Reformule toujours sans point médian (ex. pas de « développeur·euse »). "
        "Utilise plutôt des formes épicènes ou des doublets complets : « développeur ou développeuse », « candidat / candidate ».\n\n"
        "Ne commente pas. Ne parle pas de toi. Fournis uniquement le JSON demandé."
    )

    user_prompt = (
        "Analyse le texte suivant et détecte tout terme ou formulation potentiellement biaisé ou non inclusif. "
        "Renvoie uniquement le JSON structuré comme demandé.\n\n"
        f"Texte de l’offre :\n{payload.text}"
    )

    response = openai.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    # Extraction du contenu JSON renvoyé par le modèle
    content = response.choices[0].message.content
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Réponse OpenAI non valide : JSON mal formé")

    return result
