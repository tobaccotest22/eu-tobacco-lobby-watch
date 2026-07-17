"""
Pour chaque eurodéputé rencontré par une organisation suivie (member_id présent
dans data/live_data.json, ajouté par scripts/fetch_ep_meetings.py), ce script
récupère son pays via l'API Open Data officielle du Parlement européen :
https://data.europarl.europa.eu/api/v2/meps/{member_id}

Contrairement à l'export CSV de search-meetings (aucun champ pays/nationalité),
cette API structurée (JSON-LD) expose l'historique des mandats de chaque
eurodéputé, chacun rattaché à un pays ("represents") sous forme de code ISO3
(ex: "NLD" pour ZIJLSTRA Auke). On retient le mandat de député en cours
(memberDuring sans endDate) ; à défaut, le plus récent par date de début.

Écrit data/mep_countries.json : { member_id: { country_code, country_name } }.
"""

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

LIVE_DATA_PATH = "data/live_data.json"
OUTPUT_PATH = "data/mep_countries.json"
MEP_API_URL = "https://data.europarl.europa.eu/api/v2/meps/{member_id}?format=application%2Fld%2Bjson"
USER_AGENT = "eu-tobacco-lobby-watch/0.4"
REQUEST_TIMEOUT = 20
SLEEP_BETWEEN_REQUESTS = 2
MAX_RETRIES = 5

COUNTRY_NAMES_FR = {
    "AUT": "Autriche", "BEL": "Belgique", "BGR": "Bulgarie", "HRV": "Croatie",
    "CYP": "Chypre", "CZE": "Tchéquie", "DNK": "Danemark", "EST": "Estonie",
    "FIN": "Finlande", "FRA": "France", "DEU": "Allemagne", "GRC": "Grèce",
    "HUN": "Hongrie", "IRL": "Irlande", "ITA": "Italie", "LVA": "Lettonie",
    "LTU": "Lituanie", "LUX": "Luxembourg", "MLT": "Malte", "NLD": "Pays-Bas",
    "POL": "Pologne", "PRT": "Portugal", "ROU": "Roumanie", "SVK": "Slovaquie",
    "SVN": "Slovénie", "ESP": "Espagne", "SWE": "Suède",
}


def http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < MAX_RETRIES:
                wait = 5 * attempt
                print(f"    429 Too Many Requests, nouvelle tentative dans {wait}s...")
                time.sleep(wait)
                continue
            raise


def collect_member_ids(live_data: dict) -> set[str]:
    member_ids = set()
    for rid, entry in live_data.items():
        if rid == "_aggregate":
            continue
        for meeting in (entry.get("ep_meetings") or {}).get("since_2025", []):
            if meeting.get("member_id"):
                member_ids.add(str(meeting["member_id"]))
    return member_ids


def fetch_mep_country(member_id: str) -> dict | None:
    url = MEP_API_URL.format(member_id=member_id)
    try:
        payload = http_get_json(url)
    except Exception as exc:
        return {"error": f"API MEP échouée : {exc}"}

    people = payload.get("data") or []
    if not people:
        return None
    memberships = people[0].get("hasMembership") or []

    parliament_memberships = [
        m for m in memberships
        if m.get("role") == "def/ep-roles/MEMBER_PARLIAMENT" and m.get("represents")
    ]
    if not parliament_memberships:
        return None

    current = [m for m in parliament_memberships if not m.get("memberDuring", {}).get("endDate")]
    chosen = current[0] if current else max(
        parliament_memberships,
        key=lambda m: m.get("memberDuring", {}).get("startDate") or "",
    )

    country_code = chosen["represents"][0].rstrip("/").rsplit("/", 1)[-1]
    return {
        "country_code": country_code,
        "country_name": COUNTRY_NAMES_FR.get(country_code, country_code),
    }


def main():
    with open(LIVE_DATA_PATH, encoding="utf-8") as f:
        live_data = json.load(f)

    member_ids = collect_member_ids(live_data)
    print(f"{len(member_ids)} eurodéputés uniques à résoudre")

    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            result = json.load(f).get("meps", {})
    except FileNotFoundError:
        result = {}

    remaining = sorted(member_ids - result.keys())
    print(f"{len(result)} déjà résolus, {len(remaining)} restants")

    for member_id in remaining:
        country = fetch_mep_country(member_id)
        if country and "error" not in country:
            print(f"  {member_id} -> {country['country_name']}")
            result[member_id] = country
        elif country and "error" in country:
            print(f"  {member_id} -> {country['error']}")
        else:
            print(f"  {member_id} -> pas de mandat de député trouvé")
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    output = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "meps": result,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\nTerminé. {len(result)}/{len(member_ids)} pays résolus. Résultats écrits dans {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
