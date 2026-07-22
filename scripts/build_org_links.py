"""
Convertit data/link_candidates_draft.json (brouillon d'audit, avec preuves et
notes de methode) en data/org_links.json (donnees propres consommees par le
graphe D3 de index.html : liste de noeuds et de liens uniques).

Ne prend que "clear_candidates" (les cas encore dans "ambiguous_cases", comme
France Vapotage, sont volontairement exclus tant qu'ils ne sont pas tranches).

Deux entrees de clear_candidates qui decrivent la meme relation vue des deux
cotes (ex: "Mesa Del Tobacco -> Logista" et "Logista -> Mesa Del Tobacco")
sont fusionnees en un seul lien nom-oriente, en conservant toutes les preuves.

Le style de trait ("style") est determine par priorite : "dotted" des qu'un
cabinet de lobbying commun est implique (meme quand l'organisation partage
par ailleurs un lien d'association confirme - le partage de cabinet reste
l'information la plus notable a distinguer visuellement) ; sinon "solid" des
qu'au moins un cote vient du registre officiel ; sinon "dashed" (verification
externe uniquement). Le champ "source_type" liste en revanche TOUTES les
methodes ayant contribue au lien, meme quand le style visuel n'en retient
qu'une - le detail complet reste visible au clic dans le panneau du site.

A relancer avec `python scripts/build_org_links.py` a chaque fois que
data/link_candidates_draft.json change (nouvelle validation, cas ambigu
tranche, etc.).
"""

import json
import re

ENTITIES_PATH = "data/entities.json"
CANDIDATES_PATH = "data/link_candidates_draft.json"
OUTPUT_PATH = "data/org_links.json"


def short_label(name: str) -> str:
    """Coupe l'annotation entre parentheses en fin de nom pour l'affichage graphe."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def main():
    entities = json.load(open(ENTITIES_PATH, encoding="utf-8"))["entities"]
    candidates = json.load(open(CANDIDATES_PATH, encoding="utf-8"))["clear_candidates"]

    entity_by_id = {e["register_id"]: e for e in entities if e.get("register_id")}

    edges = {}
    for c in candidates:
        pair = tuple(sorted([c["source_id"], c["target_id"]]))
        entry = edges.setdefault(pair, {
            "source": pair[0],
            "target": pair[1],
            "link_types": [],
            "has_registre_officiel": False,
            "has_verification_externe": False,
            "has_cabinet_commun": False,
            "evidence": [],
        })
        entry["link_types"].append(c["link_type"])
        if "registre_officiel" in c["source_type"]:
            entry["has_registre_officiel"] = True
        if "verification_externe" in c["source_type"]:
            entry["has_verification_externe"] = True
        if "cabinet_commun" in c["source_type"]:
            entry["has_cabinet_commun"] = True
        entry["evidence"].extend(c.get("evidence") or [])
        for ext in c.get("external_sources") or []:
            entry["evidence"].append({"org": None, "field": "verification_externe", "text": ext["description"], "url": ext["url"]})

    links = []
    node_ids = set()
    for (source_id, target_id), entry in edges.items():
        node_ids.add(source_id)
        node_ids.add(target_id)

        if entry["has_cabinet_commun"]:
            style = "dotted"
        elif entry["has_registre_officiel"]:
            style = "solid"
        else:
            style = "dashed"

        source_types = []
        if entry["has_registre_officiel"]:
            source_types.append("registre_officiel")
        if entry["has_verification_externe"]:
            source_types.append("verification_externe")
        if entry["has_cabinet_commun"]:
            source_types.append("cabinet_commun")

        links.append({
            "source": source_id,
            "target": target_id,
            "link_type": "; ".join(dict.fromkeys(entry["link_types"])),
            "style": style,
            "source_type": " + ".join(source_types),
            "evidence": entry["evidence"],
        })

    degree = {}
    for link in links:
        degree[link["source"]] = degree.get(link["source"], 0) + 1
        degree[link["target"]] = degree.get(link["target"], 0) + 1

    nodes = []
    for register_id in sorted(node_ids):
        entity = entity_by_id.get(register_id, {})
        name = entity.get("name", register_id)
        nodes.append({
            "id": register_id,
            "name": name,
            "label": short_label(name),
            "section": (entity.get("section") or "").strip(),
            "degree": degree.get(register_id, 0),
        })

    seen_isolated_ids = set()
    isolated = []
    for e in entities:
        register_id = e.get("register_id")
        if not register_id or register_id in node_ids or register_id in seen_isolated_ids:
            continue
        seen_isolated_ids.add(register_id)
        isolated.append({
            "id": register_id,
            "name": e["name"],
            "label": short_label(e["name"]),
            "section": (e.get("section") or "").strip(),
            "degree": 0,
        })

    output = {
        "_readme": (
            "Genere par scripts/build_org_links.py a partir de "
            "data/link_candidates_draft.json (clear_candidates uniquement). "
            "'nodes'/'links' = organisations liees a au moins une autre ; "
            "'isolated_nodes' = organisations suivies sans lien identifie a ce jour "
            "(affichees sur le site via un bouton optionnel)."
        ),
        "nodes": nodes,
        "links": links,
        "isolated_nodes": isolated,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"{len(nodes)} organisations liees, {len(links)} liens uniques, {len(isolated)} organisations isolees")


if __name__ == "__main__":
    main()
