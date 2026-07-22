"""
Convertit data/link_candidates_draft.json (brouillon d'audit, avec preuves et
notes de methode) en data/org_links.json (donnees propres consommees par le
graphe D3 de index.html : noeuds et liens, avec categories pour les filtres).

Trois familles de noeuds/liens sont assemblees :

1. Organisations suivies (data/entities.json), classees en 3 categories a
   partir des champs deja presents "section" et "type" :
   - "manufacturer" (Fabricants de tabac) : type mentionnant manufacturer/
     tobacco company/distributor.
   - "trade_association" (Associations professionnelles) : le reste des
     organisations de section "Tobacco Business Organisations" (en pratique,
     uniquement des "(Local) Trade association").
   - "harm_reduction" (Organisations harm reduction liees a l'industrie) :
     section "Harm reduction organisations..." (toutes, quel que soit leur
     "type", qui y est heterogene).
   Liens entre elles : "clear_candidates" de link_candidates_draft.json.

2. Reseaux d'affaires generalistes (categorie "generalist_network") : lus
   dans le texte libre de data/raw_links_text.json (champs
   associations_networks/members_affiliates). Curation manuelle (liste
   GENERALIST_NETWORKS ci-dessous) plutot qu'une detection automatique : on
   ne retient QUE les reseaux clairement generalistes/multi-sectoriels (pas
   specifiques au tabac, a la logistique ou a un autre secteur), et cites
   par au moins 2 de nos organisations suivies - une mention par une seule
   organisation ne revele aucun lien ENTRE organisations, ce qui est
   l'objet de ce graphe (voir data_notes en sortie pour les cas ecartes a
   ce titre, ex: ICC, MEDEF, BDI, CONFINDUSTRIA... chacun cite par une
   seule organisation).

3. Intermediaires/cabinets de lobbying (categorie "intermediary", noeuds
   carres) : lus dans data/live_data.json, champ intermediaries_current_year
   (deja structure - liste de noms - pour 8 organisations sur 45). TOUS les
   cabinets deviennent des noeuds, y compris ceux cites par une seule
   organisation (contrairement aux reseaux generalistes : un cabinet
   partage revele un lien entre organisations via sa position de hub dans
   le graphe - inutile d'exiger 2+ citations en amont, la topologie s'en
   charge).

A relancer avec `python scripts/build_org_links.py` a chaque fois que
data/link_candidates_draft.json, data/raw_links_text.json ou
data/live_data.json changent.
"""

import json
import re

ENTITIES_PATH = "data/entities.json"
CANDIDATES_PATH = "data/link_candidates_draft.json"
RAW_LINKS_PATH = "data/raw_links_text.json"
LIVE_DATA_PATH = "data/live_data.json"
OUTPUT_PATH = "data/org_links.json"

# ---------------------------------------------------------------------
# Reseaux d'affaires generalistes cites par au moins 2 de nos organisations
# suivies (curation manuelle depuis data/raw_links_text.json). Chaque entree :
# id synthetique, nom affiche, liste de (register_id de l'organisation citante,
# texte source exact, precision optionnelle sur la nature du lien).
# ---------------------------------------------------------------------
GENERALIST_NETWORKS = [
    {
        "id": "gen:businesseurope",
        "name": "BusinessEurope",
        "citations": [
            ("51925911965-76", "BusinessEurope", None),   # PMI
            ("71175716023-03", "Business Europe", None),   # JTI
            ("2427500988-58", "BusinessEurope", None),     # BAT
        ],
    },
    {
        "id": "gen:amcham-eu",
        "name": "AmCham EU",
        "citations": [
            ("51925911965-76", "AmCham EU", None),
            ("2427500988-58", "AmCham EU", None),
            ("701118397425-19", "AmCham", None),  # Tabaqueira
        ],
    },
    {
        "id": "gen:kangaroo-group",
        "name": "The Kangaroo Group",
        "citations": [
            ("51925911965-76", "The Kangaroo Group", None),
            ("71175716023-03", "The Kangaroo Group", None),
            ("1496873833-97", "Kangaroo", None),  # Tobacco Europe AISBL
        ],
    },
    {
        "id": "gen:wirtschaftsrat-cdu",
        "name": "Wirtschaftsrat der CDU",
        "citations": [
            ("51925911965-76", "Wirtschaftsrat der CDU", None),
            ("71175716023-03", "Wirtschaftsrat der CDU", None),
        ],
    },
    {
        "id": "gen:seap",
        "name": "Society of European Affairs Professionals (SEAP)",
        "citations": [
            ("51925911965-76", "Society of European Affairs Professionals", None),
            ("1496873833-97", "SEAP : Society of European Affairs Professionals", None),
            ("92802501097-37", "Paul Varakas is a member of the Society of European Affairs Professionals (SEAP)", "representant individuel, pas l'organisation elle-meme"),
        ],
    },
    {
        "id": "gen:aeca",
        "name": "American European Community Association (AECA)",
        "citations": [
            ("71175716023-03", "American European Community Association (AECA)", None),
            ("1496873833-97", "AECA: The American European Community Association", None),
        ],
    },
    {
        "id": "gen:consumer-choice-center",
        "name": "Consumer Choice Center",
        "citations": [
            ("71175716023-03", "While not a member, JT International supports the Consumer Choice Center", "soutien revendique, pas une adhesion"),
            ("2427500988-58", "While not a member, BAT also supports the Consumer Choice Center", "soutien revendique, pas une adhesion"),
        ],
    },
]

GENERALIST_EXCLUDED_SINGLE_MENTION = [
    "ICC - International Chamber of Commerce (Tabaqueira uniquement)",
    "Confederacao Empresarial Portuguesa / CIP (Tabaqueira uniquement)",
    "Associacao Industrial Portuguesa / AIP (Tabaqueira uniquement)",
    "CONFINDUSTRIA (Logista uniquement)",
    "MEDEF de l'Est Parisien (Logista uniquement)",
    "Bundesverband der Deutschen Industrie / BDI (Bundesverband der Tabakwirtschaft uniquement)",
    "Verband der bayerischen Wirtschaft / vbw (Bundesverband der Tabakwirtschaft uniquement)",
    "VNO-NCW (Vereniging Nederlandse Sigaretten- en Kerftabakfabrikanten uniquement)",
    "CEOE (Mesa Del Tobacco / Asociacion Empresarial del Tabaco - meme organisation espagnole faitiere que CEOE, deja mentionnee une seule fois par citation distincte)",
    "Confcommercio (Federazione Italiana Tabaccai uniquement)",
    "Japan Business Council in Europe / JBCE (JT International uniquement)",
    "European Society of Association Executives / ESAE (Tobacco Europe AISBL uniquement)",
    "Trans-Atlantic Policy Network, European Business Summit, The European House Ambrosetti (PMI uniquement)",
    "Spanish Chamber of Commerce in Belgium, BCCB (British American Tobacco uniquement)",
]


def short_label(name: str) -> str:
    """Coupe l'annotation entre parentheses en fin de nom pour l'affichage graphe."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def categorize_entity(entity: dict) -> str:
    section = (entity.get("section") or "").strip()
    type_ = (entity.get("type") or "").lower()
    if section.startswith("Harm reduction"):
        return "harm_reduction"
    if "manufacturer" in type_ or "tobacco company" in type_ or "distributor" in type_:
        return "manufacturer"
    return "trade_association"


def slugify_cabinet(name: str) -> str:
    return "cab:" + re.sub(r"\s+", " ", name.strip()).lower()


def main():
    entities = json.load(open(ENTITIES_PATH, encoding="utf-8"))["entities"]
    candidates = json.load(open(CANDIDATES_PATH, encoding="utf-8"))["clear_candidates"]
    live_data = json.load(open(LIVE_DATA_PATH, encoding="utf-8"))

    entity_by_id = {e["register_id"]: e for e in entities if e.get("register_id")}

    # ---- 1. Liens organisation <-> organisation (inchange) ----
    edges = {}
    for c in candidates:
        pair = tuple(sorted([c["source_id"], c["target_id"]]))
        entry = edges.setdefault(pair, {
            "source": pair[0], "target": pair[1], "link_types": [],
            "has_registre_officiel": False, "has_verification_externe": False,
            "evidence": [],
        })
        entry["link_types"].append(c["link_type"])
        if "registre_officiel" in c["source_type"]:
            entry["has_registre_officiel"] = True
        if "verification_externe" in c["source_type"]:
            entry["has_verification_externe"] = True
        entry["evidence"].extend(c.get("evidence") or [])
        for ext in c.get("external_sources") or []:
            entry["evidence"].append({"org": None, "field": "verification_externe", "text": ext["description"], "url": ext["url"]})

    org_links = []
    org_node_ids = set()
    for (source_id, target_id), entry in edges.items():
        org_node_ids.add(source_id)
        org_node_ids.add(target_id)
        style = "solid" if entry["has_registre_officiel"] else "dashed"
        source_types = []
        if entry["has_registre_officiel"]:
            source_types.append("registre_officiel")
        if entry["has_verification_externe"]:
            source_types.append("verification_externe")
        org_links.append({
            "source": source_id, "target": target_id,
            "link_type": "; ".join(dict.fromkeys(entry["link_types"])),
            "style": style, "source_type": " + ".join(source_types),
            "evidence": entry["evidence"],
        })

    # ---- 2. Noeuds "reseau generaliste" + liens vers les organisations citantes ----
    generalist_nodes = []
    generalist_links = []
    for net in GENERALIST_NETWORKS:
        citations = [c for c in net["citations"] if c[2] != "SKIP"]
        if len(citations) < 2:
            continue
        generalist_nodes.append({"id": net["id"], "name": net["name"], "label": net["name"]})
        for org_id, quote, precision in citations:
            org_node_ids.add(org_id)
            link_type = "membre (reseau generaliste)" if not precision else f"membre (reseau generaliste) - {precision}"
            generalist_links.append({
                "source": org_id, "target": net["id"], "link_type": link_type,
                "style": "solid", "source_type": "registre_officiel",
                "evidence": [{"org": entity_by_id.get(org_id, {}).get("name"), "field": "associations_networks", "text": quote}],
            })

    # ---- 3. Noeuds "intermediaire/cabinet" + liens vers les organisations declarantes ----
    cabinet_nodes = {}
    cabinet_links = []
    for register_id, entity in entity_by_id.items():
        entry = live_data.get(register_id, {})
        names = entry.get("intermediaries_current_year") or []
        for raw_name in names:
            clean_name = re.sub(r"\s+", " ", raw_name.strip())
            if not clean_name:
                continue
            cid = slugify_cabinet(clean_name)
            cabinet_nodes.setdefault(cid, {"id": cid, "name": clean_name, "label": clean_name})
            org_node_ids.add(register_id)
            cabinet_links.append({
                "source": register_id, "target": cid,
                "link_type": "intermediaire declare (registre officiel)",
                "style": "solid", "source_type": "registre_officiel",
                "evidence": [{"org": entity["name"], "field": "intermediaries_current_year", "text": clean_name}],
            })

    # ---- Assemblage des noeuds ----
    all_links = org_links + generalist_links + cabinet_links
    degree = {}
    for link in all_links:
        degree[link["source"]] = degree.get(link["source"], 0) + 1
        degree[link["target"]] = degree.get(link["target"], 0) + 1

    nodes = []
    isolated = []
    seen_isolated_ids = set()
    for e in entities:
        register_id = e.get("register_id")
        if not register_id:
            continue
        d = degree.get(register_id, 0)
        node = {
            "id": register_id, "name": e["name"], "label": short_label(e["name"]),
            "category": categorize_entity(e), "shape": "circle", "degree": d,
        }
        if d == 0:
            if register_id in seen_isolated_ids:
                continue
            seen_isolated_ids.add(register_id)
            isolated.append(node)
        else:
            nodes.append(node)

    for net_node in generalist_nodes:
        nodes.append({
            "id": net_node["id"], "name": net_node["name"], "label": net_node["label"],
            "category": "generalist_network", "shape": "circle",
            "degree": degree.get(net_node["id"], 0),
        })

    for cab_node in cabinet_nodes.values():
        nodes.append({
            "id": cab_node["id"], "name": cab_node["name"], "label": cab_node["label"],
            "category": "intermediary", "shape": "square",
            "degree": degree.get(cab_node["id"], 0),
        })

    output = {
        "_readme": (
            "Genere par scripts/build_org_links.py. 'nodes' = tout noeud ayant au moins un "
            "lien (organisations suivies + reseaux generalistes + cabinets intermediaires) ; "
            "'isolated_nodes' = organisations suivies sans lien identifie a ce jour. Chaque "
            "noeud a un champ 'category' (manufacturer / trade_association / harm_reduction / "
            "generalist_network / intermediary) pour les filtres du site, et 'shape' "
            "(circle / square)."
        ),
        "generalist_networks_excluded_single_mention": GENERALIST_EXCLUDED_SINGLE_MENTION,
        "nodes": nodes,
        "links": all_links,
        "isolated_nodes": isolated,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    from collections import Counter
    cat_counts = Counter(n["category"] for n in nodes)
    print(f"{len(nodes)} noeuds relies, {len(all_links)} liens, {len(isolated)} organisations isolees")
    for cat, count in cat_counts.most_common():
        print(f"  - {cat}: {count}")


if __name__ == "__main__":
    main()
