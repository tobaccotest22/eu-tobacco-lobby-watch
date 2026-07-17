"""
Complète scripts/fetch_ep_meetings.py (qui filtre par register_id, donc
seulement nos 46 organisations connues) par une recherche libre par mot-clé
sur le registre officiel du Parlement européen :
https://www.europarl.europa.eu/meps/en/search-meetings

Objectif : obtenir un total de réunions "tabac/nicotine, tous acteurs
confondus" depuis le 1er janvier 2025 - y compris cabinets de conseil,
lobbyistes individuels, organisations absentes de notre liste de 46, et
même des acteurs opposés à l'industrie (ONG de santé, etc., puisque la
recherche est par mot-clé et non par camp).

Une même réunion peut remonter pour plusieurs mots-clés à la fois (ex:
"tobacco" et "nicotine") : on dédoublonne sur (member_id, meeting_date,
title). Le champ CSV "lobbyist_id" peut lui-même contenir plusieurs
identifiants de registre séparés par "|" quand une réunion a plusieurs
organisations participantes ; on éclate cette liste pour vérifier si l'une
d'elles correspond à une de nos 46 organisations suivies.

Écrit le résultat dans data/live_data.json._aggregate :
- ep_meetings_keyword_total_since_2025 : nombre de réunions dédoublonnées
- ep_meetings_keyword_terms : les mots-clés utilisés
- ep_meetings_outside_our_46 : réunions ne correspondant à AUCUNE de nos 46
  organisations (pour voir qui sont ces acteurs "hors liste")
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
KEYWORDS = ["tobacco", "nicotine", "cigarette", "cigar", "vape", "snus", "tabac"]
USER_AGENT = "Mozilla/5.0 (compatible; eu-tobacco-lobby-watch/0.4)"
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_REQUESTS = 1


def fetch_keyword_csv(keyword: str) -> list[dict]:
    params = {
        "textualSearch": keyword,
        "fromDate": SINCE_DATE.strftime("%d/%m/%Y"),
        "toDate": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
        "exportFormat": "CSV",
    }
    url = f"{EP_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        raw = response.read().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(raw)))


def load_our_register_ids() -> set[str]:
    with open(ENTITIES_PATH, encoding="utf-8") as f:
        entities = json.load(f)["entities"]
    return {e["register_id"] for e in entities if e.get("register_id")}


def dedupe_meetings(rows_by_keyword: dict[str, list[dict]]) -> dict:
    """Fusionne les résultats de tous les mots-clés sur (member_id, date, title)."""
    meetings = {}
    for keyword, rows in rows_by_keyword.items():
        for row in rows:
            key = (row.get("member_id"), row.get("meeting_date"), row.get("title"))
            lobbyist_ids = [x for x in (row.get("lobbyist_id") or "").split("|") if x]
            attendees = [x.strip() for x in (row.get("attendees") or "").split("|") if x.strip()]

            meeting = meetings.setdefault(key, {
                "member_id": row.get("member_id"),
                "member_name": row.get("member_name"),
                "date": row.get("meeting_date"),
                "title": row.get("title"),
                "member_capacity": row.get("member_capacity"),
                "procedure_reference": row.get("procedure_reference") or None,
                "attendees": set(),
                "lobbyist_ids": set(),
                "matched_keywords": set(),
            })
            meeting["attendees"].update(attendees)
            meeting["lobbyist_ids"].update(lobbyist_ids)
            meeting["matched_keywords"].add(keyword)
    return meetings


def main():
    our_register_ids = load_our_register_ids()

    rows_by_keyword = {}
    for keyword in KEYWORDS:
        print(f"Recherche mot-clé : {keyword}")
        try:
            rows_by_keyword[keyword] = fetch_keyword_csv(keyword)
        except Exception as exc:
            print(f"  échec pour '{keyword}' : {exc}")
            rows_by_keyword[keyword] = []
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    meetings = dedupe_meetings(rows_by_keyword)

    outside_our_46 = []
    for meeting in meetings.values():
        if not (meeting["lobbyist_ids"] & our_register_ids):
            outside_our_46.append({
                "date": meeting["date"],
                "member_name": meeting["member_name"],
                "title": meeting["title"],
                "procedure_reference": meeting["procedure_reference"],
                "attendees": sorted(meeting["attendees"]),
                "matched_keywords": sorted(meeting["matched_keywords"]),
            })
    outside_our_46.sort(key=lambda m: m["date"] or "", reverse=True)

    outside_actors = sorted({name for m in outside_our_46 for name in m["attendees"]})

    try:
        with open(LIVE_DATA_PATH, encoding="utf-8") as f:
            live_data = json.load(f)
    except FileNotFoundError:
        live_data = {}

    aggregate = live_data.setdefault("_aggregate", {})
    aggregate["ep_meetings_keyword_total_since_2025"] = len(meetings)
    aggregate["ep_meetings_keyword_terms"] = KEYWORDS
    aggregate["ep_meetings_keyword_computed_at"] = datetime.now(timezone.utc).isoformat()
    aggregate["ep_meetings_outside_our_46_count"] = len(outside_our_46)
    aggregate["ep_meetings_outside_our_46"] = outside_our_46
    aggregate["ep_meetings_outside_our_46_actors"] = outside_actors

    with open(LIVE_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(live_data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\nTotal réunions tabac/nicotine dédoublonnées depuis 2025 : {len(meetings)}")
    print(f"Dont hors de nos 46 organisations : {len(outside_our_46)}")
    print(f"Terminé. Résultat fusionné dans {LIVE_DATA_PATH}")


if __name__ == "__main__":
    main()
