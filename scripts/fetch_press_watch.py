"""
Pipeline de la section « Veille - Presse » — orchestrateur (étape du workflow).

Chaîne : découverte (Google News RSS + flux directs) -> résolution des liens
-> extraction du texte visible -> classification (prompt section 1) -> file de
revue / exclusions -> dédoublonnage (entites_citees, section 2) -> synthèse du
jour (section 7) -> écriture accumulée data/press_watch.json.

Modes :
  (défaut)                 exécution nocturne : classification + synthèse via API
                           Claude (ANTHROPIC_API_KEY), écrit data/press_watch.json
  --backfill-days N        traite les N derniers jours (test / rattrapage) au
                           lieu du seul jour courant
  --dry-run                n'écrit pas data/press_watch.json (écrit
                           data/press_watch.dryrun.json) et ne commite rien
  --no-llm                 aucun appel API ; sans --classifications, s'arrête
                           après extraction en écrivant le fichier de candidats
  --classifications FILE   rejoue des classifications produites à la main
                           (clé "classifications" indexée par id d'article)
  --synthesis FILE         idem pour les synthèses (clé "synthesis" par date ISO)
  --report FILE            écrit un rapport Markdown détaillé de l'exécution
  --candidates FILE        chemin du dump de candidats en mode --no-llm

Le workflow GitHub (.github/workflows/press_watch.yml) reste en dispatch manuel
+ --dry-run tant que la section n'a pas été validée.
"""

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone, date

sys.path.insert(0, "scripts")

from press_watch import feeds, resolve, extract, dedupe, store
from press_watch.sources import GOOGLE_NEWS_QUERIES, DIRECT_FEEDS, topic_prefilter
from press_watch import classify as classify_mod
from press_watch import synthesize as synth_mod
from press_watch.report import write_report

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _article_id(url: str, title: str, published: str | None) -> str:
    basis = (url or "").strip().lower().rstrip("/")
    if not basis:
        basis = f"{title}|{published}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _clean_source_name(name: str) -> str:
    name = (name or "").strip().strip("-").strip()
    return re.sub(r"\s+", " ", name)


def _clean_title(title: str, source_name: str) -> str:
    """Google News suffixe les titres de « - <média> ». On retire ce suffixe
    quand il correspond à la source connue, pour l'affichage et l'id."""
    title = (title or "").strip()
    if source_name:
        for sep in (" - ", " | ", " – ", " — "):
            suffix = f"{sep}{source_name}"
            if title.endswith(suffix):
                return title[: -len(suffix)].strip()
    # suffixe générique « - Quelque Chose » en toute fin (média non identifié)
    m = re.match(r"^(.*\S)\s+[-–—|]\s+[A-Z][\w.& ]{1,30}$", title)
    return m.group(1).strip() if m else title


def _canonical_url(url: str) -> str:
    # retire les paramètres de tracking usuels pour stabiliser l'id
    from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
    try:
        p = urlparse(url)
    except ValueError:
        return url
    drop = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "fbclid", "gclid", "ref", "cmpid", "at_medium", "at_campaign"}
    q = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in drop]
    return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), p.params,
                       urlencode(q), ""))


# --------------------------------------------------------------------------
# 1. Découverte
# --------------------------------------------------------------------------

def discover(since: date, until: date, log: list) -> tuple[list[dict], list[dict]]:
    """Renvoie (entrées retenues, journal des flux)."""
    feed_log = []
    raw_entries: list[feeds.FeedEntry] = []

    for feed in DIRECT_FEEDS:
        if not feed.get("active", True):
            continue
        entries, err = feeds.load_feed(feed["url"], feed_lang=feed["lang"],
                                       feed_label=feed["name"])
        feed_log.append({"type": "flux direct", "name": feed["name"], "url": feed["url"],
                         "entries": len(entries), "error": err})
        if err:
            log.append(f"[flux direct] {feed['name']} : {err}")
        raw_entries.extend(entries)

    for gq in GOOGLE_NEWS_QUERIES:
        entries, err = feeds.load_feed(gq["url"], feed_lang=gq["lang"],
                                       feed_label=f"Google News [{gq['lang']}]")
        feed_log.append({"type": "google news", "name": f"GN {gq['lang']}: {gq['query'][:70]}…",
                         "url": gq["url"], "entries": len(entries), "error": err})
        if err:
            log.append(f"[google news {gq['lang']}] {err}")
        raw_entries.extend(entries)

    # fenêtre de dates (entrées sans date conservées, retriées après extraction)
    windowed = [e for e in raw_entries if feeds.in_window(e, since, until)]

    # résolution des liens + dédoublonnage par URL
    by_url: dict[str, dict] = {}
    unresolved = 0
    for e in windowed:
        r = resolve.resolve(e.link)
        if not r["resolved"]:
            unresolved += 1
        url = _canonical_url(r["url"])
        src = _clean_source_name(e.source_name or e.feed_label)
        rec = by_url.get(url)
        if rec is None:
            by_url[url] = {
                "url": url,
                "title": _clean_title(e.title, src),
                "source_name": src,
                "lang": e.feed_lang,
                "published": e.published.isoformat() if e.published else None,
                "summary": e.summary,
                "feed_labels": {e.feed_label},
                "resolve_method": r["method"],
                "url_resolved": r["resolved"],
                "resolve_note": r["note"],
            }
        else:
            rec["feed_labels"].add(e.feed_label)
            if (not rec["source_name"] or rec["source_name"].startswith("Google News")) and e.source_name:
                rec["source_name"] = src
            if not rec["published"] and e.published:
                rec["published"] = e.published.isoformat()

    log.append(f"Découverte : {len(raw_entries)} entrées brutes, {len(windowed)} dans la "
               f"fenêtre {since}→{until}, {len(by_url)} URL uniques, {unresolved} liens non résolus.")

    # pré-filtre thématique léger
    kept, dropped = [], []
    for rec in by_url.values():
        rec["feed_labels"] = sorted(rec["feed_labels"])
        blob = f"{rec['title']} {rec['summary']}"
        (kept if topic_prefilter(blob) else dropped).append(rec)
    log.append(f"Pré-filtre thématique : {len(kept)} candidats retenus, "
               f"{len(dropped)} écartés (aucun mot-clé du dossier).")
    return kept, {"feeds": feed_log, "prefiltered_out":
                  [{"title": d["title"], "source": d["source_name"], "url": d["url"]} for d in dropped]}


# --------------------------------------------------------------------------
# 2. Extraction
# --------------------------------------------------------------------------

def enrich_with_text(candidates: list[dict], log: list) -> list[dict]:
    out = []
    now = datetime.now(timezone.utc).isoformat()
    for rec in candidates:
        ext = extract.extract_article(rec["url"])
        published = rec["published"]
        art = {
            **rec,
            "final_url": ext["final_url"],
            "site_name": ext["site_name"],
            "meta_description": ext["meta_description"],
            "text": ext["text"],
            "text_len": ext["text_len"],
            "paywalled": ext["paywalled"],
            "paywall_reason": ext["paywall_reason"],
            "http_status": ext["http_status"],
            "fetch_error": ext["fetch_error"],
            "published": published,
            "discovered_at": now,
        }
        art["id"] = _article_id(_canonical_url(ext["final_url"] or rec["url"]),
                                rec["title"], published)
        if ext["fetch_error"]:
            log.append(f"[extraction] {rec['source_name'] or rec['url']} : {ext['fetch_error']}")
        out.append(art)
    return out


# --------------------------------------------------------------------------
# 3. Classification + partition
# --------------------------------------------------------------------------

def classify_all(articles: list[dict], classifier, log: list) -> list[dict]:
    for art in articles:
        try:
            c = classifier.classify(art)
        except Exception as exc:
            log.append(f"[classification] échec sur {art['title']!r} : {exc}")
            art["classification_error"] = str(exc)
            art["classified"] = None
            continue
        art["classified"] = c.to_json()
        art["schema_warnings"] = c.schema_warnings
        if c.schema_warnings:
            log.append(f"[schéma] {art['title'][:60]!r} : {'; '.join(c.schema_warnings)}")
    return articles


def partition(articles: list[dict]):
    published, review, excluded, errored = [], [], [], []
    for art in articles:
        c = art.get("classified")
        if c is None:
            errored.append(art)
            continue
        if not c["pertinent"]:
            excluded.append(art)
        elif c["confiance"] == "faible":
            review.append(art)
        else:
            published.append(art)
    return published, review, excluded, errored


def _public_record(art: dict) -> dict:
    c = art["classified"]
    return {
        "id": art["id"],
        "url": art.get("final_url") or art["url"],
        "title": art["title"],
        "source_name": art.get("source_name") or art.get("site_name") or "",
        "lang": c["langue_source"],
        "published": art.get("published"),
        "discovered_at": art.get("discovered_at"),
        "angle": c["angle"],
        "resume": c["resume"],
        "source_type": c["source_type"],
        "sous_abonnement": c["sous_abonnement"],
        "confiance": c["confiance"],
        "entites_citees": c["entites_citees"],
    }


def _excluded_record(art: dict) -> dict:
    c = art["classified"]
    return {
        "id": art["id"], "url": art.get("final_url") or art["url"], "title": art["title"],
        "source_name": art.get("source_name") or art.get("site_name") or "",
        "published": art.get("published"), "discovered_at": art.get("discovered_at"),
        "source_type": c["source_type"], "confiance": c["confiance"],
        "raison_exclusion": c["raison_exclusion"],
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backfill-days", type=int, default=1)
    ap.add_argument("--since", type=str, help="AAAA-MM-JJ (prioritaire sur --backfill-days)")
    ap.add_argument("--until", type=str, help="AAAA-MM-JJ (défaut : aujourd'hui)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--classifications", type=str)
    ap.add_argument("--synthesis", type=str)
    ap.add_argument("--report", type=str)
    ap.add_argument("--candidates", type=str, default="data/press_watch_candidates.json")
    ap.add_argument("--from-candidates", type=str,
                    help="repart d'un dump de candidats (--no-llm) au lieu de refaire "
                         "la découverte + l'extraction ; utile pour rejouer la "
                         "classification sans re-crawler")
    ap.add_argument("--data-path", type=str, default=store.DATA_PATH)
    args = ap.parse_args()

    today = datetime.now(timezone.utc).date()
    until = date.fromisoformat(args.until) if args.until else today
    if args.since:
        since = date.fromisoformat(args.since)
    else:
        since = until - timedelta(days=max(0, args.backfill_days - 1))

    log: list[str] = []
    print(f"Fenêtre : {since} → {until}")

    if args.from_candidates:
        with open(args.from_candidates, encoding="utf-8") as f:
            dump = json.load(f)
        articles = dump["articles"]
        discovery_meta = dump.get("discovery", {"feeds": [], "prefiltered_out": []})
        log.extend(dump.get("log", []))
        log.append(f"Repris depuis {args.from_candidates} : {len(articles)} candidats "
                   f"(pas de nouvelle découverte).")
    else:
        candidates, discovery_meta = discover(since, until, log)
        articles = enrich_with_text(candidates, log)

    # -- mode dump candidats (pas de classification disponible) --------------
    if args.no_llm and not args.classifications:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window": {"since": since.isoformat(), "until": until.isoformat()},
            "articles": articles,
            "discovery": discovery_meta,
            "log": log,
        }
        with open(args.candidates, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"\n{len(articles)} candidats écrits dans {args.candidates} "
              f"(mode --no-llm sans --classifications).")
        for line in log:
            print("  -", line)
        return

    # -- classifieur / synthétiseur ---------------------------------------
    if args.classifications:
        classifier = classify_mod.ManualClassifier(args.classifications)
        synth_path = args.synthesis or args.classifications
        synthesizer = synth_mod.ManualSynthesizer(synth_path)
        manual = True
    else:
        from press_watch.llm import AnthropicClient
        client = AnthropicClient()
        classifier = classify_mod.ApiClassifier(client)
        synthesizer = synth_mod.ApiSynthesizer(client)
        manual = False

    articles = classify_all(articles, classifier, log)
    published, review, excluded, errored = partition(articles)
    log.append(f"Classification : {len(published)} publiables, {len(review)} en revue "
               f"(confiance faible), {len(excluded)} exclus, {len(errored)} en erreur.")

    # -- dédoublonnage (pool publiable + articles déjà stockés dans la fenêtre)
    existing = store.load(args.data_path)
    existing_in_window = [
        a for a in existing["articles"]
        if a.get("published") and since.isoformat() <= a["published"] <= until.isoformat()
    ]
    pub_records = [_public_record(a) for a in published]
    dupe_input = pub_records + [dict(a, _existing=True) for a in existing_in_window]
    dup_groups = dedupe.find_duplicates(dupe_input)

    dropped_ids = {d for g in dup_groups for d in g["dropped"]}
    kept_records = [r for r in pub_records if r["id"] not in dropped_ids]
    log.append(f"Dédoublonnage : {len(dup_groups)} groupe(s) de doublons, "
               f"{len(dropped_ids)} article(s) écarté(s).")

    # File de revue : dédoublonnage interne aussi (évite 3-4 entrées quasi
    # identiques à valider une par une), mais on ne fusionne pas revue et
    # publiables — un article incertain ne doit pas disparaître derrière un
    # publié.
    review_records = [_public_record(a) | {"schema_warnings": a.get("schema_warnings", [])}
                      for a in review]
    review_dups = dedupe.find_duplicates(review_records)
    review_dropped = {d for g in review_dups for d in g["dropped"]}
    review_records = [r for r in review_records if r["id"] not in review_dropped]
    if review_dropped:
        log.append(f"File de revue : {len(review_dropped)} doublon(s) interne(s) fusionné(s).")

    # -- synthèse par jour ---------------------------------------------------
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in kept_records:
        by_day[r["published"] or until.isoformat()].append(r)

    daily = []
    day_list = [since + timedelta(days=i) for i in range((until - since).days + 1)]
    prev_resume = None  # synthèse du jour précédent calculée dans CE run (backfill)
    for d in day_list:
        di = d.isoformat()
        day_articles = by_day.get(di, [])
        resume_hier = prev_resume or store.previous_synthesis(existing, di)
        if manual:
            s = synthesizer.synthesize(day_articles, resume_hier, day=di)
        else:
            s = synthesizer.synthesize(day_articles, resume_hier)
        prev_resume = s["resume_du_jour"]
        daily.append({
            "date": di,
            "type": s["type"],
            "resume_du_jour": s["resume_du_jour"],
            "articles_source": s["articles_source"],
            "api_called": s.get("api_called", not manual),
            "n_articles": len(day_articles),
        })

    # -- écriture -----------------------------------------------------------
    run_record = {
        "date": datetime.now(timezone.utc).isoformat(),
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "mode": "manuel" if manual else "api",
        "dry_run": args.dry_run,
        "counts": {
            "candidats": len(articles), "publies": len(kept_records),
            "revue": len(review_records), "exclus": len(excluded),
            "erreurs": len(errored), "doublons_ecartes": len(dropped_ids),
        },
    }
    merged = store.merge(
        existing,
        articles=kept_records,
        queue_review=review_records,
        excluded=[_excluded_record(a) for a in excluded],
        duplicates=dup_groups,
        daily_synthesis=daily,
        run_record=run_record,
    )

    out_path = "data/press_watch.dryrun.json" if args.dry_run else args.data_path
    store.save(merged, out_path)
    print(f"\nÉcrit : {out_path}")
    for line in log:
        print("  -", line)

    if args.report:
        write_report(args.report, window=(since, until), articles=articles,
                     published=published, review_records=review_records, excluded=excluded,
                     errored=errored, dup_groups=dup_groups, dropped_ids=dropped_ids,
                     daily=daily, discovery_meta=discovery_meta, log=log,
                     manual=manual, dry_run=args.dry_run)
        print(f"Rapport : {args.report}")


if __name__ == "__main__":
    main()
