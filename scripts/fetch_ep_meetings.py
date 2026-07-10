"""
Pour chaque organisation de data/entities.json ayant un register_id, ce script
compte et liste les réunions déclarées par des eurodéputés depuis le
1er janvier 2025, via le registre officiel du Parlement européen :
https://www.europarl.europa.eu/meps/en/search-meetings

Le filtre transparencyRegisterIds (identifié en inspectant le formulaire de
recherche via /search-meetings/facets) permet un filtrage exact par numéro de
registre de transparence, avec un export CSV directement exploitable
(&exportFormat=CSV).

Le script fusionne ses résultats dans data/live_data.json sans écraser les
clés "lobbyfacts"/"ec_meetings" qu'écrit scripts/fetch_lobbyfacts.py.
"""

import csv
import io
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ENTITIES_PATH = "data/entities.json"
LIVE_DATA_PATH = "data/live_data.json"
EP_SEARCH_URL = "https://www.europarl.europa.eu/meps/en/search-meetings"
SINCE_DATE = datetime(2025, 1, 1)
USER_AGENT = "Mozilla/5.0 (compatible; eu-tobacco-lobby-watch/0.3)"
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_REQUESTS = 1


def fetch_ep_meetings(register_id: str) -> dict:
    params = {
        "transparencyRegisterIds": register_id,
        "fromDate": SINCE_DATE.strftime("%d/%m/%Y"),
        "toDate": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
        "exportFormat": "CSV",
    }
    url = f"{EP_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read().decode("utf-8-sig")
    except Exception as exc:
        return {"error": f"export CSV échoué : {exc}", "source_url": url}

    reader = csv.DictReader(io.StringIO(raw))
    meetings = [
        {
            "date": row.get("meeting_date"),
            "member_name": row.get("member_name"),
            "member_capacity": row.get("member_capacity"),
            "title": row.get("title"),
            "procedure_reference": row.get("procedure_reference") or None,
        }
        for row in reader
    ]
    meetings.sort(key=lambda m: m["date"] or "", reverse=True)

    return {
        "source_url": url,
        "since_2025_count": len(meetings),
        "since_2025": meetings,
    }


def main():
    with open(ENTITIES_PATH, encoding="utf-8") as f:
        entities = json.load(f)["entities"]

    try:
        with open(LIVE_DATA_PATH, encoding="utf-8") as f:
            live_data = json.load(f)
    except FileNotFoundError:
        live_data = {}

    now = datetime.now(timezone.utc).isoformat()

    for entity in entities:
        register_id = entity.get("register_id")
        name = entity["name"]
        if not register_id:
            print(f"(pas de register_id, ignoré) {name}")
            continue

        print(f"Réunions PE : {name} ({register_id})")
        entry = live_data.setdefault(register_id, {"name": name, "register_id": register_id})
        entry["name"] = name
        entry["ep_meetings"] = fetch_ep_meetings(register_id)
        entry["ep_meetings_last_fetched"] = now
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    with open(LIVE_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(live_data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\nTerminé. Résultats fusionnés dans {LIVE_DATA_PATH}")


if __name__ == "__main__":
    main()
