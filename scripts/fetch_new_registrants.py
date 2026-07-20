"""
Veille brute des nouvelles inscriptions au registre de transparence de l'UE
mentionnant tabac/nicotine/vape - tous types d'acteurs confondus, sans tri
industrie/santé publique/autre (cf. limites documentées dans NOTES.md :
aucun champ structuré du registre ne permet de distinguer fiablement un
lobby tabac d'une ONG anti-tabac ou d'un acteur neutre).

Endpoint public vérifié, sans authentification :
https://ec.europa.eu/transparencyregister/public/lastestRegistration
Renvoie les 10 dernières inscriptions au registre, tous secteurs confondus
(id, name, registrationDate). Comme le tabac/nicotine/vape est un secteur
mineur du volume total d'inscriptions (~3-6/jour), la plupart des exécutions
ne remonteront aucune correspondance : on ACCUMULE les résultats trouvés au
fil du temps dans data/live_data.json._aggregate.new_tobacco_registrants
plutôt que d'écraser à chaque exécution (même principe que
ec_meetings_outside_our_46).

Pour chaque candidat parmi les 10 dernières inscriptions, on vérifie le nom
ET l'objet déclaré ("Objectifs/mandat de votre organisation", lu sur la même
fiche fragment que scripts/fetch_lobbyfacts.py) : une correspondance sur l'un
ou l'autre suffit.
"""

import html
import json
import re
import urllib.request
from datetime import datetime, timezone

from bs4 import BeautifulSoup

LIVE_DATA_PATH = "data/live_data.json"
LATEST_REGISTRATIONS_URL = "https://ec.europa.eu/transparencyregister/public/lastestRegistration?lang=fr"
ORG_DETAIL_FRAGMENT = "https://ec.europa.eu/transparencyregister/public/PUBLIC/ORGANISATION/{id}?lang=fr"
REGISTER_PUBLIC_URL = "https://transparency-register.europa.eu/search-register-or-update/organisation-detail_fr?id={id}"
KEYWORDS = ["tobacco", "nicotine", "cigarette", "cigar", "vape", "snus", "tabac"]
USER_AGENT = "Mozilla/5.0 (compatible; eu-tobacco-lobby-watch/0.4)"
REQUEST_TIMEOUT = 20


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        return response.read()


def fetch_latest_registrations() -> list[dict]:
    return json.loads(http_get(LATEST_REGISTRATIONS_URL))


def fetch_objectives(org_id: str) -> str | None:
    """Lit le champ "Objectifs/mandat de votre organisation" sur la fiche détail."""
    try:
        detail_html = http_get(ORG_DETAIL_FRAGMENT.format(id=org_id)).decode("utf-8")
    except Exception:
        return None

    soup = BeautifulSoup(detail_html, "lxml")
    for row in soup.select("tr.ecl-table__row"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        label_el = cells[0].find("strong")
        if not label_el:
            continue
        label = label_el.get_text(strip=True)
        if "Objectifs" in label and "mandat" in label:
            return cells[1].get_text(" ", strip=True)
    return None


def matches_keywords(text: str | None) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(keyword in lower for keyword in KEYWORDS)


def main():
    print("Téléchargement des dernières inscriptions au registre de transparence...")
    latest = fetch_latest_registrations()
    print(f"{len(latest)} inscriptions récentes récupérées (tous secteurs confondus)")

    try:
        with open(LIVE_DATA_PATH, encoding="utf-8") as f:
            live_data = json.load(f)
    except FileNotFoundError:
        live_data = {}

    aggregate = live_data.setdefault("_aggregate", {})
    existing = aggregate.get("new_tobacco_registrants", [])
    existing_ids = {e["id"] for e in existing}

    now = datetime.now(timezone.utc).isoformat()
    new_matches = []

    for candidate in latest:
        org_id = candidate.get("id")
        name = html.unescape(candidate.get("name") or "")
        if not org_id or org_id in existing_ids:
            continue

        matched_via = None
        if matches_keywords(name):
            matched_via = "nom"
        else:
            objectives = fetch_objectives(org_id)
            if matches_keywords(objectives):
                matched_via = "objet déclaré"

        if matched_via:
            print(f"  Correspondance ({matched_via}) : {name}")
            new_matches.append({
                "id": org_id,
                "name": name,
                "registration_date": candidate.get("registrationDate"),
                "register_url": REGISTER_PUBLIC_URL.format(id=org_id),
                "matched_via": matched_via,
                "detected_at": now,
            })

    combined = existing + new_matches
    combined.sort(key=lambda e: e.get("registration_date") or "", reverse=True)

    aggregate["new_tobacco_registrants"] = combined
    aggregate["new_tobacco_registrants_count"] = len(combined)
    aggregate["new_tobacco_registrants_computed_at"] = now

    with open(LIVE_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(live_data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\n{len(new_matches)} nouvelle(s) correspondance(s) ajoutée(s), {len(combined)} au total accumulées.")


if __name__ == "__main__":
    main()
