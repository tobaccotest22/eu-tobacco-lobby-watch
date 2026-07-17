"""
Pour chaque organisation de data/entities.json ayant un register_id, ce script
récupère l'historique du budget annuel déclaré, année par année, à partir du
bloc JSON caché de la page datacard LobbyFacts :
https://www.lobbyfacts.eu/datacard/x?rid={register_id}

Contrairement à scripts/fetch_lobbyfacts.py (qui ne lit que l'instantané
budget_low/budget_high le plus récent), la page datacard embarque un
<div id="graph_info" style="display:none">{"2010":1125000,...}</div>
utilisé pour dessiner son propre graphique "Lobbying Costs over the years" :
ce bloc contient l'historique complet tel que déclaré par l'organisation.

Vérifié manuellement sur trois organisations avant généralisation (Philip
Morris International, British American Tobacco, Imperial Brands) : PMI donne
bien 2 750 000 € pour 2022, cohérent avec l'exercice attendu.

Écrit data/budget_history.json : historique par organisation (register_id ->
budget par année) + agrégat par année (somme des budgets disponibles cette
année-là, avec le nombre d'organisations comptées).
"""

import html
import json
import re
import time
import urllib.request
from datetime import datetime, timezone

ENTITIES_PATH = "data/entities.json"
OUTPUT_PATH = "data/budget_history.json"
DATACARD_URL = "https://www.lobbyfacts.eu/datacard/x?rid={register_id}"
USER_AGENT = "eu-tobacco-lobby-watch/0.3"
REQUEST_TIMEOUT = 20
SLEEP_BETWEEN_REQUESTS = 1

GRAPH_INFO_RE = re.compile(r'<div id="graph_info"[^>]*>(.*?)</div>', re.DOTALL)


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        return response.read().decode("utf-8")


def fetch_budget_by_year(register_id: str) -> dict | None:
    url = DATACARD_URL.format(register_id=register_id)
    try:
        page_html = http_get(url)
    except Exception as exc:
        return {"error": f"page datacard échouée : {exc}"}

    match = GRAPH_INFO_RE.search(page_html)
    if not match:
        return None

    try:
        raw_json = html.unescape(match.group(1))
        return json.loads(raw_json)
    except Exception as exc:
        return {"error": f"lecture du bloc graph_info échouée : {exc}"}


def compute_yearly_totals(organisations: dict) -> dict:
    totals: dict = {}
    for entry in organisations.values():
        budget_by_year = entry.get("budget_by_year")
        if not isinstance(budget_by_year, dict) or "error" in budget_by_year:
            continue
        for year, amount in budget_by_year.items():
            if not isinstance(amount, (int, float)):
                continue
            bucket = totals.setdefault(year, {"total": 0, "nb_organisations": 0})
            bucket["total"] += amount
            bucket["nb_organisations"] += 1
    return dict(sorted(totals.items()))


def main():
    with open(ENTITIES_PATH, encoding="utf-8") as f:
        entities = json.load(f)["entities"]

    organisations = {}
    for entity in entities:
        register_id = entity.get("register_id")
        name = entity["name"]
        if not register_id:
            print(f"(pas de register_id, ignoré) {name}")
            continue

        print(f"Historique budget LobbyFacts : {name} ({register_id})")
        budget_by_year = fetch_budget_by_year(register_id)
        if budget_by_year is None:
            print("  (pas de bloc graph_info trouvé sur la fiche)")
        elif isinstance(budget_by_year, dict) and "error" in budget_by_year:
            print(f"  ({budget_by_year['error']})")

        organisations[register_id] = {
            "name": name,
            "budget_by_year": budget_by_year,
        }
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    data = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "organisations": organisations,
        "yearly_totals": compute_yearly_totals(organisations),
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\nTerminé. Résultats écrits dans {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
