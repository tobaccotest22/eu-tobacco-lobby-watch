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
import time
import urllib.parse
import urllib.request

ENTITIES_PATH = "data/entities.json"
OUTPUT_PATH = "data/matches.json"
API_BASE = "https://api2.lobbyfacts.eu/api/1/representative"


def search_lobbyfacts(name: str):
    """Interroge LobbyFacts et renvoie les candidats trouvés pour un nom donné."""
    query = urllib.parse.quote(name)
    url = f"{API_BASE}?q={query}&limit=5"
    req = urllib.request.Request(url, headers={"User-Agent": "eu-tobacco-lobby-watch/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"error": str(exc)}

    results = data.get("results", data if isinstance(data, list) else [])
    candidates = []
    for item in results[:5]:
        # On garde l'objet brut complet pour cette version : la recherche
        # renvoie un identifiant interne LobbyFacts, pas le numero officiel
        # du registre (celui affiche dans les fiches publiques, ex "2427500988-58").
        # On le recupere ici tel quel pour l'identifier precisement a l'etape suivante.
        candidates.append({
            "name_found": item.get("name"),
            "raw": item,
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
