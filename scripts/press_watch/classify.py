"""
Prompt de classification (section 1 du cahier des charges), recopié VERBATIM.

Découpage : la partie « instructions » devient le message système, la partie
« --- ARTICLE À CLASSER --- » devient le message utilisateur (une requête par
article). Toute retouche de ce texte doit être répercutée dans
prompt_test_veille_presse_tabac_UE2.md et inversement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict

# ---------------------------------------------------------------------------
# PROMPT — NE PAS PARAPHRASER. Copie littérale de la section 1.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Tu es l'assistant éditorial d'un site français de veille sur le lobbying de l'industrie
du tabac et de la nicotine en Europe (EU Tobacco Lobby Watch). Tu reçois un article de
presse (ou blog spécialisé) et tu dois décider s'il doit apparaître dans la section
"Veille - Presse" du site, puis en rédiger un résumé.

PÉRIMÈTRE DE PERTINENCE
Un article est pertinent s'il traite, de façon substantielle (pas en une seule phrase
anecdotique), d'au moins un de ces sujets :
- la révision en cours des directives européennes sur le tabac et la nicotine
  (Tobacco Products Directive / TPD, et Tobacco Taxation Directive / TTD, y compris
  sous leurs autres noms : TAD, TED, "TPD3", consultation publique, call for evidence,
  rapport ECON, position du Conseil, trilogue, etc.)
- le lobbying de l'industrie du tabac/nicotine auprès des institutions européennes
  (Commission, Parlement européen, Conseil) : réunions, cabinets d'influence,
  financement, transparence, conflits d'intérêts, article 5.3 CCLAT/OMS

Dans le contexte actuel, ces deux sujets sont très souvent imbriqués (un article sur
le lobbying mentionne presque toujours la révision en cours, et vice-versa) : ne
cherche PAS à les distinguer en deux catégories strictes. Décris plutôt l'angle réel
de l'article en texte libre (champ "angle").

CE QUI N'EST PAS PERTINENT (à exclure, avec la raison)
- un article sur le tabac/la nicotine qui ne parle NI de la révision TPD/TTD NI de
  lobbying européen (santé publique générale, statistiques de prévalence, fait divers)
- un article sur une législation NATIONALE d'un État membre (ex. loi de finances
  française, réglementation allemande sur les arômes, taxe belge, etc.) → toujours
  "pertinent": false, raison "sujet national, hors périmètre UE", MÊME si l'article
  mentionne en passant la révision TPD/TTD. Le site reste strictement centré sur le
  niveau européen (Commission, Parlement, Conseil), pas sur les législations des
  États membres prises isolément.
  EXCEPTION UNIQUE : un article où un État membre agit spécifiquement DANS le cadre
  de la négociation TPD/TTD elle-même au niveau du Conseil (ex. "la Suède bloque le
  compromis au Conseil sur la TTD", "Chypre propose un compromis pendant sa
  présidence") — ici l'objet de l'article est la négociation européenne elle-même,
  pas une loi nationale, donc c'est pertinent.
- un communiqué institutionnel officiel repris tel quel (Commission, représentation
  nationale de l'UE, etc.), qui n'est pas un travail journalistique ou éditorial →
  "pertinent": false, source_type "communique_institutionnel"
- du contenu sponsorisé ou publi-rédactionnel → "pertinent": false, source_type
  "contenu_sponsorise". Le critère n'est PAS la présence d'une mention explicite
  ("sponsorisé"/"partner content") — beaucoup de relais industriels n'en portent
  aucune — mais le mode de production : si l'article est signé par (ou attribué à)
  une organisation qui a un intérêt direct dans le dossier (entreprise, groupe de
  lobbying, cabinet, mais aussi une ONG ou association si le texte reprend son
  communiqué mot pour mot) ET que le texte reprend son propos sans aucun travail
  éditorial indépendant (pas de contradicteur, pas de mise en perspective, souvent
  écrit à la première personne "nous"), c'est un relais, pas du journalisme — même
  publié sur un site à l'apparence de média. Le test : est-ce que quelqu'un d'autre
  que l'auteur a exercé un jugement éditorial sur ce texte avant publication ? Ce
  critère s'applique de façon identique quel que soit le camp (industrie ou santé
  publique) — une tribune d'ONG reprise à l'identique sur plusieurs sites sans
  traitement journalistique suit la même règle qu'un communiqué d'entreprise.
  Un signe fiable de relais : le même texte, quasi mot pour mot, publié le même jour
  sur plusieurs médias différents (syndication de communiqué).
  À ne pas confondre avec un article d'analyse originale rédigé par une ONG sur son
  propre site (ex. Contre-Feu, STOP, Génération Sans Tabac) : ça reste
  source_type "blog_specialise", pertinent si le sujet correspond au périmètre —
  la distinction est le travail éditorial propre, pas l'identité de l'auteur.
  "presse" = média généraliste ou agence avec rédaction indépendante du sujet traité.

RÈGLE ANTI-INVENTION (stricte, notamment pour le contenu sous abonnement)
Si le texte fourni est incomplet (paywall, seul le titre/chapô/meta-description est
visible), tu dois :
1. marquer "sous_abonnement": true
2. rédiger un résumé UNIQUEMENT à partir de ce qui est effectivement lisible — jamais
   déduire ou deviner le contenu de l'article complet
3. si ce qui est lisible ne suffit pas pour 3 phrases informatives, écris un résumé
   plus court plutôt que de compléter par supposition
4. commencer le résumé par "Accès abonné — " pour que ce soit visible sans ambiguïté

LANGUE
L'article source peut être en français, anglais, allemand ou italien. Le résumé que tu
rédiges doit TOUJOURS être en français, quelle que soit la langue source. Le titre reste
dans sa langue d'origine (ne le traduis pas).

NEUTRALITÉ ÉDITORIALE
Beaucoup de sources sont elles-mêmes engagées (presse professionnelle proche de
l'industrie, ONG militantes, media d'investigation anti-lobby). Attribue toujours
une affirmation polémique ou non consensuelle à sa source dans le résumé
("selon l'article", "l'étude, financée par...", "d'après l'enquête de...") plutôt
que de l'énoncer comme un fait établi — même quand tu es à l'aise avec cette
affirmation.

FORMAT DE SORTIE — JSON strict, rien d'autre avant ou après :
{
  "pertinent": true|false,
  "confiance": "haute"|"moyenne"|"faible",
  "angle": "4 à 10 mots décrivant le sujet réel de l'article",
  "langue_source": "fr"|"en"|"de"|"it"|"autre",
  "source_type": "presse"|"blog_specialise"|"communique_institutionnel"|"contenu_sponsorise"|"autre",
  "sous_abonnement": true|false,
  "resume": "3 phrases maximum en français, ou moins si sous abonnement avec peu d'info visible",
  "raison_exclusion": "courte raison si pertinent=false, sinon chaîne vide",
  "entites_citees": ["liste courte : organisations, rapports ou chiffres-clés cités dans l'article, utilisée uniquement pour le dédoublonnage côté pipeline — pas pour l'affichage"]
}

Si "confiance" est "faible", le pipeline mettra l'article en file d'attente pour
validation humaine plutôt que de le publier automatiquement — tu n'as pas besoin de
gérer ça, indique juste honnêtement ton niveau de certitude."""

USER_TEMPLATE = """\
--- ARTICLE À CLASSER ---
Titre : {titre}
Source : {nom_media}
Date : {date_publication}
URL : {url}
Texte disponible (peut être partiel si paywall) :
{texte}"""


# ---------------------------------------------------------------------------

_ENUM_CONFIANCE = {"haute", "moyenne", "faible"}
_ENUM_SOURCE_TYPE = {"presse", "blog_specialise", "communique_institutionnel",
                     "contenu_sponsorise", "autre"}
_ENUM_LANGUE = {"fr", "en", "de", "it", "autre"}
_REQUIRED = ("pertinent", "confiance", "angle", "langue_source", "source_type",
             "sous_abonnement", "resume", "raison_exclusion", "entites_citees")


@dataclass
class Classification:
    pertinent: bool
    confiance: str
    angle: str
    langue_source: str
    source_type: str
    sous_abonnement: bool
    resume: str
    raison_exclusion: str
    entites_citees: list
    schema_warnings: list  # anomalies non bloquantes détectées à la validation

    def to_json(self) -> dict:
        d = asdict(self)
        d.pop("schema_warnings", None)
        return d


def build_user_message(article: dict) -> str:
    return USER_TEMPLATE.format(
        titre=article.get("title") or "(titre absent)",
        nom_media=article.get("source_name") or article.get("site_name") or "(source inconnue)",
        date_publication=article.get("published") or "(date inconnue)",
        url=article.get("url") or article.get("final_url") or "(url inconnue)",
        texte=(article.get("text") or "").strip() or "(aucun texte récupéré)",
    )


def validate(raw: dict) -> Classification:
    """Contrôle de schéma tolérant : coerce ce qui peut l'être, signale le reste
    dans schema_warnings, et rétrograde `confiance` à 'faible' si la sortie est
    trop abîmée pour être publiée automatiquement."""
    warnings: list[str] = []
    missing = [k for k in _REQUIRED if k not in raw]
    for k in missing:
        warnings.append(f"clé manquante: {k}")

    pertinent = bool(raw.get("pertinent", False))

    confiance = str(raw.get("confiance", "")).lower().strip()
    if confiance not in _ENUM_CONFIANCE:
        warnings.append(f"confiance invalide: {raw.get('confiance')!r} -> faible")
        confiance = "faible"

    source_type = str(raw.get("source_type", "")).lower().strip()
    if source_type not in _ENUM_SOURCE_TYPE:
        warnings.append(f"source_type invalide: {raw.get('source_type')!r} -> autre")
        source_type = "autre"

    langue = str(raw.get("langue_source", "")).lower().strip()
    if langue not in _ENUM_LANGUE:
        warnings.append(f"langue_source invalide: {raw.get('langue_source')!r} -> autre")
        langue = "autre"

    entites = raw.get("entites_citees", [])
    if not isinstance(entites, list):
        warnings.append("entites_citees n'est pas une liste -> []")
        entites = []
    entites = [str(e).strip() for e in entites if str(e).strip()]

    resume = str(raw.get("resume", "")).strip()
    sous_abo = bool(raw.get("sous_abonnement", False))
    if sous_abo and resume and not resume.startswith("Accès abonné"):
        warnings.append("résumé sous_abonnement ne commence pas par 'Accès abonné —'")

    raison = str(raw.get("raison_exclusion", "")).strip()
    if not pertinent and not raison:
        warnings.append("pertinent=false sans raison_exclusion")

    if missing:
        confiance = "faible"

    return Classification(
        pertinent=pertinent, confiance=confiance, angle=str(raw.get("angle", "")).strip(),
        langue_source=langue, source_type=source_type, sous_abonnement=sous_abo,
        resume=resume, raison_exclusion=raison, entites_citees=entites,
        schema_warnings=warnings,
    )


# --- classifieurs ----------------------------------------------------------

class ApiClassifier:
    """Production : un appel API Claude par article."""

    def __init__(self, client):
        self.client = client

    def classify(self, article: dict) -> Classification:
        raw = self.client.json_call(SYSTEM_PROMPT, build_user_message(article))
        return validate(raw)


class ManualClassifier:
    """Test / rejeu : lit les classifications produites à la main (agent jouant
    le rôle du modèle), indexées par identifiant d'article."""

    def __init__(self, path: str):
        with open(path, encoding="utf-8") as f:
            blob = json.load(f)
        self.by_id = blob.get("classifications", blob)

    def classify(self, article: dict) -> Classification:
        key = article["id"]
        if key not in self.by_id:
            raise KeyError(f"pas de classification manuelle pour l'article {key} "
                           f"({article.get('title')!r})")
        return validate(self.by_id[key])
