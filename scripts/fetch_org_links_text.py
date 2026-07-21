"""
Étape 1 de l'exploration des liens entre organisations : pour chacune des 48
organisations de data/entities.json, va chercher sur sa fiche officielle du
registre de transparence (transparency-register.europa.eu) le texte brut de
trois champs qui ne sont PAS dans nos données actuelles :

1. "Liste des associations, (con)fédérations, réseaux et autres organismes
   dont vous faites partie"
2. "Liste des membres et organisations affiliées/partenaires"
3. "Intermédiaires pendant l'exercice en cours"

Réutilise le même endpoint fragment HTML que scripts/fetch_lobbyfacts.py
(REGISTER_DETAIL_FRAGMENT), déjà validé en production pour lire budget/
personnes/cabinets sur la même page.

Ce script ne fait AUCUN traitement/nettoyage : il écrit juste le texte brut
(ou null si le champ est absent/"N/A") par organisation dans
data/raw_links_text.json. Le nettoyage du bruit et la détection de
candidats de liens sont faits dans un second temps par
scripts/analyze_org_links.py, une fois ce fichier généré.

Les libellés officiels contiennent des caractères accentués qui se
corrompent selon l'environnement (apostrophes/accents) : comme dans
fetch_lobbyfacts.py, on matche sur des sous-chaînes ASCII stables plutôt
que sur le libellé exact.
"""

import json
import time
import urllib.request

from bs4 import BeautifulSoup

ENTITIES_PATH = "data/entities.json"
OUTPUT_PATH = "data/raw_links_text.json"
REGISTER_DETAIL_FRAGMENT = "https://ec.europa.eu/transparencyregister/public/PUBLIC/ORGANISATION/{register_id}?lang=fr"
USER_AGENT = "eu-tobacco-lobby-watch/0.3"
REQUEST_TIMEOUT = 20
SLEEP_BETWEEN_REQUESTS = 1


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        return response.read()


def extract_cell_text(value_cell) -> str | None:
    """Texte brut d'une cellule de la fiche registre, ou None si vide/"N/A"."""
    text = value_cell.get_text("\n", strip=True)
    text = text.strip()
    if not text or text.upper() == "N/A":
        return None
    return text


def parse_links_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    fields = {
        "associations_networks": None,
        "members_affiliates": None,
        "intermediaries_current_year": None,
    }
    for row in soup.select("tr.ecl-table__row"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        label_el = cells[0].find("strong")
        if not label_el:
            continue
        label = label_el.get_text(strip=True)
        value_cell = cells[1]

        if "associations" in label and "organismes" in label:
            fields["associations_networks"] = extract_cell_text(value_cell)
        elif "membres et organisations" in label:
            fields["members_affiliates"] = extract_cell_text(value_cell)
        elif "exercice en cours" in label and "Interm" in label:
            fields["intermediaries_current_year"] = extract_cell_text(value_cell)

    return fields


def fetch_org_links_text(register_id: str) -> dict:
    url = REGISTER_DETAIL_FRAGMENT.format(register_id=register_id)
    try:
        html = http_get(url).decode("utf-8")
    except Exception as exc:
        return {"error": f"fiche registre echouee : {exc}"}

    try:
        return parse_links_fields(html)
    except Exception as exc:
        return {"error": f"lecture fiche registre echouee : {exc}"}


def main():
    with open(ENTITIES_PATH, encoding="utf-8") as f:
        entities = json.load(f)["entities"]

    result = {
        "computed_at": None,
        "organisations": {},
    }

    from datetime import datetime, timezone

    for entity in entities:
        register_id = entity.get("register_id")
        name = entity["name"]
        if not register_id:
            print(f"(pas de register_id, ignore) {name}")
            continue

        print(f"Extraction liens : {name} ({register_id})")
        fields = fetch_org_links_text(register_id)
        result["organisations"][register_id] = {
            "name": name,
            "register_url": entity.get("register_url"),
            **fields,
        }
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    result["computed_at"] = datetime.now(timezone.utc).isoformat()

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Ecrit {len(result['organisations'])} organisations dans {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
