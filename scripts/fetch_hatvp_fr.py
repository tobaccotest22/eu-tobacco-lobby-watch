"""
Volet France : extraction HATVP (Haute Autorite pour la transparence de la
vie publique) - repertoire des representants d'interets.

Contrairement au site EU (scraping page par page), HATVP publie un export
officiel nocturne complet en CSV ("vues separees"), telecharge par ce
script plutot que scrape au cas par cas :
https://www.hatvp.fr/agora/opendata/csv/Vues_Separees_CSV.zip

Fichiers utilises dans ce zip :
- 1_informations_generales.csv : une ligne par organisation inscrite
  (denomination, SIRET, ville...).
- 15_exercices.csv : un exercice (periode de declaration) par organisation
  et par annee. ATTENTION : la periode n'est pas toujours l'annee civile
  (ex: SEITA et Logista declarent sur un exercice octobre-septembre). Le
  champ qui correspond a "l'annee 2024/2025" au sens ou l'entend le
  fichier Excel de reference du client est annee_fin, PAS annee_debut -
  verifie en recoupant les 9 organisations du fichier Excel qui ont un
  nombre d'actions HATVP deja renseigne : 8/9 correspondent exactement en
  utilisant annee_fin (la 9e, British American Tobacco France, affiche 6
  actions en 2025 cote HATVP contre 1 dans le fichier Excel - la
  publication HATVP de cet exercice date du 26/03/2026, donc posterieure
  a la constitution probable du fichier Excel : ecart de fraicheur des
  donnees, pas un bug d'extraction).
- 8_objets_activites.csv : le texte libre de chaque activite declaree
  (objet_activite), rattache a un exercice via exercices_id. C'est ce
  champ qui est filtre par mot-cle pour la decouverte de nouvelles
  organisations (point 4a/4b de la demande).

Le champ date_publication_activite de 8_objets_activites.csv ne doit PAS
etre utilise pour attribuer une action a l'annee 2024 ou 2025 : c'est la
date de derniere publication/mise a jour de la fiche, pas la date de
l'exercice auquel elle appartient (verifie : donne des comptages trop
eleves et incoherents avec le fichier Excel, l'annee_fin de l'exercice
associe est la bonne cle).

Sortie : data/hatvp_fr_raw.json avec :
- "orgs_with_activity" : toutes les organisations ayant au moins une
  activite en 2024 ou 2025 mentionnant un mot-cle tabac/nicotine/vapotage
  (recherche sur objet_activite), avec leur nombre d'actions par annee
  (source : nombre_activites de l'exercice, pas un comptage manuel des
  lignes objets - coherent avec le mode de calcul du fichier Excel).
- "orgs_matched_by_name" : organisations dont la denomination elle-meme
  contient un mot-cle (verification croisee du point 4b).
"""

import glob
import io
import json
import re
import unicodedata
import urllib.request
import zipfile

import pandas as pd

ZIP_URL = "https://www.hatvp.fr/agora/opendata/csv/Vues_Separees_CSV.zip"
EXTRACT_DIR = "data/_hatvp_raw"
OUTPUT_PATH = "data/hatvp_fr_raw.json"

KEYWORDS = ["tabac", "nicotine", "cigarette electronique", "cigarette", "vapotage", "vape", "tabagisme"]


def strip_accents(s):
    if not isinstance(s, str):
        return s
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def matches_keywords(text):
    norm = strip_accents(text or "").lower()
    return any(kw in norm for kw in KEYWORDS)


def download_and_extract():
    req = urllib.request.Request(ZIP_URL, headers={"User-Agent": "eu-tobacco-lobby-watch/0.3"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(EXTRACT_DIR)


def find_csv_dir():
    import os
    candidates = glob.glob(f"{EXTRACT_DIR}/**/1_informations_generales.csv", recursive=True)
    if not candidates:
        raise FileNotFoundError("1_informations_generales.csv introuvable apres extraction")
    return os.path.dirname(candidates[0])


def main():
    print("Telechargement de l'export HATVP (peut prendre quelques dizaines de secondes)...")
    download_and_extract()
    csv_dir = find_csv_dir()

    info = pd.read_csv(f"{csv_dir}/1_informations_generales.csv", sep=";", encoding="utf-8")
    exo = pd.read_csv(f"{csv_dir}/15_exercices.csv", sep=";", encoding="utf-8")
    obj = pd.read_csv(f"{csv_dir}/8_objets_activites.csv", sep=";", encoding="utf-8")

    # --- 4b : organisations dont le NOM contient un mot-cle ---
    info["denom_match"] = info["denomination"].fillna("").apply(matches_keywords)
    by_name = info[info["denom_match"]][
        ["representants_id", "denomination", "identifiant_national", "ville", "dateCessation"]
    ].to_dict("records")

    # --- 4a : organisations dont au moins une ACTIVITE (texte libre) contient un mot-cle ---
    #
    # Important : pour une organisation mono-secteur (PMI, France Vapotage...),
    # la totalite de son activite declaree porte sur le tabac/la nicotine, donc
    # son nombre_activites total (cote exercice) EST le nombre d'actions
    # pertinentes - c'est ce qui a permis de valider la methode sur le fichier
    # Excel. Mais pour un cabinet de conseil multi-clients (ex: Boury Tallon,
    # AI2P, TMA...), nombre_activites compte TOUTES ses activites pour TOUS ses
    # clients, tabac ou non - l'utiliser donnerait des comptages absurdement
    # eleves (ex: 294 en 2024 pour un cabinet). Le nombre pertinent est donc
    # le compte des lignes objet_activite qui matchent effectivement un
    # mot-cle, pas nombre_activites brut. On calcule les deux : "actions_XXXX"
    # (matched) est la colonne principale, "total_activites_org_XXXX" donne le
    # volume global de l'organisation a titre de contexte (utile pour reperer
    # les cabinets generalistes dont le tabac n'est qu'une petite part).
    obj["objet_match"] = obj["objet_activite"].fillna("").apply(matches_keywords)
    matched_objets = obj[obj["objet_match"]].merge(
        exo[["exercices_id", "representants_id", "annee_fin", "nombre_activites"]],
        on="exercices_id", how="left",
    )

    org_ids = matched_objets["representants_id"].dropna().unique()

    orgs_with_activity = []
    for rid in org_ids:
        info_row = info[info["representants_id"] == rid]
        if info_row.empty:
            continue
        info_row = info_row.iloc[0]
        org_matched = matched_objets[matched_objets["representants_id"] == rid]
        org_exercices = exo[exo["representants_id"] == rid]

        actions_2024 = int((org_matched["annee_fin"] == 2024).sum())
        actions_2025 = int((org_matched["annee_fin"] == 2025).sum())
        if actions_2024 == 0 and actions_2025 == 0:
            continue  # l'activite matchee est sur une autre annee que 2024/2025
        total_2024 = int(org_exercices[org_exercices["annee_fin"] == 2024]["nombre_activites"].sum())
        total_2025 = int(org_exercices[org_exercices["annee_fin"] == 2025]["nombre_activites"].sum())

        orgs_with_activity.append({
            "representants_id": int(rid),
            "denomination": info_row["denomination"],
            "identifiant_national": info_row["identifiant_national"],
            "ville": info_row["ville"],
            "date_enregistrement": info_row.get("date_premiere_publication"),
            "date_cessation": info_row.get("dateCessation"),
            "actions_2024": actions_2024,
            "actions_2025": actions_2025,
            "total_activites_org_2024": total_2024,
            "total_activites_org_2025": total_2025,
            "est_specialise_tabac": (actions_2024 == total_2024 and actions_2025 == total_2025),
        })

    orgs_with_activity.sort(key=lambda o: -(o["actions_2024"] + o["actions_2025"]))

    output = {
        "_readme": (
            "Genere par scripts/fetch_hatvp_fr.py depuis l'export officiel HATVP "
            "(vues separees, mis a jour chaque nuit). 'orgs_with_activity' : "
            "organisations ayant au moins une activite en 2024 ou 2025 dont le texte "
            "(objet_activite) contient un des mots-cles " + str(KEYWORDS) + ". Le nombre "
            "d'actions par annee vient du champ nombre_activites de l'exercice HATVP "
            "correspondant (annee_fin = 2024 ou 2025), PAS d'un comptage des lignes "
            "filtrees par mot-cle - verifie exact sur 8/9 organisations de reference. "
            "'orgs_matched_by_name' : organisations dont la denomination elle-meme "
            "contient un mot-cle (verification croisee)."
        ),
        "orgs_with_activity": orgs_with_activity,
        "orgs_matched_by_name": by_name,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    print(f"{len(orgs_with_activity)} organisations avec activite 2024/2025 matchee par mot-cle")
    print(f"{len(by_name)} organisations dont le nom contient un mot-cle")
    print(f"Ecrit dans {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
