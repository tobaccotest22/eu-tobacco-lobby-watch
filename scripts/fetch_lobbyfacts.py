"""
Pour chaque organisation de data/entities.json ayant un register_id, ce script
récupère deux choses et les écrit dans data/live_data.json :

1. Un instantané LobbyFacts (statut, ETP/personnes déclarées) via
   https://api2.lobbyfacts.eu/api/1/representative. ATTENTION : les données
   LobbyFacts ne sont plus mises à jour depuis ~mars 2022 (vérifié sur
   plusieurs organisations lors du développement) — ce n'est donc qu'un
   instantané historique, pas une donnée "live". LobbyFacts n'expose par
   ailleurs aucun champ budget/cabinets : ces valeurs restent celles saisies
   manuellement dans data/entities.json.

2. La vraie liste des réunions avec des membres de la Commission (Commissaires,
   cabinets, Directeurs généraux, et depuis le 1/1/2025 le personnel
   d'encadrement) via le PDF officiel et à jour du registre de transparence :
   https://ec.europa.eu/transparencyregister/public/meetings/{register_id}/pdf
   Ce PDF est régénéré à la demande par la Commission (contrairement à
   LobbyFacts) et contient des réunions jusqu'à la date du jour.

3. Le budget annuel déclaré, le nombre de personnes concernées et la liste
   des cabinets/consultants sous-traitants pour l'exercice en cours, lus
   directement sur la fiche officielle du registre de transparence
   (transparency-register.europa.eu). Cette page Drupal est statique mais
   injecte son contenu principal via un fetch JS vers un fragment HTML ;
   ce fragment (endpoint trouvé dans son bundle JS) est directement
   accessible et c'est celui-ci que le script interroge.

Le script fusionne ses résultats dans data/live_data.json sans écraser la
partie "ep_meetings" qu'écrit scripts/fetch_ep_meetings.py.
"""

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from io import BytesIO

from bs4 import BeautifulSoup
from pypdf import PdfReader

ENTITIES_PATH = "data/entities.json"
LIVE_DATA_PATH = "data/live_data.json"
LOBBYFACTS_API = "https://api2.lobbyfacts.eu/api/1/representative"
EC_MEETINGS_PDF = "https://ec.europa.eu/transparencyregister/public/meetings/{register_id}/pdf"
REGISTER_DETAIL_FRAGMENT = "https://ec.europa.eu/transparencyregister/public/PUBLIC/ORGANISATION/{register_id}?lang=fr"
SINCE_DATE = "2025-01-01"
USER_AGENT = "eu-tobacco-lobby-watch/0.3"
REQUEST_TIMEOUT = 20
SLEEP_BETWEEN_REQUESTS = 1


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        return response.read()


def fetch_lobbyfacts_snapshot(register_id: str) -> dict | None:
    """Résout le register_id en id interne LobbyFacts puis récupère la fiche complète."""
    query = urllib.parse.quote(register_id)
    search_url = f"{LOBBYFACTS_API}?q={query}&limit=5"
    try:
        search_data = json.loads(http_get(search_url))
    except Exception as exc:
        return {"error": f"recherche LobbyFacts échouée : {exc}"}

    match = next(
        (r for r in search_data.get("results", []) if r.get("identification_code") == register_id),
        None,
    )
    if match is None:
        return None

    try:
        detail = json.loads(http_get(f"{LOBBYFACTS_API}/{match['id']}"))
    except Exception as exc:
        return {"error": f"détail LobbyFacts échoué : {exc}"}

    return {
        "status": detail.get("status"),
        "members": detail.get("members"),
        "members_fte": detail.get("members_fte"),
        "members_25": detail.get("members_25"),
        "members_50": detail.get("members_50"),
        "members_75": detail.get("members_75"),
        "members_100": detail.get("members_100"),
        "snapshot_date": detail.get("last_update_date"),
        "lobbyfacts_url": f"https://www.lobbyfacts.eu/datacard/x?rid={register_id}",
    }


def parse_ec_meetings_pdf(pdf_bytes: bytes) -> list[dict]:
    """Extrait les réunions (date, représentant/DG, lieu+sujet) du PDF officiel du registre."""
    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() for page in reader.pages)

    # On coupe la partie légale de fin et l'en-tête du tableau.
    text = text.split("References")[0]
    header_match = re.search(r"Subject\(s\)", text)
    if header_match:
        text = text[header_match.end():]

    # Chaque réunion commence par son numéro séquentiel (1, 2, 3, ...).
    positions = [(m.start(), int(m.group(1))) for m in re.finditer(r"(?:^|\n)\s*(\d{1,3})\s", text)]
    entry_starts = []
    expected = 1
    for pos, num in positions:
        if num == expected:
            entry_starts.append(pos)
            expected += 1
    entry_starts.append(len(text))

    meetings = []
    for i in range(len(entry_starts) - 1):
        chunk = text[entry_starts[i]:entry_starts[i + 1]]
        chunk = re.sub(r"^\s*\d{1,3}\s", "", chunk, count=1)
        date_match = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", chunk)
        if not date_match:
            continue
        day, month, year = date_match.groups()
        representative = re.sub(r"-\s+", "-", chunk[:date_match.start()])
        representative = re.sub(r"\s+", " ", representative).strip().strip(",")
        details = re.sub(r"\s+", " ", chunk[date_match.end():]).strip()
        meetings.append({
            "date": f"{year}-{month}-{day}",
            "representative_or_dg": representative,
            "location_and_subject": details,
        })
    return meetings


def fetch_ec_meetings(register_id: str) -> dict | None:
    url = EC_MEETINGS_PDF.format(register_id=register_id)
    try:
        pdf_bytes = http_get(url)
    except Exception as exc:
        return {"error": f"PDF réunions EC échoué : {exc}"}

    try:
        meetings = parse_ec_meetings_pdf(pdf_bytes)
    except Exception as exc:
        return {"error": f"lecture PDF réunions EC échouée : {exc}"}

    since = [m for m in meetings if m["date"] >= SINCE_DATE]
    return {
        "source_pdf_url": url,
        "total_all_time_count": len(meetings),
        "since_2025_count": len(since),
        "since_2025": since,
    }


def parse_amount(text: str) -> int | None:
    digits = text.replace("\xa0", "").replace(" ", "").replace(" ", "").replace("€", "").strip()
    return int(digits) if digits.isdigit() else None


def parse_register_detail(html: str) -> dict:
    """Lit budget/personnes/cabinets sur le fragment HTML de la fiche du registre.

    Les libellés officiels contiennent des accents ("coûts", "personnes
    concernées") ; on matche sur des sous-chaînes stables pour éviter tout
    souci d'encodage entre environnements.
    """
    soup = BeautifulSoup(html, "lxml")
    fields = {
        "people_involved": None,
        "nb_intermediaries": None,
        "intermediaries_current_year": [],
        "budget_low": None,
        "budget_high": None,
    }
    for row in soup.select("tr.ecl-table__row"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        label_el = cells[0].find("strong")
        if not label_el:
            continue
        label = label_el.get_text(strip=True).rstrip(":")
        value_cell = cells[1]

        if "personnes" in label and "total" in label:
            txt = value_cell.get_text(strip=True)
            fields["people_involved"] = int(txt) if txt.isdigit() else None

        elif "exercice en cours" in label and "Interm" in label:
            names = [td.get_text(strip=True) for td in value_cell.select("tbody td") if td.get_text(strip=True)]
            fields["nb_intermediaries"] = len(names)
            fields["intermediaries_current_year"] = names

        elif "co" in label and "ts annuels" in label:
            nums = [parse_amount(s.get_text()) for s in value_cell.select("span > span")]
            nums = [n for n in nums if n is not None]
            if len(nums) >= 2:
                fields["budget_low"], fields["budget_high"] = nums[0], nums[1]
            elif len(nums) == 1:
                fields["budget_low"] = fields["budget_high"] = nums[0]

    return fields


def fetch_register_detail(register_id: str) -> dict | None:
    url = REGISTER_DETAIL_FRAGMENT.format(register_id=register_id)
    try:
        html = http_get(url).decode("utf-8")
    except Exception as exc:
        return {"error": f"fiche registre échouée : {exc}"}

    try:
        return parse_register_detail(html)
    except Exception as exc:
        return {"error": f"lecture fiche registre échouée : {exc}"}


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

        print(f"LobbyFacts + réunions EC + fiche registre : {name} ({register_id})")
        entry = live_data.setdefault(register_id, {"name": name, "register_id": register_id})
        entry["name"] = name
        entry["lobbyfacts"] = fetch_lobbyfacts_snapshot(register_id)
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        entry["ec_meetings"] = fetch_ec_meetings(register_id)
        time.sleep(SLEEP_BETWEEN_REQUESTS)

        register_detail = fetch_register_detail(register_id) or {}
        if "error" in register_detail:
            entry["register_detail_error"] = register_detail["error"]
        else:
            entry["budget_low"] = register_detail.get("budget_low")
            entry["budget_high"] = register_detail.get("budget_high")
            entry["people_involved"] = register_detail.get("people_involved")
            entry["nb_intermediaries"] = register_detail.get("nb_intermediaries")
            entry["intermediaries_current_year"] = register_detail.get("intermediaries_current_year")

        entry["lobbyfacts_last_fetched"] = now
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    with open(LIVE_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(live_data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\nTerminé. Résultats fusionnés dans {LIVE_DATA_PATH}")


if __name__ == "__main__":
    main()
