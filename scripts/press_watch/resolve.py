"""
Résolution des liens Google News RSS vers l'URL réelle de l'éditeur.

Google News renvoie des liens du type
    https://news.google.com/rss/articles/CBMi<base64url>...
qui ne redirigent pas en HTTP simple (redirection JS + jeton). Stratégies, dans
l'ordre, en s'arrêtant à la première qui donne une URL hors google :

1. lien déjà direct (host != news.google.com / google.com) -> tel quel
2. décodage du segment base64url : le protobuf encodé contient souvent l'URL
   cible en clair -> on la récupère par regex
3. GET du lien Google News (UA navigateur) et lecture de l'URL finale après
   redirections ; à défaut, `<link rel=canonical>`, `<meta property=og:url>`,
   `data-n-au`, ou premier `<a>` sortant vers un domaine de presse
4. échec -> on renvoie le lien Google News tel quel avec resolved=False
   (l'article sera traité en mode « titre + extrait RSS seulement », la règle
   anti-invention du prompt s'applique).
"""

import base64
import html as _html
import json
import re
import urllib.parse
from urllib.parse import urlparse, parse_qs

from .httputil import fetch, BROWSER_UA
import urllib.request

_GOOGLE_HOSTS = ("news.google.com", "www.google.com", "google.com", "consent.google.com")
_URL_RE = re.compile(rb"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
_CANON_RE = re.compile(
    r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', re.I)
_OGURL_RE = re.compile(
    r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']', re.I)
_NAU_RE = re.compile(r'data-n-au=["\']([^"\']+)["\']', re.I)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _is_google(url: str) -> bool:
    h = _host(url)
    return any(h == g or h.endswith("." + g) for g in _GOOGLE_HOSTS)


def _from_base64_segment(gn_url: str) -> str | None:
    path = urlparse(gn_url).path
    m = re.search(r"/(?:rss/)?articles/([A-Za-z0-9_\-]+)", path)
    if not m:
        return None
    seg = m.group(1)
    seg += "=" * (-len(seg) % 4)
    try:
        decoded = base64.urlsafe_b64decode(seg)
    except Exception:
        return None
    for cand in _URL_RE.findall(decoded):
        try:
            u = cand.decode("utf-8")
        except UnicodeDecodeError:
            continue
        # rejette les URL google et les artefacts de protobuf trop courts
        if not _is_google(u) and len(u) > 15 and "." in _host(u):
            # coupe d'éventuels octets de contrôle collés en fin
            u = re.split(r"[\x00-\x1f]", u)[0]
            return u.rstrip("\\")
    return None


_BATCH_URL = ("https://news.google.com/_/DotsSplashUi/data/batchexecute"
              "?rpcids=Fbv4je&source-path=%2Frss%2Farticles%2F&hl=en-US&gl=US&_reqid=1")


def _from_batchexecute(gn_url: str) -> tuple[str | None, str | None]:
    """Méthode « officieuse » courante : la page article Google News porte un
    attribut data-p (c-wiz) contenant id/timestamp/signature ; on rejoue l'appel
    interne DotsSplashUi/batchexecute (rpc Fbv4je / garturlreq) qui renvoie
    l'URL réelle de l'éditeur. C'est la seule méthode fiable depuis que Google a
    chiffré le segment des liens /rss/articles/."""
    page = fetch(gn_url, browser=True)
    if page.error:
        return None, page.error
    m = re.search(r'data-p="([^"]+)"', page.text())
    if not m:
        return None, "attribut data-p absent"
    try:
        arr = json.loads(_html.unescape(m.group(1)).replace("%.@.", "[", 1))
        obj_id, ts, sig = arr[1], arr[-2], arr[-1]
    except (ValueError, IndexError) as exc:
        return None, f"data-p illisible ({exc})"

    inner = json.dumps([
        "garturlreq",
        [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
          None, None, None, None, None, 0, 1],
         "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
        obj_id, ts, sig,
    ])
    body = "f.req=" + urllib.parse.quote(json.dumps([[["Fbv4je", inner, None, "generic"]]]))
    req = urllib.request.Request(
        _BATCH_URL, data=body.encode("utf-8"),
        headers={"User-Agent": BROWSER_UA,
                 "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except Exception as exc:
        return None, f"batchexecute échoué ({exc})"

    for line in raw.split("\n"):
        if "garturlres" not in line:
            continue
        try:
            payload = json.loads(line)
            url = json.loads(payload[0][2])[1]
        except (ValueError, IndexError, KeyError):
            continue
        if url and not _is_google(url):
            return url, None
    return None, "batchexecute sans URL exploitable"


def _from_page(gn_url: str) -> tuple[str | None, int, str | None]:
    res = fetch(gn_url, browser=True)
    if res.error:
        return None, res.status, res.error
    if not _is_google(res.final_url):
        return res.final_url, res.status, None
    html = res.text()
    for rx in (_CANON_RE, _OGURL_RE, _NAU_RE):
        m = rx.search(html)
        if m and not _is_google(m.group(1)):
            return m.group(1), res.status, None
    # parfois un <a href="https://editeur/..."> unique dans le corps
    for m in re.finditer(r'<a[^>]+href=["\'](https?://[^"\']+)["\']', html, re.I):
        if not _is_google(m.group(1)):
            return m.group(1), res.status, None
    return None, res.status, "page Google News sans URL éditeur exploitable"


def resolve(link: str) -> dict:
    """Renvoie {url, resolved: bool, method: str, note: str|None}."""
    if not link:
        return {"url": link, "resolved": False, "method": "vide", "note": "lien absent"}

    if not _is_google(link):
        # certains flux passent l'URL éditeur dans ?url=
        qs = parse_qs(urlparse(link).query)
        if "url" in qs and qs["url"]:
            return {"url": qs["url"][0], "resolved": True, "method": "param_url", "note": None}
        return {"url": link, "resolved": True, "method": "direct", "note": None}

    from_b64 = _from_base64_segment(link)
    if from_b64:
        return {"url": from_b64, "resolved": True, "method": "base64", "note": None}

    url, err_batch = _from_batchexecute(link)
    if url:
        return {"url": url, "resolved": True, "method": "batchexecute", "note": None}

    url, status, err_page = _from_page(link)
    if url:
        return {"url": url, "resolved": True, "method": "page_redirect", "note": None}

    return {"url": link, "resolved": False, "method": "echec",
            "note": err_batch or err_page or f"non résolu (HTTP {status})"}
