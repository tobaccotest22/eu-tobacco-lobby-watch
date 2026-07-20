"""
Veille brute des inscriptions au registre de transparence de l'UE mentionnant
tabac/nicotine/vape - tous types d'acteurs confondus, sans tri industrie/santé
publique/autre (cf. limites documentées dans NOTES.md : aucun champ structuré
du registre ne permet de distinguer fiablement un lobby tabac d'une ONG
anti-tabac ou d'un acteur neutre).

Deux sources, combinées dans la même liste accumulée
data/live_data.json._aggregate.new_tobacco_registrants (jamais écrasée, cf.
ec_meetings_outside_our_46 pour le même principe) :

1. Flux quotidien - endpoint public vérifié, sans authentification :
   https://ec.europa.eu/transparencyregister/public/lastestRegistration
   Renvoie les 10 dernières inscriptions au registre, tous secteurs confondus
   (id, name, registrationDate). Comme le tabac/nicotine/vape est un secteur
   mineur du volume total d'inscriptions (~3-6/jour), la plupart des
   exécutions ne remontent aucune correspondance ici - mais dès qu'une
   nouvelle inscription tabac apparaît, elle est détectée le jour même.

2. Recherche mot-clé sur tout l'historique du registre - endpoint de
   recherche public utilisé par l'interface elle-même :
   https://ec.europa.eu/transparencyregister/public/search?queryText=...
   Contrairement au flux quotidien (qui ne voit que les 10 dernières
   inscriptions tous secteurs), cette recherche couvre TOUT l'historique du
   registre et remonte du vrai contenu tabac immédiatement, même vieux de
   plusieurs mois/années. Vérifié manuellement : "tobacco" seul remonte ~154
   résultats sur ~16 pages - trop pour re-scanner à chaque exécution
   nocturne. On ne lance donc cette recherche exhaustive (tous les mots-clés,
   toutes les pages) que tant que l'accumulation est encore pauvre
   (MIN_HISTORY_TARGET) ; une fois ce seuil atteint, elle ne se redéclenche
   plus - le flux quotidien (source 1) prend seul le relais pour les
   nouvelles entrées.

Pour chaque candidat (des deux sources), la date d'inscription est lue sur la
fiche détail de l'organisation (champ "Date d'enregistrement"), sauf pour le
flux quotidien qui la fournit déjà directement.
"""

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from bs4 import BeautifulSoup

# Évite un crash sur les noms d'organisations contenant des caractères que
# l'encodage par défaut de la console (souvent cp1252 sous Windows) ne peut
# pas afficher ; n'affecte pas l'écriture du JSON, toujours en UTF-8.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LIVE_DATA_PATH = "data/live_data.json"
LATEST_REGISTRATIONS_URL = "https://ec.europa.eu/transparencyregister/public/lastestRegistration?lang=fr"
SEARCH_URL = "https://ec.europa.eu/transparencyregister/public/search"
ORG_DETAIL_FRAGMENT = "https://ec.europa.eu/transparencyregister/public/PUBLIC/ORGANISATION/{id}?lang=fr"
REGISTER_PUBLIC_URL = "https://transparency-register.europa.eu/search-register-or-update/organisation-detail_fr?id={id}"
KEYWORDS = ["tobacco", "nicotine", "cigarette", "cigar", "vape", "snus", "tabac"]
USER_AGENT = "Mozilla/5.0 (compatible; eu-tobacco-lobby-watch/0.4)"
REQUEST_TIMEOUT = 20
SLEEP_BETWEEN_REQUESTS = 0.3
MIN_HISTORY_TARGET = 10
MAX_SEARCH_PAGES = 40


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        return response.read()


def fetch_latest_registrations() -> list[dict]:
    return json.loads(http_get(LATEST_REGISTRATIONS_URL))


def fetch_org_detail_fields(org_id: str) -> dict:
    """Lit "Objectifs/mandat" et "Date d'enregistrement" sur la fiche détail."""
    try:
        detail_html = http_get(ORG_DETAIL_FRAGMENT.format(id=org_id)).decode("utf-8")
    except Exception:
        return {"objectives": None, "registration_date": None}

    soup = BeautifulSoup(detail_html, "lxml")
    fields = {"objectives": None, "registration_date": None}
    for row in soup.select("tr.ecl-table__row"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        label_el = cells[0].find("strong")
        if not label_el:
            continue
        label = label_el.get_text(strip=True)

        if "Objectifs" in label and "mandat" in label:
            fields["objectives"] = cells[1].get_text(" ", strip=True)
        elif re.match(r"Date d.enregistrement$", label):
            raw = cells[1].get_text(strip=True)
            match = re.match(r"(\d{2})/(\d{2})/(\d{4})", raw)
            if match:
                day, month, year = match.groups()
                fields["registration_date"] = f"{year}-{month}-{day}"

    return fields


def matches_keywords(text: str | None) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(keyword in lower for keyword in KEYWORDS)


def fetch_search_page(query_text: str, page: int) -> tuple[list[dict], bool]:
    url = f"{SEARCH_URL}?lang=fr&queryText={urllib.parse.quote(query_text)}&page={page}"
    try:
        page_html = http_get(url).decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"    échec page {page} pour '{query_text}' : {exc}")
        return [], False

    soup = BeautifulSoup(page_html, "lxml")
    results = []
    for article in soup.select("article.ecl-content-item"):
        link = article.select_one("a.ecl-link")
        label = article.select_one(".ecl-link__label")
        if not link or not label:
            continue
        match = re.search(r"id=([^&]+)", link.get("href") or "")
        if not match:
            continue
        results.append({"id": match.group(1), "name": html.unescape(label.get_text(strip=True))})

    has_next = any(a.get_text(strip=True) == "Suivant" for a in soup.select("a"))
    return results, has_next


def fetch_all_search_results(query_text: str) -> list[dict]:
    """Parcourt toutes les pages de résultats pour un mot-clé donné."""
    all_results = []
    page = 1
    while page <= MAX_SEARCH_PAGES:
        results, has_next = fetch_search_page(query_text, page)
        all_results.extend(results)
        if not has_next or not results:
            break
        page += 1
        time.sleep(SLEEP_BETWEEN_REQUESTS)
    return all_results


def main():
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

    # 1. Flux quotidien : 10 dernières inscriptions tous secteurs, filtrées par mot-clé.
    print("Téléchargement des dernières inscriptions au registre de transparence...")
    latest = fetch_latest_registrations()
    print(f"{len(latest)} inscriptions récentes récupérées (tous secteurs confondus)")

    for candidate in latest:
        org_id = candidate.get("id")
        name = html.unescape(candidate.get("name") or "")
        if not org_id or org_id in existing_ids:
            continue

        matched_via = None
        if matches_keywords(name):
            matched_via = "nom"
        else:
            fields = fetch_org_detail_fields(org_id)
            if matches_keywords(fields["objectives"]):
                matched_via = "objet déclaré"

        if matched_via:
            print(f"  [flux quotidien] Correspondance ({matched_via}) : {name}")
            existing_ids.add(org_id)
            new_matches.append({
                "id": org_id,
                "name": name,
                "registration_date": candidate.get("registrationDate"),
                "register_url": REGISTER_PUBLIC_URL.format(id=org_id),
                "matched_via": matched_via,
                "detected_at": now,
            })

    # 2. Recherche mot-clé sur tout l'historique, tant que l'accumulation est pauvre.
    if len(existing_ids) < MIN_HISTORY_TARGET:
        print(f"\nStock actuel ({len(existing_ids)}) sous le seuil ({MIN_HISTORY_TARGET}) : "
              f"recherche mot-clé sur tout l'historique du registre...")
        for keyword in KEYWORDS:
            print(f"  Recherche '{keyword}'...")
            results = fetch_all_search_results(keyword)
            print(f"    {len(results)} résultat(s)")
            for r in results:
                org_id = r["id"]
                if org_id in existing_ids:
                    continue
                existing_ids.add(org_id)
                fields = fetch_org_detail_fields(org_id)
                time.sleep(SLEEP_BETWEEN_REQUESTS)

                # Le moteur de recherche du registre indexe des champs bien
                # plus larges que le nom/objet (ex: listes de propositions
                # législatives suivies), ce qui remonte des organisations
                # sans rapport réel avec le tabac (une chambre médicale, un
                # groupe de distribution...). On revérifie donc nous-mêmes
                # sur nom + objet déclaré, comme pour le flux quotidien.
                if not (matches_keywords(r["name"]) or matches_keywords(fields["objectives"])):
                    continue

                print(f"    Correspondance (recherche historique '{keyword}') : {r['name']}")
                new_matches.append({
                    "id": org_id,
                    "name": r["name"],
                    "registration_date": fields["registration_date"],
                    "register_url": REGISTER_PUBLIC_URL.format(id=org_id),
                    "matched_via": f"recherche historique ({keyword})",
                    "detected_at": now,
                })
    else:
        print(f"\nStock actuel ({len(existing_ids)}) au-dessus du seuil ({MIN_HISTORY_TARGET}) : "
              "recherche historique ignorée, le flux quotidien suffit désormais.")

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
