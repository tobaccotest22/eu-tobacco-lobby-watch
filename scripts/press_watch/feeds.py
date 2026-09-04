"""
Récupération et parsing des flux RSS 2.0 et Atom (stdlib uniquement).

On ne dépend pas de feedparser : les flux visés (Google News RSS, WordPress,
Atom classique) sont couverts par un parsing ElementTree tolérant.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from .httputil import fetch

_ATOM = "{http://www.w3.org/2005/Atom}"
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class FeedEntry:
    title: str
    link: str
    summary: str = ""
    published: date | None = None
    source_name: str = ""          # média d'origine (Google News le fournit)
    source_url: str = ""           # domaine du média d'origine si connu
    feed_lang: str = ""
    feed_label: str = ""           # d'où vient l'entrée (nom du flux / requête)
    raw_link_is_google: bool = False
    extra: dict = field(default_factory=dict)


def _strip_html(s: str) -> str:
    if not s:
        return ""
    s = _TAG_RE.sub(" ", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
           .replace("&#39;", "'").replace("&apos;", "'").replace("&lt;", "<").replace("&gt;", ">"))
    return _WS_RE.sub(" ", s).strip()


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    raw = raw.strip()
    # RFC 822 (RSS) : "Wed, 02 Sep 2026 10:30:00 GMT"
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            return dt.astimezone(timezone.utc).date() if dt.tzinfo else dt.date()
    except (TypeError, ValueError):
        pass
    # ISO 8601 (Atom) : "2026-09-02T10:30:00Z"
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw.replace("Z", "+0000") if fmt.endswith("%z") else raw, fmt)
            return dt.date()
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse_feed(xml_bytes: bytes, *, feed_lang: str = "", feed_label: str = "") -> list[FeedEntry]:
    entries: list[FeedEntry] = []
    # Certains flux WordPress renvoient un BOM ou une ligne vide avant la
    # déclaration XML, ce qui fait échouer ElementTree ("text declaration not
    # at start of entity"). On nettoie l'amorce.
    if xml_bytes[:3] == b"\xef\xbb\xbf":
        xml_bytes = xml_bytes[3:]
    xml_bytes = xml_bytes.lstrip()
    lt = xml_bytes.find(b"<")
    if lt > 0:
        xml_bytes = xml_bytes[lt:]
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return entries

    # --- RSS 2.0 ---------------------------------------------------------
    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item"):
            title = _strip_html(_text(item.find("title")))
            link = _text(item.find("link"))
            desc = _text(item.find("description"))
            pub = _parse_date(_text(item.find("pubDate")))
            source_el = item.find("source")
            source_name = _strip_html(_text(source_el)) if source_el is not None else ""
            source_url = source_el.get("url", "") if source_el is not None else ""
            if not link:
                guid = item.find("guid")
                if guid is not None and (guid.get("isPermaLink") != "false"):
                    link = _text(guid)
            entries.append(FeedEntry(
                title=title, link=link, summary=_strip_html(desc), published=pub,
                source_name=source_name, source_url=source_url,
                feed_lang=feed_lang, feed_label=feed_label,
                raw_link_is_google="news.google.com" in (link or ""),
            ))
        return entries

    # --- Atom ----------------------------------------------------------
    if root.tag == f"{_ATOM}feed":
        for item in root.findall(f"{_ATOM}entry"):
            title = _strip_html(_text(item.find(f"{_ATOM}title")))
            link = ""
            for lk in item.findall(f"{_ATOM}link"):
                rel = lk.get("rel", "alternate")
                if rel == "alternate" or not link:
                    link = lk.get("href", "") or link
            summary = _strip_html(_text(item.find(f"{_ATOM}summary"))
                                  or _text(item.find(f"{_ATOM}content")))
            pub = _parse_date(_text(item.find(f"{_ATOM}published"))
                              or _text(item.find(f"{_ATOM}updated")))
            entries.append(FeedEntry(
                title=title, link=link, summary=summary, published=pub,
                feed_lang=feed_lang, feed_label=feed_label,
                raw_link_is_google="news.google.com" in (link or ""),
            ))
    return entries


def _looks_like_feed(body: bytes) -> bool:
    head = body[:600].lstrip().lower()
    return b"<rss" in head or b"<feed" in head or b"<?xml" in head or b"<rdf" in head


def load_feed(url: str, *, feed_lang: str = "", feed_label: str = "") -> tuple[list[FeedEntry], str | None]:
    """Renvoie (entrées, erreur).

    `erreur` non nul => flux injoignable ou réponse qui n'est pas un flux.
    Un flux valide mais sans article (ex. requête Google News sans résultat sur
    la fenêtre) renvoie ([], None) : ce n'est pas une anomalie.
    """
    res = fetch(url, browser=False)
    if not res.ok or not _looks_like_feed(res.body):
        # certains hébergeurs RSS refusent le UA bot : on retente en navigateur
        res = fetch(url, browser=True)
    if not res.ok:
        return [], res.error or f"HTTP {res.status}"
    if not _looks_like_feed(res.body):
        return [], "la réponse n'est pas un flux RSS/Atom (HTML ? page de blocage ?)"
    entries = parse_feed(res.body, feed_lang=feed_lang, feed_label=feed_label)
    return entries, None


def in_window(entry: FeedEntry, since: date, until: date) -> bool:
    if entry.published is None:
        # Sans date, on garde (Google News sans pubDate est rare) : la date de
        # publication sera retentée à l'extraction. Prudence : on ne rejette pas.
        return True
    return since <= entry.published <= until
