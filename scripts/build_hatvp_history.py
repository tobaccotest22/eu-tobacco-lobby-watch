"""
Construit l'historique du budget HATVP declare (montant_depense_sup, exercice
par exercice, 2019-2025) pour :
- les 15 acteurs du tableau principal (memes denominations exactes que
  scripts/build_fr_summary_table.py - a garder synchronisee si la liste
  ACTEURS y change), utilise pour la ligne depliable "Et par rapport a
  avant ?" de chaque acteur dans le tableau ;
- un sous-ensemble de 7 organisations (BAT, PMI, Confederation des
  buralistes, Seita, FFC, AFTF, JTI) + une ligne "Total", demande
  specifiquement pour la courbe de la section "Historique / Statistiques".

Verification de faisabilite deja faite avant construction (cf. conversation) :
l'export HATVP (deja telecharge par scripts/fetch_hatvp_fr.py dans
data/_hatvp_raw/) contient bien plusieurs exercices par representant, sur
15_exercices.csv, identifies par annee_fin - c'est la meme convention deja
validee dans scripts/build_fr_summary_table.py.

Ecrit data/hatvp_history.json.
"""

import glob
import json
import os

import pandas as pd

HATVP_DIR = None
for d in glob.glob("data/_hatvp_raw/**/1_informations_generales.csv", recursive=True):
    HATVP_DIR = os.path.dirname(d)
if not HATVP_DIR:
    raise SystemExit("Lance d'abord scripts/fetch_hatvp_fr.py pour telecharger l'export HATVP.")

OUTPUT_PATH = "data/hatvp_history.json"

# (nom affiche, denomination HATVP exacte) - copie de la liste ACTEURS de
# scripts/build_fr_summary_table.py (memes libelles "acteur"), pour que la
# ligne depliable du tableau principal puisse faire correspondre chaque
# ligne par son nom.
ACTEURS_HATVP_DENOM = [
    ("Philip Morris International (PMI)", "PHILIP MORRIS FRANCE"),
    ("British American Tobacco (BAT)", "BRITISH AMERICAN TOBACCO FRANCE"),
    ("JT International (JTI)", "JT INTERNATIONAL FRANCE"),
    ("Seita (Imperial Brands)", "SOCIETE NATIONALE D'EXPLOITATION INDUSTRIELLE DES TABACS ET ALLUMETTES"),
    ("Logista", "LOGISTA FRANCE"),
    ("France Vapotage", "France Vapotage"),
    ("Fivape (CACE)", "COLLECTIF DES ACTEURS DE LA CIGARETTE ELECTRONIQUE"),
    ("LPV Company", "LPV COMPANY"),
    ("Sovape", "SOVAPE"),
    ("Confederation des buralistes", "LA CONFEDERATION NATIONALE DES BURALISTES DE FRANCE"),
    ("Association des fournisseurs de tabac a fumer (AFTF)", "ASSOCIATION DES FOURNISSEURS DE TABACS A FUMER"),
    ("Aiduce", "ASSOCIATION INDEPENDANTE DES UTILISATEURS DE CIGARETTE ELECTRONIQUE (AIDUCE)"),
    ("Federation des fabricants de cigares", "FÉDÉRATION DES FABRICANTS DE CIGARES"),
    ("Association Francaise des Industriels du Tabac (Unifab)", "ASSOCIATION FRANCAISE DES INDUSTRIELS DU TABAC"),
]

# sous-ensemble demande explicitement pour la courbe "Historique / Statistiques"
CHART_7 = {
    "Philip Morris International (PMI)",
    "British American Tobacco (BAT)",
    "JT International (JTI)",
    "Seita (Imperial Brands)",
    "Confederation des buralistes",
    "Federation des fabricants de cigares",
    "Association des fournisseurs de tabac a fumer (AFTF)",
}


def main():
    info = pd.read_csv(f"{HATVP_DIR}/1_informations_generales.csv", sep=";", encoding="utf-8")
    exo = pd.read_csv(f"{HATVP_DIR}/15_exercices.csv", sep=";", encoding="utf-8")

    organisations = {}
    yearly_totals = {}

    for display_name, hatvp_denom in ACTEURS_HATVP_DENOM:
        info_row = info[info["denomination"].str.strip() == hatvp_denom]
        budget_by_year = {}
        if info_row.empty:
            print(f"INTROUVABLE sur HATVP : {display_name} ({hatvp_denom})")
        else:
            rid = info_row.iloc[0]["representants_id"]
            org_exercices = exo[exo["representants_id"] == rid].sort_values("annee_fin")
            for _, e in org_exercices.iterrows():
                year = int(e["annee_fin"])
                if year < 2019 or year > 2025:
                    continue  # perimetre demande (2019-2025) ; au-dela, exercice pas encore cloture
                budget = e["montant_depense_sup"]
                if pd.isna(budget):
                    continue
                not_yet_published = (
                    e["nombre_activites"] == 0
                    and (e["montant_depense_inf"] or 0) == 0
                    and pd.isna(e["nombre_salaries"])
                )
                if not_yet_published:
                    # meme signature que la note "exercice pas encore publie" de
                    # build_fr_summary_table.py (0 activite, budget 0, salaries
                    # non renseignes) - un vrai 0 aurait au moins des salaries
                    # renseignes ou des activites declarees a 0 explicitement.
                    print(f"  ({display_name} {year} : exercice pas encore publie, exclu)")
                    continue
                budget_by_year[str(year)] = int(budget)
                if display_name in CHART_7:
                    yearly_totals.setdefault(str(year), {"total": 0, "nb_organisations": 0})
                    yearly_totals[str(year)]["total"] += int(budget)
                    yearly_totals[str(year)]["nb_organisations"] += 1

        organisations[display_name] = {
            "budget_by_year": budget_by_year,
            "in_chart_7": display_name in CHART_7,
        }
        print(f"{display_name:55s} : {budget_by_year}")

    output = {
        "organisations": organisations,
        "yearly_totals": dict(sorted(yearly_totals.items())),
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nEcrit dans {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
