"""
Wrapper minimal autour de l'API Messages d'Anthropic.

Clé lue dans l'environnement : ANTHROPIC_API_KEY (à fournir en secret GitHub
Actions pour le workflow nocturne — jamais commitée).

Le paquet `anthropic` est importé paresseusement : le pipeline peut tourner en
mode `--no-llm` (test / rejeu manuel) sans que le paquet soit installé.
"""

import json
import os
import re
import time

MODEL = "claude-sonnet-5"          # section 1 du cahier des charges
MAX_TOKENS = 1200
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.S)


class LLMError(RuntimeError):
    pass


class AnthropicClient:
    def __init__(self, model: str = MODEL, api_key: str | None = None):
        self.model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY absente de l'environnement. "
                "Utiliser --no-llm pour un rejeu manuel, ou définir la clé.")
        try:
            import anthropic  # noqa: WPS433
        except ImportError as exc:
            raise LLMError(
                "Le paquet 'anthropic' n'est pas installé (pip install anthropic).") from exc
        self._client = anthropic.Anthropic(api_key=self._api_key)

    def json_call(self, system: str, user: str, *, max_tokens: int = MAX_TOKENS,
                  retries: int = 2) -> dict:
        """Appel en mode « JSON only ». Renvoie le dict parsé.

        Robustesse : si le modèle enrobe le JSON (fences, phrase parasite), on
        récupère le premier bloc {...}. En cas d'échec de parsing, une relance
        avec consigne renforcée, puis LLMError.
        """
        last_err = None
        messages = [{"role": "user", "content": user}]
        for attempt in range(retries + 1):
            try:
                resp = self._client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=messages,
                )
            except Exception as exc:  # erreurs réseau / API / rate limit
                last_err = f"appel API échoué : {exc}"
                time.sleep(2 * (attempt + 1))
                continue

            text = "".join(
                block.text for block in resp.content if getattr(block, "type", "") == "text"
            ).strip()
            parsed = _try_parse_json(text)
            if parsed is not None:
                return parsed

            last_err = f"réponse non JSON : {text[:200]!r}"
            messages = [
                {"role": "user", "content": user},
                {"role": "assistant", "content": text},
                {"role": "user", "content":
                    "Ta réponse doit être uniquement le JSON demandé, sans texte "
                    "ni balise de code autour. Renvoie-le à nouveau."},
            ]

        raise LLMError(last_err or "échec inconnu")


def _try_parse_json(text: str) -> dict | None:
    if not text:
        return None
    for candidate in (text, _strip_fences(text)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    m = _JSON_BLOCK_RE.search(text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()
