"""
Complète scripts/fetch_lobbyfacts.py (qui scrape le PDF officiel du registre
par register_id, donc seulement nos organisations suivies) avec le jeu de
données ouvert d'Integrity Watch EU (Transparency International EU), qui
liste TOUTES les réunions "haut niveau" de la Commission du mandat en cours,
tous acteurs confondus :
https://integritywatch.eu/autoupdate_data_eu/lobbyists_ecmeetings/latest/ecmeetings_vonderleyen2.json

Vérifié avant d'écrire ce script : leur "Data Hub" (exports en masse) est
derrière un compte, mais ce fichier JSON qui alimente leur outil de recherche
(ecmeetings.php) est un fichier statique accessible sans authentification -
il est chargé tel quel côté client puis filtré en JavaScript
(crossfilter/dc.js). Il n'y a donc aucune API de recherche serveur à
simuler : on télécharge ce fichier (~48 Mo, ~31 500 réunions) et on filtre
nous-mêmes par mot-clé.

Chaque organisation présente à une réunion multi-participants a sa propre
entrée dans le jeu de données (une réunion à 4 organisations donne 4
entrées) : cela correspond exactement à ce dont on a besoin, une entrée par
organisation rencontrée. Le champ OrgId est le même identifiant du registre
de transparence de l'UE que data/entities.json, ce qui permet de distinguer
de façon fiable (pas de correspondance approximative par nom) les réunions
de nos organisations suivies (déjà couvertes par fetch_lobbyfacts.py) de
celles d'acteurs "hors liste".

Écrit dans data/live_data.json._aggregate :
- ec_meetings_outside_our_46 : réunions Commission hors de nos organisations
  suivies, filtrées par mot-clé tabac/nicotine (tri décroissant par date)
"""

import html
import json
import re
import urllib.request
from datetime import datetime, timezone

ENTITIES_PATH = "data/entities.json"
LIVE_DATA_PATH = "data/live_data.json"
EC_MEETINGS_DATASET_URL = "https://integritywatch.eu/autoupdate_data_eu/lobbyists_ecmeetings/latest/ecmeetings_vonderleyen2.json"
KEYWORDS = ["tobacco", "nicotine", "cigarette", "cigar", "vape", "snus", "tabac"]
USER_AGENT = "Mozilla/5.0 (compatible; eu-tobacco-lobby-watch/0.4)"
REQUEST_TIMEOUT = 90


def load_our_register_ids() -> set[str]:
    with open(ENTITIES_PATH, encoding="utf-8") as f:
        entities = json.load(f)["entities"]
    return {e["register_id"] for e in entities if e.get("register_id")}


def fetch_all_ec_meetings() -> list[dict]:
    req = urllib.request.Request(EC_MEETINGS_DATASET_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        return json.loads(response.read())


def matches_keywords(meeting: dict) -> bool:
    haystack = f"{meeting.get('subject') or ''} {meeting.get('Org') or ''}".lower()
    return any(k in haystack for k in KEYWORDS)


def cabinet_label(cabinet: str | None) -> str | None:
    if not cabinet:
        return None
    cabinet = html.unescape(cabinet)
    match = re.match(r"Cabinet of Commissioner (.+)$", cabinet)
    return f"Cabinet de {match.group(1)}" if match else cabinet


def main():
    our_register_ids = load_our_register_ids()

    print("Téléchargement du jeu de données Integrity Watch EU (réunions Commission)...")
    all_meetings = fetch_all_ec_meetings()
    print(f"{len(all_meetings)} réunions Commission au total (mandat en cours)")

    matched = [m for m in all_meetings if matches_keywords(m)]
    print(f"{len(matched)} réunions correspondant aux mots-clés tabac/nicotine")

    outside = []
    for m in matched:
        org_id = m.get("OrgId")
        if org_id and org_id in our_register_ids:
            continue
        outside.append({
            "date": m.get("date"),
            "org": html.unescape(m.get("Org") or ""),
            "org_id": org_id,
            "subject": html.unescape(m.get("subject") or ""),
            "dg": cabinet_label(m.get("cabinet")),
        })
    outside.sort(key=lambda m: m["date"] or "", reverse=True)
    outside_actors = sorted({m["org"] for m in outside if m["org"]})

    print(f"{len(outside)} hors de nos organisations suivies")

    try:
        with open(LIVE_DATA_PATH, encoding="utf-8") as f:
            live_data = json.load(f)
    except FileNotFoundError:
        live_data = {}

    aggregate = live_data.setdefault("_aggregate", {})
    # Suffixe "_current_mandate" (et non "_since_2025" comme le pendant
    # Parlement dans fetch_keyword_meetings.py) : le jeu de données Integrity
    # Watch couvre tout le mandat en cours de la Commission, sans borne de
    # date filtrable côté source.
    aggregate["ec_meetings_keyword_total_current_mandate"] = len(matched)
    aggregate["ec_meetings_keyword_terms"] = KEYWORDS
    aggregate["ec_meetings_keyword_computed_at"] = datetime.now(timezone.utc).isoformat()
    aggregate["ec_meetings_outside_our_46_count"] = len(outside)
    aggregate["ec_meetings_outside_our_46"] = outside
    aggregate["ec_meetings_outside_our_46_actors"] = outside_actors

    with open(LIVE_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(live_data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\nTerminé. Résultat fusionné dans {LIVE_DATA_PATH}")


if __name__ == "__main__":
    main()
