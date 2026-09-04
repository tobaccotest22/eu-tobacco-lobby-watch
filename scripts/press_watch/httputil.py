"""
Petit wrapper HTTP commun au pipeline de veille presse.

Même philosophie que le reste du dépôt (urllib de la stdlib, pas de requests) mais
avec deux user-agents : un UA « navigateur » pour les éditeurs qui bloquent les
bots (cf. section 9 du cahier des charges — Politico/Euractiv), et un UA « bot »
honnête pour les flux RSS et les sites qui n'ont pas de raison de nous bloquer.
"""

import gzip
import io
import urllib.error
import urllib.request

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
BOT_UA = "eu-tobacco-lobby-watch/1.0 (+https://github.com/tobaccotest22/eu-tobacco-lobby-watch)"

DEFAULT_TIMEOUT = 25


class FetchResult:
    """Réponse HTTP minimale : corps, URL finale (après redirections), statut."""

    def __init__(self, url: str, final_url: str, status: int, body: bytes,
                 content_type: str = "", error: str | None = None):
        self.url = url
        self.final_url = final_url
        self.status = status
        self.body = body
        self.content_type = content_type
        self.error = error

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status < 300

    def text(self, fallback_encoding: str = "utf-8") -> str:
        # Encodage : on tente l'en-tête, sinon utf-8, sinon latin-1 en dernier
        # recours (ne lève jamais).
        encoding = fallback_encoding
        if "charset=" in (self.content_type or "").lower():
            encoding = self.content_type.lower().split("charset=", 1)[1].split(";")[0].strip() or encoding
        for enc in (encoding, "utf-8", "cp1252", "latin-1"):
            try:
                return self.body.decode(enc)
            except (LookupError, UnicodeDecodeError):
                continue
        return self.body.decode("utf-8", errors="replace")


def fetch(url: str, *, browser: bool = True, timeout: int = DEFAULT_TIMEOUT,
          extra_headers: dict | None = None) -> FetchResult:
    """GET avec suivi de redirection. Ne lève jamais : renvoie un FetchResult
    dont `.error` est renseigné en cas d'échec."""
    headers = {
        "User-Agent": BROWSER_UA if browser else BOT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml,application/rss+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr,en;q=0.8,de;q=0.6,it;q=0.5",
        "Accept-Encoding": "gzip",
    }
    if extra_headers:
        headers.update(extra_headers)

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                try:
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                except OSError:
                    pass
            return FetchResult(
                url=url,
                final_url=resp.geturl(),
                status=resp.status,
                body=raw,
                content_type=resp.headers.get("Content-Type", ""),
            )
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()
        except Exception:
            pass
        return FetchResult(url, url, exc.code, body,
                           exc.headers.get("Content-Type", "") if exc.headers else "",
                           error=f"HTTP {exc.code}")
    except Exception as exc:  # timeout, DNS, refus de connexion, URL malformée...
        return FetchResult(url, url, 0, b"", error=f"{type(exc).__name__}: {exc}")
