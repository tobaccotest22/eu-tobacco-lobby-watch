"""
Construit la comparaison HATVP vs DGS, acteur par acteur et annee par
annee (2024 et 2025 separement, pas melangees), pour les 7 acteurs qui ont
les DEUX declarations : PMI, BAT, JTI, Seita, Logista, AFTF, Federation des
fabricants de cigares (FFC). Les acteurs vapotage/buralistes sont hors
perimetre legal DGS (article L.3512-7, deja documente dans
data/fr_summary_table.json) donc exclus de cette comparaison - comparer
leurs "0 declaration" DGS a leur budget HATVP n'aurait pas de sens.

Trois axes compares pour chaque annee :
- budget declare (fourchette HATVP vs montant unique DGS)
- nombre de personnes/salaries declares (HATVP : photo actuelle de la
  fiche, PAS specifique a l'annee - voir note ; DGS : declaration de
  l'annee precise)
- cabinets utilises (HATVP : clients actifs actuels ; DGS : cabinets
  listes dans la declaration de l'annee precise) - jusqu'ici les cabinets
  DGS n'etaient affiches nulle part sur le site alors que la donnee est
  disponible depuis data/dgs_2024_raw.json et data/dgs_2025_raw.json.

Le rapprochement des noms de cabinets entre les deux sources est fait par
normalisation + inclusion de sous-chaine (accents/majuscules/ponctuation
ignores) - une heuristique simple, pas une resolution d'entite : deux
cabinets peuvent etre le meme dans la vraie vie sans que leurs noms se
recoupent textuellement (ex. abreviation differente), auquel cas ils
seront signales a tort comme "non retrouve". A prendre comme un
reperage de premier niveau, pas une preuve definitive d'incoherence.

Ecrit data/hatvp_dgs_comparison.json.
"""

import glob
import json
import os
import re
import unicodedata

import pandas as pd

HATVP_DIR = None
for d in glob.glob("data/_hatvp_raw/**/1_informations_generales.csv", recursive=True):
    HATVP_DIR = os.path.dirname(d)
if not HATVP_DIR:
    raise SystemExit("Lance d'abord scripts/fetch_hatvp_fr.py pour telecharger l'export HATVP.")

OUTPUT_PATH = "data/hatvp_dgs_comparison.json"
DGS_SOURCES = {2024: "data/dgs_2024_raw.json", 2025: "data/dgs_2025_raw.json"}

# (nom affiche, denomination HATVP exacte, mots-cles DGS)
ORGS = [
    ("Philip Morris International (PMI)", "PHILIP MORRIS FRANCE", ["philip morris"]),
    ("British American Tobacco (BAT)", "BRITISH AMERICAN TOBACCO FRANCE", ["british american tobacco", "bat france", "bat_"]),
    ("JT International (JTI)", "JT INTERNATIONAL FRANCE", ["jt international", "japan tobacco", "jti"]),
    ("Seita (Imperial Brands)", "SOCIETE NATIONALE D'EXPLOITATION INDUSTRIELLE DES TABACS ET ALLUMETTES", ["exploitation industrielle des tabacs", "seita"]),
    ("Logista", "LOGISTA FRANCE", ["logista"]),
    ("Association des fournisseurs de tabac a fumer (AFTF)", "ASSOCIATION DES FOURNISSEURS DE TABACS A FUMER", ["fournisseurs de tabacs a fumer", "aftf"]),
    ("Federation des fabricants de cigares", "FÉDÉRATION DES FABRICANTS DE CIGARES", ["federation des fabricants de cigares", "ffc"]),
]


def normalize(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", " ", s).strip().lower()
    return s


def record_haystack(record):
    parts = [record.get("org_name_pdf", ""), record.get("source_file", ""), record.get("folder_org_name", "")]
    return normalize(" ".join(p for p in parts if p))


def find_dgs_record(records, keywords):
    matches = [r for r in records if any(kw in record_haystack(r) for kw in keywords)]
    return matches[0] if matches else None


def names_overlap(name_a, name_b):
    a, b = normalize(name_a), normalize(name_b)
    if not a or not b:
        return False
    return a in b or b in a


def cabinets_for_org(clients, info, org_siret):
    if not org_siret:
        return []
    org_siren = str(org_siret)[:9]
    matches = clients[
        clients["identifiant_national_client"].astype(str).str.startswith(org_siren)
        & clients["dateCessation"].isna()
    ]
    cabinet_ids = matches["representants_id"].unique()
    names = info[info["representants_id"].isin(cabinet_ids)]["denomination"].tolist()
    return sorted(set(names))


def personnes_for_org(collab, rid):
    people = collab[collab["representants_id"] == rid]
    seen = set()
    names = []
    for _, p in people.iterrows():
        key = (str(p["nom_collaborateur"]).strip().upper(), str(p["prenom_collaborateur"]).strip().upper())
        if key in seen:
            continue
        seen.add(key)
        names.append(f"{p['prenom_collaborateur']} {p['nom_collaborateur']}")
    return sorted(names)


def compare_cabinets(hatvp_cabinets, dgs_cabinets):
    dgs_names = [c["name"] for c in dgs_cabinets]
    hatvp_only = [c for c in hatvp_cabinets if not any(names_overlap(c, d) for d in dgs_names)]
    dgs_only = [c for c in dgs_names if not any(names_overlap(c, h) for h in hatvp_cabinets)]
    return {
        "hatvp_only": hatvp_only,
        "dgs_only": dgs_only,
        "mismatch": bool(hatvp_only or dgs_only),
    }


def main():
    info = pd.read_csv(f"{HATVP_DIR}/1_informations_generales.csv", sep=";", encoding="utf-8")
    exo = pd.read_csv(f"{HATVP_DIR}/15_exercices.csv", sep=";", encoding="utf-8")
    clients = pd.read_csv(f"{HATVP_DIR}/4_clients.csv", sep=";", encoding="utf-8")
    collab = pd.read_csv(f"{HATVP_DIR}/3_collaborateurs.csv", sep=";", encoding="utf-8")

    dgs_records = {year: json.load(open(path, encoding="utf-8")) for year, path in DGS_SOURCES.items()}

    results = []
    for display_name, hatvp_denom, dgs_keywords in ORGS:
        info_row = info[info["denomination"].str.strip() == hatvp_denom]
        if info_row.empty:
            print(f"INTROUVABLE sur HATVP : {display_name}")
            continue
        info_row = info_row.iloc[0]
        rid = info_row["representants_id"]
        org_siret = info_row["identifiant_national"]

        hatvp_cabinets = cabinets_for_org(clients, info, org_siret)
        personnes = personnes_for_org(collab, rid)

        years = {}
        for year in (2024, 2025):
            ex = exo[(exo["representants_id"] == rid) & (exo["annee_fin"] == year)]
            hatvp_budget_bas = hatvp_budget_haut = None
            if not ex.empty:
                e = ex.iloc[0]
                hatvp_budget_bas = None if pd.isna(e["montant_depense_inf"]) else int(e["montant_depense_inf"])
                hatvp_budget_haut = None if pd.isna(e["montant_depense_sup"]) else int(e["montant_depense_sup"])

            dgs_record = find_dgs_record(dgs_records[year], dgs_keywords)
            dgs_budget = dgs_record["total_declare"] if dgs_record else None
            dgs_cabinets = dgs_record["cabinets"] if dgs_record else []
            dgs_nb_personnes = dgs_record.get("nb_personnels") if dgs_record else None

            budget_mismatch = False
            if dgs_budget is not None and hatvp_budget_bas is not None and hatvp_budget_haut is not None:
                budget_mismatch = not (hatvp_budget_bas <= dgs_budget <= hatvp_budget_haut)
            elif (dgs_budget is not None) != (hatvp_budget_bas is not None):
                budget_mismatch = True  # une seule des deux sources a une donnee

            personnes_mismatch = (
                dgs_nb_personnes is not None
                and len(personnes) != dgs_nb_personnes
            )

            cabinets_cmp = compare_cabinets(hatvp_cabinets, dgs_cabinets)

            years[str(year)] = {
                "hatvp": {
                    "budget_bas": hatvp_budget_bas,
                    "budget_haut": hatvp_budget_haut,
                },
                "dgs": {
                    "budget": dgs_budget,
                    "nb_personnes": dgs_nb_personnes,
                    "cabinets": dgs_cabinets,
                    "trouve": dgs_record is not None,
                },
                "mismatches": {
                    "budget": budget_mismatch,
                    "personnes": personnes_mismatch,
                    "cabinets": cabinets_cmp["mismatch"],
                },
                "cabinets_comparison": cabinets_cmp,
            }

        results.append({
            "acteur": display_name,
            "personnes_hatvp": personnes,
            "nb_personnes_hatvp": len(personnes),
            "cabinets_hatvp": hatvp_cabinets,
            "years": years,
        })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    for r in results:
        print(f"\n=== {r['acteur']} (personnes HATVP actuelles : {r['nb_personnes_hatvp']}) ===")
        for year, y in r["years"].items():
            flags = y["mismatches"]
            flagged = [k for k, v in flags.items() if v]
            print(f"  {year} : HATVP {y['hatvp']['budget_bas']}-{y['hatvp']['budget_haut']} vs "
                  f"DGS {y['dgs']['budget']} (personnes DGS={y['dgs']['nb_personnes']}) "
                  f"-> ecarts: {flagged if flagged else 'aucun'}")

    print(f"\nEcrit dans {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
