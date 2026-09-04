"""
Extraction du texte réellement visible d'un article + détection de paywall.

Objectif : reproduire ce que verra le pipeline en production, PAS contourner les
paywalls. Pour une page en accès libre on renvoie le corps ; pour une page sous
abonnement on renvoie ce qui est public (titre, meta-description, chapô, encadré
type « This article in 1 minute » de Follow the Money) et on lève le drapeau
`paywalled`.

Pas de dépendance readability : bs4 + heuristiques suffisent pour du texte
d'article. On ne cherche pas la perfection typographique, juste un texte propre
et complet à passer au prompt.
"""

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .httputil import fetch

_BLOCK_TAGS = ("script", "style", "noscript", "form", "aside", "figure",
               "nav", "header", "footer", "svg", "button")

_PAYWALL_MARKERS = [
    "s'abonner", "abonnez-vous", "déjà abonné", "réservé aux abonnés",
    "article réservé", "poursuivre la lecture", "lecture réservée",
    "subscribe to read", "subscribe to continue", "already a subscriber",
    "this article is for subscribers", "for subscribers only", "sign in to read",
    "become a member", "create a free account to continue",
    "content included in subscription", "this content is included in subscription",
    "nur für abonnenten", "jetzt abonnieren", "weiterlesen mit",
    "contenuto riservato agli abbonati", "abbonati per leggere", "solo per abbonati",
]

# Encadré « This article in 1 minute » de ftm.eu — accès libre même sur article payant.
_FTM_TEASER_RE = re.compile(
    r"(this article in \d+ ?min-?ute?s?.*?)(?:\n\n|\Z)", re.I | re.S)


def _clean(txt: str) -> str:
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def _meta(soup: BeautifulSoup, *names) -> str:
    for name in names:
        el = (soup.find("meta", attrs={"name": name})
              or soup.find("meta", attrs={"property": name}))
        if el and el.get("content"):
            return el["content"].strip()
    return ""


def _json_ld_free_flag(soup: BeautifulSoup) -> bool | None:
    """Lit isAccessibleForFree dans le JSON-LD. None si absent."""
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in (data if isinstance(data, list) else [data]):
            if not isinstance(obj, dict):
                continue
            val = obj.get("isAccessibleForFree")
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.strip().lower() in ("true", "yes")
    return None


def _main_text(soup: BeautifulSoup) -> str:
    for tag in soup(list(_BLOCK_TAGS)):
        tag.decompose()

    candidates = []
    for sel in ("article", "main", '[itemprop="articleBody"]', ".article-body",
                ".article__body", ".post-content", ".entry-content", ".c-article",
                ".story-body", "#article-body"):
        candidates.extend(soup.select(sel))
    if not candidates and soup.body:
        candidates = [soup.body]

    best, best_len = "", 0
    for node in candidates:
        paras = [p.get_text(" ", strip=True) for p in node.find_all(["p", "h2", "h3", "li"])]
        paras = [p for p in paras if len(p) > 25]
        text = "\n\n".join(paras)
        if len(text) > best_len:
            best, best_len = text, len(text)
    return _clean(best)


def extract_article(url: str) -> dict:
    """
    Renvoie un dict :
      final_url, http_status, fetch_error,
      html_title, meta_description, site_name,
      text, text_len, paywalled, paywall_reason, free_flag
    Ne lève jamais.
    """
    out = {
        "final_url": url, "http_status": 0, "fetch_error": None,
        "html_title": "", "meta_description": "", "site_name": "",
        "text": "", "text_len": 0, "paywalled": False,
        "paywall_reason": None, "free_flag": None,
    }

    res = fetch(url, browser=True)
    out["final_url"] = res.final_url
    out["http_status"] = res.status
    if not res.ok:
        out["fetch_error"] = res.error or f"HTTP {res.status}"
        return out
    ctype = (res.content_type or "").lower()
    if "html" not in ctype and "xml" not in ctype and res.body[:15].lstrip()[:1] != b"<":
        out["fetch_error"] = f"contenu non-HTML ({ctype or 'type inconnu'})"
        return out

    html = res.text()
    soup = BeautifulSoup(html, "lxml")

    out["html_title"] = (soup.title.get_text(strip=True) if soup.title else "")
    out["meta_description"] = _meta(soup, "description", "og:description",
                                    "twitter:description")
    out["site_name"] = _meta(soup, "og:site_name") or urlparse(res.final_url).hostname or ""
    out["free_flag"] = _json_ld_free_flag(soup)

    body_text = _main_text(soup)
    low_html = html.lower()

    # --- détection paywall -------------------------------------------------
    reasons = []
    if out["free_flag"] is False:
        reasons.append("JSON-LD isAccessibleForFree=false")
    marker_hit = next((m for m in _PAYWALL_MARKERS if m in low_html), None)
    if marker_hit:
        reasons.append(f"marqueur « {marker_hit} »")
    # corps très court par rapport à la meta-description = probable troncature
    if body_text and out["meta_description"] and len(body_text) < 400 \
            and len(body_text) < 3 * len(out["meta_description"]):
        reasons.append("corps tronqué (plus court que 3x la meta-description)")

    if reasons:
        out["paywalled"] = True
        out["paywall_reason"] = " ; ".join(reasons)

    # --- cas particulier ftm.eu : encadré « This article in 1 minute » ----
    if "ftm.eu" in (urlparse(res.final_url).hostname or ""):
        full_plain = _clean(soup.get_text("\n", strip=True))
        m = _FTM_TEASER_RE.search(full_plain)
        if m:
            teaser = _clean(m.group(1))
            if len(teaser) > len(body_text):
                body_text = teaser
            out["paywalled"] = True
            out["paywall_reason"] = (out["paywall_reason"] or "") + \
                " ; encadré « This article in 1 minute » récupéré"

    # Si on n'a quasi rien mais une meta-description : la fournir comme secours,
    # le prompt appliquera la règle anti-invention.
    if len(body_text) < 200 and out["meta_description"]:
        body_text = (body_text + "\n\n" + out["meta_description"]).strip()
        if not out["paywalled"]:
            out["paywalled"] = True
            out["paywall_reason"] = "corps non extractible, seule la meta-description est disponible"

    out["text"] = body_text
    out["text_len"] = len(body_text)
    return out
