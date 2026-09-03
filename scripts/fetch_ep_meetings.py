"""
Pour chaque organisation de data/entities.json ayant un register_id, ce script
compte et liste les réunions déclarées par des eurodéputés depuis le
1er janvier 2025, via le registre officiel du Parlement européen :
https://www.europarl.europa.eu/meps/en/search-meetings

Le filtre transparencyRegisterIds (identifié en inspectant le formulaire de
recherche via /search-meetings/facets) permet un filtrage exact par numéro de
registre de transparence, avec un export CSV directement exploitable
(&exportFormat=CSV).

Depuis ~juillet 2026, ce endpoint est protégé par un challenge JS AWS WAF
qu'une requête HTTP simple ne peut pas résoudre (voir docstring de
scripts/ep_meetings_client.py) : on passe donc par Playwright pour
obtenir un cookie de session valide avant chaque export CSV.

Le script fusionne ses résultats dans data/live_data.json sans écraser les
clés "lobbyfacts"/"ec_meetings" qu'écrit scripts/fetch_lobbyfacts.py.

Comme ce script tourne en second dans le workflow, il recalcule aussi, à la
fin, un total agrégé ("_aggregate") sur l'ensemble des organisations : somme
du budget_high (estimation maximale prudente plutôt qu'une moyenne),
somme de people_involved, et nombre total de réunions Parlement/Commission
depuis 2025.
"""

import json
import sys
import time
import urllib.parse
from datetime import datetime, timezone

from ep_meetings_client import EP_SEARCH_URL, ep_meetings_session

ENTITIES_PATH = "data/entities.json"
LIVE_DATA_PATH = "data/live_data.json"
SINCE_DATE = datetime(2025, 1, 1)
SLEEP_BETWEEN_REQUESTS = 1


def fetch_ep_meetings(fetch_csv, register_id: str) -> dict:
    params = {
        "transparencyRegisterIds": register_id,
        "fromDate": SINCE_DATE.strftime("%d/%m/%Y"),
        "toDate": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
    }
    url = f"{EP_SEARCH_URL}?{urllib.parse.urlencode({**params, 'exportFormat': 'CSV'})}"
    try:
        rows = fetch_csv(params)
    except Exception as exc:
        return {"error": f"export CSV échoué : {exc}", "source_url": url}

    meetings = [
        {
            "date": row.get("meeting_date"),
            "member_id": row.get("member_id") or None,
            "member_name": row.get("member_name"),
            "member_capacity": row.get("member_capacity"),
            "title": row.get("title"),
            "procedure_reference": row.get("procedure_reference") or None,
        }
        for row in rows
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
    errors = []

    with ep_meetings_session() as fetch_csv:
        for entity in entities:
            register_id = entity.get("register_id")
            name = entity["name"]
            if not register_id:
                print(f"(pas de register_id, ignoré) {name}")
                continue

            print(f"Réunions PE : {name} ({register_id})")
            entry = live_data.setdefault(register_id, {"name": name, "register_id": register_id})
            entry["name"] = name
            result = fetch_ep_meetings(fetch_csv, register_id)
            if "error" in result:
                # On ne remplace pas les données de la veille par une erreur :
                # ça écraserait un comptage valide par un 0 silencieux dans
                # l'agrégat. On garde l'ancienne valeur et on fait échouer le
                # job plus bas pour que l'échec soit visible.
                errors.append(f"{name} ({register_id}) : {result['error']}")
                print(f"  ÉCHEC : {result['error']}")
            else:
                entry["ep_meetings"] = result
                entry["ep_meetings_last_fetched"] = now
            time.sleep(SLEEP_BETWEEN_REQUESTS)

    # Fusionne (plutôt que remplace) : les scripts de recherche mot-clé
    # (fetch_keyword_meetings.py, fetch_ec_keyword_meetings.py) et
    # fetch_mep_countries.py écrivent aussi des clés dans _aggregate,
    # potentiellement avant ce script selon l'ordre d'exécution.
    live_data.setdefault("_aggregate", {}).update(compute_aggregate(live_data))

    with open(LIVE_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(live_data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\nTerminé. Résultats fusionnés dans {LIVE_DATA_PATH}")

    if errors:
        print(f"\n{len(errors)} organisation(s) en échec sur {len(entities)} :")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)


def compute_aggregate(live_data: dict) -> dict:
    orgs = [e for rid, e in live_data.items() if rid != "_aggregate"]
    return {
        "note": "budget_total = somme des bornes hautes (budget_high) : estimation maximale prudente, pas une moyenne.",
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "nb_organisations": len(orgs),
        "budget_high_total": sum(e.get("budget_high") or 0 for e in orgs),
        "people_involved_total": sum(e.get("people_involved") or 0 for e in orgs),
        "ep_meetings_since_2025_total": sum((e.get("ep_meetings") or {}).get("since_2025_count") or 0 for e in orgs),
        "ec_meetings_since_2025_total": sum((e.get("ec_meetings") or {}).get("since_2025_count") or 0 for e in orgs),
    }


if __name__ == "__main__":
    main()
