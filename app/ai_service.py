import os
import json
import time
import threading
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_call_count = 0
_call_lock = threading.Lock()

# ponytail: clients lazy-init, un par provider. thread-safe round-robin.
_gemini_client = None
_openrouter_client = None
_groq_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        _gemini_client = OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=api_key,
            timeout=30.0,
        )
    return _gemini_client


def _get_openrouter_client():
    global _openrouter_client
    if _openrouter_client is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        _openrouter_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=30.0,
        )
    return _openrouter_client


def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set")
        _groq_client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
            timeout=30.0,
        )
    return _groq_client


# ponytail: wrapper g4f -> meme interface que OpenAI SDK.
class _G4FWrapper:
    """Enrobe g4f.Client pour matcher l'interface client.chat.completions.create()."""

    def __init__(self, provider):
        self._provider = provider

    @property
    def chat(self):
        return _G4FChat(self._provider)


class _G4FChat:
    def __init__(self, provider):
        self._provider = provider

    @property
    def completions(self):
        return _G4FCompletions(self._provider)


class _G4FCompletions:
    def __init__(self, provider):
        self._provider = provider

    def create(self, model, messages, temperature=0, max_tokens=4000):
        import g4f
        client = g4f.Client(provider=self._provider)
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return resp


def _get_g4f_groq_client():
    import g4f
    return _G4FWrapper(g4f.Provider.Groq)


# ponytail: ordre = cle reelle d'abord, puis fallbacks g4f gratuits.
PROVIDERS = [
    {"name": "Groq", "client_fn": _get_groq_client, "model": "llama-3.3-70b-versatile"},
    {"name": "G4F-Groq", "client_fn": _get_g4f_groq_client, "model": "llama-3.3-70b-versatile"},
    {"name": "OpenRouter", "client_fn": _get_openrouter_client, "model": "google/gemma-4-31b-it:free"},
]

API_DELAY_SECONDS = 5


def _next_provider():
    global _call_count
    with _call_lock:
        provider = PROVIDERS[_call_count % len(PROVIDERS)]
        _call_count += 1
    return provider


INVOICE_PROMPT = """Tu es un moteur d'extraction de données de factures.

Ta mission est d'extraire les informations présentes dans un texte OCR de facture.

IMPORTANTES RÈGLES :

- Retourne UNIQUEMENT un JSON valide.
- Ne retourne aucun texte, aucune explication, aucun markdown.
- Si une information est absente, retourne null.
- Ne jamais inventer une valeur.
- Si plusieurs valeurs sont possibles, choisir celle ayant le plus de probabilité.
- Les montants doivent être des nombres.
- Les dates doivent être au format DD/MM/YYYY lorsque possible.
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
    "tva": null,
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


_RATE_LIMIT_PATTERNS = ("429", "rate limit", "quota", "insufficient_quota", "too many requests", "exceeded")
_TIMEOUT_PATTERNS = ("timeout", "timed out", "deadline exceeded", "connection")


def _is_rate_limit_error(err_msg: str) -> bool:
    lower = err_msg.lower()
    return any(p in lower for p in _RATE_LIMIT_PATTERNS)


def _is_timeout_error(err_msg: str) -> bool:
    lower = err_msg.lower()
    return any(p in lower for p in _TIMEOUT_PATTERNS)


def extract_invoice_with_ai(raw_text: str) -> dict:
    from fastapi import HTTPException

    last_error = None
    for _ in range(len(PROVIDERS)):
        provider = _next_provider()

        try:
            client = provider["client_fn"]()
        except RuntimeError as e:
            print(f"[AI] {provider['name']} skip: {e}")
            last_error = e
            continue

        model = provider["model"]
        print(f"[AI] Appel via {provider['name']} (model: {model})")

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": INVOICE_PROMPT},
                    {"role": "user", "content": raw_text},
                ],
                temperature=0,
                max_tokens=4000,
            )
            text = response.choices[0].message.content.strip()
            print(f"[AI] {provider['name']} OK, reponse recue ({len(text)} chars)")
        except Exception as e:
            err_msg = str(e)
            print(f"[AI] {provider['name']} ERREUR: {err_msg[:200]}")
            if _is_rate_limit_error(err_msg):
                print(f"[AI] {provider['name']} rate limit/quota atteint, bascule au provider suivant...")
                last_error = e
                continue
            if _is_timeout_error(err_msg):
                print(f"[AI] {provider['name']} timeout, bascule au provider suivant...")
                last_error = e
                continue
            raise HTTPException(status_code=502, detail=f"{provider['name']} API error: {e}")

        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            print(f"[AI] {provider['name']} JSON invalide: {text[:200]}")
            raise HTTPException(
                status_code=502,
                detail=f"Invalid JSON from {provider['name']}: {text[:200]}",
            )

    raise HTTPException(
        status_code=502,
        detail=f"Tous les providers ont atteint leur quota. Derniere erreur: {last_error}",
    )


def extract_invoice_with_ai_delayed(raw_text: str) -> dict:
    """Appelle l'AI, retourne le resultat immediatement, puis attend 30s en arriere-plan."""
    result = extract_invoice_with_ai(raw_text)

    def _background_delay():
        print(f"[AI] Pause de {API_DELAY_SECONDS}s avant le prochain appel...")
        time.sleep(API_DELAY_SECONDS)
        print(f"[AI] Pause terminee, prochain appel autorise.")

    threading.Thread(target=_background_delay, daemon=True).start()
    return result
