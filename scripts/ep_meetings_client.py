"""
Client partagé pour interroger https://www.europarl.europa.eu/meps/en/search-meetings.

Depuis ~juillet 2026, ce endpoint est protégé par un challenge JS AWS WAF
(cookie "aws-waf-token" posé par un script chargé depuis *.token.awswaf.com).
Une requête HTTP simple (urllib/requests, sans moteur JS) ne peut pas résoudre
ce challenge : le serveur répond 202 avec un corps vide/HTML au lieu du CSV
attendu, ce qui se traduisait par des résultats vides ou non filtrés.

On utilise donc Playwright pour :
1. Charger une première fois la page de recherche dans un vrai Chromium
   headless, ce qui exécute le challenge JS et pose le cookie aws-waf-token
   sur le contexte navigateur.
2. Réutiliser ce même contexte (donc les mêmes cookies) pour toutes les
   requêtes suivantes vers &exportFormat=CSV, via context.request (l'API de
   requêtes HTTP de Playwright, qui partage le cookie jar du contexte) —
   pas besoin de gérer un téléchargement de fichier.

Le format du CSV renvoyé n'a lui pas changé : colonnes title, member_id,
member_name, meeting_date, member_capacity, procedure_reference, attendees,
lobbyist_id (vérifié en juillet 2026 par requête directe sur le site).
"""

import csv
import io
import urllib.parse
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

EP_SEARCH_URL = "https://www.europarl.europa.eu/meps/en/search-meetings"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


@contextmanager
def ep_meetings_session():
    """Ouvre un contexte navigateur, résout le challenge WAF, puis fournit
    une fonction fetch_csv(params) -> list[dict] réutilisant ce contexte."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        page.goto(EP_SEARCH_URL, wait_until="networkidle")

        def fetch_csv(params: dict) -> list[dict]:
            url = f"{EP_SEARCH_URL}?{urllib.parse.urlencode({**params, 'exportFormat': 'CSV'})}"
            response = context.request.get(url)
            if not response.ok:
                raise RuntimeError(f"export CSV échoué ({response.status}) : {url}")
            raw = response.text().lstrip("﻿")
            return list(csv.DictReader(io.StringIO(raw)))

        try:
            yield fetch_csv
        finally:
            context.close()
            browser.close()
