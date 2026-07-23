"""
Construit l'historique du total declare DGS (remuneration personnels +
achats cabinets + avantages) pour les 7 organisations suivies : BAT, PMI,
Confederation des buralistes, Seita, FFC, AFTF, JTI - sur 2022-2025 (2022 et
2023 : scripts/parse_dgs_2022_2023.py ; 2024 : scripts/parse_dgs_2024.py ;
2025 : scripts/parse_dgs_2025.py, deja calcule dans data/dgs_2025_raw.json).

Chaque annee a son propre format de source (nom de fichier ou de dossier),
donc l'appariement organisation -> enregistrement se fait par mot-cle sur le
nom extrait du PDF et/ou le nom de fichier/dossier, plutot que par une cle
strictement identique d'une annee a l'autre.

La Confederation des buralistes n'a ete trouvee dans AUCUNE des 4 annees :
coherent avec la conclusion deja documentee (statut de "prepose de
l'administration des douanes", hors perimetre de l'article L.3512-7 qui vise
les "distributeurs") - ce n'est pas un trou d'extraction.

Ecrit data/dgs_history.json.
"""

import json
import unicodedata

SOURCES = {
    2022: "data/dgs_2022_raw.json",
    2023: "data/dgs_2023_raw.json",
    2024: "data/dgs_2024_raw.json",
    2025: "data/dgs_2025_raw.json",
}

OUTPUT_PATH = "data/dgs_history.json"

# (nom affiche, mots-cles a chercher dans org_name_pdf/source_file/folder_org_name, normalises sans accents/majuscules)
ORGS = [
    ("Philip Morris International (PMI)", ["philip morris"]),
    ("British American Tobacco (BAT)", ["british american tobacco", "bat france", "bat_"]),
    ("JT International (JTI)", ["jt international", "japan tobacco", "jti"]),
    ("Seita (Imperial Brands)", ["exploitation industrielle des tabacs", "seita"]),
    ("Confederation des buralistes", ["confederation nationale des buralistes", "confederation des buralistes"]),
    ("Federation des fabricants de cigares", ["federation des fabricants de cigares", "ffc"]),
    ("Association des fournisseurs de tabac a fumer (AFTF)", ["fournisseurs de tabacs a fumer", "aftf"]),
]


def normalize(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.lower()


def record_haystack(record):
    parts = [
        record.get("org_name_pdf", ""),
        record.get("source_file", ""),
        record.get("folder_org_name", ""),
    ]
    return normalize(" ".join(p for p in parts if p))


def main():
    all_records = {}
    for year, path in SOURCES.items():
        with open(path, encoding="utf-8") as f:
            all_records[year] = json.load(f)

    organisations = {}
    yearly_totals = {}
    unmatched_by_org = {}

    for display_name, keywords in ORGS:
        budget_by_year = {}
        for year, records in all_records.items():
            matches = [
                r for r in records
                if any(kw in record_haystack(r) for kw in keywords)
            ]
            if len(matches) > 1:
                print(f"ATTENTION : {display_name} / {year} matche {len(matches)} enregistrements, "
                      f"je garde le premier : {[m.get('source_file') or m.get('folder_org_name') for m in matches]}")
            if matches:
                total = matches[0]["total_declare"]
                budget_by_year[str(year)] = total
                yearly_totals.setdefault(str(year), {"total": 0, "nb_organisations": 0})
                yearly_totals[str(year)]["total"] += total
                yearly_totals[str(year)]["nb_organisations"] += 1

        organisations[display_name] = budget_by_year
        print(f"{display_name:55s} : {budget_by_year}")

    output = {
        "organisations": organisations,
        "yearly_totals": dict(sorted(yearly_totals.items())),
        "_notes": [
            "Confederation des buralistes : aucune declaration DGS trouvee sur "
            "2022-2025 (les 4 annees ont ete cherchees) - coherent avec le statut "
            "de 'prepose de l'administration des douanes' (hors perimetre de "
            "l'article L.3512-7 qui vise les 'distributeurs'), deja documente "
            "dans data/fr_summary_table.json.",

            "BAT : le montant declare au titre de la remuneration des personnels "
            "passe de 10 436EUR (2023) a 422 392EUR (2024), soit x40. Verification "
            "faite sur le nombre de salaries declares (pas seulement le montant) : "
            "il reste stable (3 personnes en 2023 comme en 2024, source : "
            "'Nombre de personnes/personnels remunerees' dans chaque PDF) - "
            "l'ecart n'est donc PAS explique par un changement de perimetre "
            "(plus de personnes comptees). Aucune autre explication verifiee "
            "trouvee a ce stade : le chiffre est repris tel que declare, sans "
            "correction ni interpretation.",
        ],
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nEcrit dans {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
