"""
Prompt de synthèse du jour (section 7 du cahier des charges), recopié VERBATIM.

Appel séparé, une fois par exécution, APRÈS classification et dédoublonnage.
N'utilise que les sorties déjà produites (résumé, angle, entités) — jamais les
textes complets — donc coût quasi nul.

Cas liste vide : aucun appel, texte par défaut en dur (section 7).
"""

from __future__ import annotations

import json

DEFAULT_EMPTY_TEXT = (
    "Pas d'actualité particulière aujourd'hui sur la révision TPD/TTD ou le lobbying "
    "du tabac et de la nicotine à Bruxelles."
)

SYSTEM_PROMPT = """\
Tu rédiges la phrase de synthèse quotidienne d'un site de veille sur la révision
des directives européennes TPD/TTD et le lobbying du tabac/nicotine à Bruxelles.
Tu reçois la liste des articles retenus aujourd'hui (déjà résumés et classés
pertinents) et tu dois produire UNE phrase de synthèse, visible sans avoir à
ouvrir la section — donc elle doit donner l'essentiel d'un coup d'œil.

RÈGLES DE HIÉRARCHISATION
- Privilégie un fait concret et daté (un vote, un blocage au Conseil, une fuite de
  document, une nomination, une décision d'un médiateur ou d'une juridiction) par
  rapport à une tribune d'opinion, une déclaration répétée ou un rappel de
  calendrier déjà connu.
- Si tous les articles du jour (ou la majorité) partagent au moins 3 entités
  citées en commun, c'est le même événement couvert par plusieurs médias : dis-le
  clairement plutôt que de faire semblant que ce sont des informations séparées.
- Si plusieurs sujets distincts et sans lien réel entre eux sont présents,
  choisis le plus significatif selon le critère ci-dessus comme "information
  principale", et mentionne les autres en une incise courte — ne force jamais un
  lien narratif qui n'existe pas entre des sujets décorrélés.
- Si rien ne se détache clairement (mentions mineures, redites, rien de nouveau),
  dis-le honnêtement plutôt que de gonfler artificiellement l'importance d'un
  article pour remplir la case.
- Ne mentionne jamais un fait qui ne figure pas explicitement dans les résumés
  fournis — tu synthétises, tu n'inventes pas de lien de causalité.
- Si un résumé de la veille est fourni et que rien de nouveau n'est arrivé
  depuis, tu peux le dire ("toujours pas d'avancée depuis hier sur ce dossier").

FORMAT DE SORTIE — JSON strict :
{
  "type": "evenement_unique"|"plusieurs_sujets"|"rien_de_marquant",
  "resume_du_jour": "1 à 2 phrases maximum, en français, ton factuel",
  "articles_source": ["titres des articles utilisés pour construire ce résumé"]
}"""

USER_TEMPLATE = """\
--- ARTICLES RETENUS AUJOURD'HUI ---
{liste_json_articles_du_jour}

--- RÉSUMÉ DE LA VEILLE (optionnel, pour éviter la redite) ---
{resume_hier}"""


def build_user_message(day_articles: list[dict], resume_hier: str | None) -> str:
    payload = [
        {
            "titre": a.get("title"),
            "source": a.get("source_name") or a.get("site_name"),
            "angle": a.get("angle"),
            "resume": a.get("resume"),
            "sous_abonnement": a.get("sous_abonnement", False),
            "entites_citees": a.get("entites_citees", []),
        }
        for a in day_articles
    ]
    return USER_TEMPLATE.format(
        liste_json_articles_du_jour=json.dumps(payload, ensure_ascii=False, indent=2),
        resume_hier=(resume_hier or "(aucun)"),
    )


def _validate(raw: dict, day_articles: list[dict]) -> dict:
    t = str(raw.get("type", "")).strip()
    if t not in {"evenement_unique", "plusieurs_sujets", "rien_de_marquant"}:
        t = "plusieurs_sujets" if len(day_articles) > 1 else "evenement_unique"
    return {
        "type": t,
        "resume_du_jour": str(raw.get("resume_du_jour", "")).strip(),
        "articles_source": [str(x) for x in raw.get("articles_source", []) if str(x).strip()],
    }


class ApiSynthesizer:
    def __init__(self, client):
        self.client = client

    def synthesize(self, day_articles: list[dict], resume_hier: str | None = None) -> dict:
        if not day_articles:
            return {"type": "rien_de_marquant", "resume_du_jour": DEFAULT_EMPTY_TEXT,
                    "articles_source": [], "api_called": False}
        raw = self.client.json_call(
            SYSTEM_PROMPT, build_user_message(day_articles, resume_hier))
        out = _validate(raw, day_articles)
        out["api_called"] = True
        return out


class ManualSynthesizer:
    """Test / rejeu : synthèses produites à la main, indexées par date ISO."""

    def __init__(self, path: str):
        with open(path, encoding="utf-8") as f:
            blob = json.load(f)
        self.by_date = blob.get("synthesis", blob)

    def synthesize(self, day_articles: list[dict], resume_hier: str | None = None,
                   *, day: str) -> dict:
        if not day_articles:
            return {"type": "rien_de_marquant", "resume_du_jour": DEFAULT_EMPTY_TEXT,
                    "articles_source": [], "api_called": False}
        if day not in self.by_date:
            raise KeyError(f"pas de synthèse manuelle pour le {day}")
        out = _validate(self.by_date[day], day_articles)
        out["api_called"] = False
        return out
