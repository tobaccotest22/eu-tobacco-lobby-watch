"""
Ce script lit data/entities.json (la liste des 49 organisations),
interroge l'API publique de LobbyFacts (https://api2.lobbyfacts.eu)
pour chaque nom d'organisation, et sauvegarde les correspondances
trouvées dans data/matches.json.

Rien n'est modifié automatiquement dans entities.json : ce fichier
matches.json sert juste à vérifier/valider les identifiants avant
de les reporter dans entities.json à l'étape suivante.
"""

import json
import re
import time
import urllib.parse
import urllib.request

ENTITIES_PATH = "data/entities.json"
OUTPUT_PATH = "data/matches.json"
API_BASE = "https://api2.lobbyfacts.eu/api/1/representative"
DATACARD_BASE = "https://www.lobbyfacts.eu/datacard"

# Nombre de candidats a recuperer par recherche. Le nom exact recherche
# n'est pas toujours le resultat le plus "pertinent" pour l'API (ex: BAT
# n'apparaissait qu'en 11e position sur 26 resultats) : on prend une marge
# large pour ne pas rater la bonne entite.
SEARCH_LIMIT = 50
CANDIDATES_KEPT = 10


def slugify(name: str) -> str:
    """Construit un slug approximatif pour l'URL. Le site LobbyFacts identifie
    la fiche via le parametre ?rid=<identification_code> ; le slug n'a pas
    besoin d'etre exact pour que la page se resolve correctement (verifie
    manuellement : une URL avec un slug bidon mais le bon rid affiche la
    bonne fiche)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "entite"


def search_lobbyfacts(name: str):
    """Interroge LobbyFacts et renvoie les candidats trouvés pour un nom donné."""
    query = urllib.parse.quote(name)
    url = f"{API_BASE}?q={query}&limit={SEARCH_LIMIT}"
    req = urllib.request.Request(url, headers={"User-Agent": "eu-tobacco-lobby-watch/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"error": str(exc)}

    results = data.get("results", data if isinstance(data, list) else [])

    # L'API classe les resultats par pertinence, pas par correspondance de nom :
    # la bonne entite peut arriver bien apres la Neme position (ex : British
    # American Tobacco est 11e sur 26 resultats). On garde donc en priorite
    # toute correspondance de nom exacte, puis on complete avec les resultats
    # les plus pertinents jusqu'a CANDIDATES_KEPT.
    exact = [item for item in results if (item.get("name") or "").strip().lower() == name.strip().lower()]
    rest = [item for item in results if item not in exact]
    ordered_items = exact + rest[:max(0, CANDIDATES_KEPT - len(exact))]

    candidates = []
    for item in ordered_items:
        name_found = item.get("name")
        # Le vrai numero officiel du registre de transparence (format
        # "2427500988-58") se trouve dans le champ "identification_code" de
        # l'API - le champ "id" est un hash interne LobbyFacts sans rapport
        # avec le registre public.
        register_id = item.get("identification_code")
        candidates.append({
            "name_found": name_found,
            "register_id": register_id,
            "status": item.get("status"),
            "lobbyfacts_url": (
                f"{DATACARD_BASE}/{slugify(name_found or '')}?rid={register_id}"
                if register_id else None
            ),
        })
    return {"candidates": candidates}


def main():
    with open(ENTITIES_PATH, encoding="utf-8") as f:
        data = json.load(f)

    matches = []
    for entity in data["entities"]:
        name = entity["name"]
        print(f"Recherche : {name}")
        result = search_lobbyfacts(name)
        matches.append({"name": name, "category": entity["category"], **result})
        time.sleep(1)  # on ne surcharge pas l'API

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)

    print(f"\nTerminé. Résultats dans {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
