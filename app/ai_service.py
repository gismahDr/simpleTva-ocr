import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_client = None

OPENROUTER_MODEL = "google/gemini-2.5-flash"


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
    return _client


INVOICE_PROMPT = """Tu es un moteur d'extraction de données de factures.

Ta mission est d'extraire les informations présentes dans un texte OCR de facture.

IMPORTANTES RÈGLES :

- Retourne UNIQUEMENT un JSON valide.
- Ne retourne aucun texte, aucune explication, aucun markdown.
- Si une information est absente, retourne null.
- Ne jamais inventer une valeur.
- Si plusieurs valeurs sont possibles, choisir celle ayant le plus de probabilité.
- Les montants doivent être des nombres.
- Les dates doivent être au format YYYY-MM-DD lorsque possible.
- Les décimales utilisent le point.
- Les quantités sont numériques.
- Les prix unitaires sont numériques.
- Les montants TTC doivent correspondre au total final de la facture.
- Si la devise est absente, retourner null.

Le JSON doit respecter EXACTEMENT ce schéma :

{
  "supplier": {
    "name": null,
    "ice": null,
    "if": null,
    "rc": null,
    "patente": null,
    "address": null,
    "phone": null,
    "email": null
  },

  "customer": {
    "name": null,
    "ice": null,
    "if": null,
    "address": null
  },

  "invoice": {
    "number": null,
    "date": null,
    "due_date": null,
    "currency": null
  },

  "totals": {
    "subtotal": null,
    "discount": null,
    "vat": null,
    "total": null
  },

  "items": [
    {
      "description": null,
      "quantity": null,
      "unit": null,
      "unit_price": null,
      "vat_rate": null,
      "total": null
    }
  ]
}

Voici le texte OCR :

"""


def extract_invoice_with_ai(raw_text: str) -> dict:
    from fastapi import HTTPException
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": INVOICE_PROMPT},
                {"role": "user", "content": raw_text},
            ],
            temperature=0,
            max_tokens=4000,
        )
        text = response.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenRouter API error: {e}")

    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502, detail=f"Invalid JSON from AI: {text[:200]}"
        )
