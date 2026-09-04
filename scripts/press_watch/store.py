"""
Lecture / écriture du fichier de données de la veille presse.

data/press_watch.json — accumulé, jamais écrasé (même principe que
_aggregate.new_tobacco_registrants). Tant que la section n'est pas branchée au
site, ce fichier n'est référencé nulle part : le produire ne change rien à
l'affichage public.

Structure :
{
  "schema_version": 1,
  "generated_at": "ISO",
  "articles":        [ ... ],   # publiés : pertinent && confiance != faible, dédoublonnés
  "queue_review":    [ ... ],   # confiance == faible -> validation humaine
  "excluded":        [ ... ],   # pertinent == false (audit ; plafonné)
  "duplicates":      [ ... ],   # groupes de doublons détectés
  "daily_synthesis": [ ... ],   # une entrée par jour d'exécution
  "runs":            [ ... ]    # journal des exécutions
}
"""

import json
import os
from datetime import datetime, timezone

DATA_PATH = "data/press_watch.json"
SCHEMA_VERSION = 1
MAX_EXCLUDED = 400          # borne l'historique d'audit
MAX_RUNS = 200


def _empty() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": None,
        "articles": [],
        "queue_review": [],
        "excluded": [],
        "duplicates": [],
        "daily_synthesis": [],
        "runs": [],
    }


def load(path: str = DATA_PATH) -> dict:
    if not os.path.exists(path):
        return _empty()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    base = _empty()
    base.update(data)
    base["schema_version"] = SCHEMA_VERSION
    return base


def _index_by_id(items: list[dict]) -> dict[str, dict]:
    return {it["id"]: it for it in items if "id" in it}


def merge(data: dict, *, articles: list[dict], queue_review: list[dict],
          excluded: list[dict], duplicates: list[dict],
          daily_synthesis: list[dict], run_record: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    data["generated_at"] = now

    # Articles publiés : accumulation, l'existant gagne (on ne réécrit pas un
    # résumé déjà publié), sauf si l'existant était en file de revue.
    idx = _index_by_id(data["articles"])
    for art in articles:
        if art["id"] not in idx:
            data["articles"].append(art)
            idx[art["id"]] = art
    data["articles"].sort(key=lambda a: (a.get("published") or "", a.get("discovered_at") or ""),
                          reverse=True)

    # File de revue : on retire ceux qui ont depuis été publiés, on ajoute les nouveaux.
    published_ids = set(idx)
    qr = _index_by_id(data["queue_review"])
    for art in queue_review:
        if art["id"] not in published_ids:
            qr[art["id"]] = art
    data["queue_review"] = [a for a in qr.values() if a["id"] not in published_ids]
    data["queue_review"].sort(key=lambda a: a.get("discovered_at") or "", reverse=True)

    # Exclus : accumulation plafonnée.
    exc = _index_by_id(data["excluded"])
    for art in excluded:
        exc.setdefault(art["id"], art)
    data["excluded"] = sorted(exc.values(),
                              key=lambda a: a.get("discovered_at") or "", reverse=True)[:MAX_EXCLUDED]

    # Doublons : accumulation (clé = kept + tuple(dropped)).
    seen = {(d["kept"], tuple(sorted(d["dropped"]))) for d in data["duplicates"]}
    for d in duplicates:
        key = (d["kept"], tuple(sorted(d["dropped"])))
        if key not in seen:
            data["duplicates"].append(d)
            seen.add(key)

    # Synthèses : une par date, la dernière exécution du jour écrase.
    by_date = {s["date"]: s for s in data["daily_synthesis"]}
    for s in daily_synthesis:
        by_date[s["date"]] = s
    data["daily_synthesis"] = sorted(by_date.values(), key=lambda s: s["date"], reverse=True)

    data["runs"].append(run_record)
    data["runs"] = data["runs"][-MAX_RUNS:]
    return data


def save(data: dict, path: str = DATA_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def previous_synthesis(data: dict, before_date: str) -> str | None:
    prior = [s for s in data.get("daily_synthesis", []) if s["date"] < before_date]
    if not prior:
        return None
    return max(prior, key=lambda s: s["date"]).get("resume_du_jour")
