"""
Construit le tableau resume France (un acteur par ligne) a partir de :
- data/_hatvp_raw/.../Vues_Separees (export officiel HATVP, deja telecharge
  par scripts/fetch_hatvp_fr.py)
- data/dgs_2025_raw.json (declarations DGS 2025, deja parsees par
  scripts/parse_dgs_2025.py)
- la liste des 19 acteurs du fichier Excel de reference, ajustee selon
  l'echange avec l'utilisateur :
  - Fivape et le "Collectif des Acteurs de la Cigarette Electronique (CACE)"
    sont la MEME organisation (CACE est le nom d'inscription legal de Fivape
    sur HATVP, identifiant national 798356911, confirme par l'utilisateur) -
    fusionnes en une seule ligne "Fivape (CACE)".
  - Association Francaise des Industriels du Tabac (Unifab) : ajoutee puis
    RETIREE sur demande de l'utilisateur - fait autre chose que du lobbying
    tabac au sens du perimetre actuel de ce tableau (a revoir/classer dans
    une autre categorie plus tard, pas pour l'instant).

Colonnes du tableau : Acteur, Categorie, Budget (fourchette HATVP declaree,
exercice 2025), Cabinets utilises (+nombre, avec pour chacun la ou les
annees 2024/2025 ou la relation client etait active sur HATVP - voir
cabinets_by_year_for_org), Salaries (nombre de personnes nommees dans la
section "Personnes chargees de la representation d'interets" de la fiche
HATVP - PAS l'ETP de 15_exercices.csv, juge trop approximatif/declaratif),
Declaration DGS 2025 (montant total uniquement - detail cabinets/salaries
DGS disponible en note a part si besoin).

Le budget HATVP est lu sur l'exercice dont annee_fin = 2025 (le plus
recent), pour rester coherent avec le point de comparaison DGS 2025 demande
par l'utilisateur. Les cabinets couvrent 2024 ET 2025 (verification de
faisabilite faite avant generalisation : 4_clients.csv expose dateAjout/
dateCessation par relation client, ce qui suffit a determiner l'annee
d'activite - contrairement aux personnes/activites, aucune table HATVP ne
rattache une action a un client precis, donc impossible d'aller plus loin
que "relation client active sur l'annee", pas "a facture une action sur
l'annee"). Les personnes (3_collaborateurs.csv) ne sont, elles, PAS
specifiques a un exercice - c'est la photo actuelle de la fiche HATVP,
deduplique par (nom, prenom) car HATVP liste parfois deux fois la meme
personne (une fois avec sa fonction renseignee, une fois vide).
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

DGS_PATH = "data/dgs_2025_raw.json"
OUTPUT_PATH = "data/fr_summary_table.json"

# (nom affiche, categorie, denomination exacte HATVP ou None si introuvable,
#  nom de dossier DGS 2025 ou None si aucune declaration/hors perimetre)
ACTEURS = [
    ("Philip Morris International (PMI)", "Industriels du tabac", "PHILIP MORRIS FRANCE", "Philip Morris France"),
    ("British American Tobacco (BAT)", "Industriels du tabac", "BRITISH AMERICAN TOBACCO FRANCE", "BAT France"),
    ("JT International (JTI)", "Industriels du tabac", "JT INTERNATIONAL FRANCE", "JTI France"),
    ("Seita (Imperial Brands)", "Industriels du tabac", "SOCIETE NATIONALE D'EXPLOITATION INDUSTRIELLE DES TABACS ET ALLUMETTES", "SEITA"),
    ("Logista", "Industriels du tabac", "LOGISTA FRANCE", "Logista France"),
    ("France Vapotage", "Vapotage", "France Vapotage", None),
    ("Fivape (CACE)", "Vapotage", "COLLECTIF DES ACTEURS DE LA CIGARETTE ELECTRONIQUE", None),  # CACE = nom d'inscription HATVP de Fivape (798356911)
    ("LPV Company", "Vapotage", "LPV COMPANY", None),
    ("Sovape", "Vapotage", "SOVAPE", None),
    ("Confederation des buralistes", "Association/Federation", "LA CONFEDERATION NATIONALE DES BURALISTES DE FRANCE", None),
    ("Association des fournisseurs de tabac a fumer (AFTF)", "Association/Federation", "ASSOCIATION DES FOURNISSEURS DE TABACS A FUMER", "AFTF"),
    ("Aiduce", "Association/Federation", "ASSOCIATION INDEPENDANTE DES UTILISATEURS DE CIGARETTE ELECTRONIQUE (AIDUCE)", None),
    ("Federation des fabricants de cigares", "Association/Federation", "FÉDÉRATION DES FABRICANTS DE CIGARES", "Fédération des fabricants de cigares"),
    ("Cigusto / HDDB Holding", "Cas particulier (actions via un tiers)", None, None),  # via Coalitio, voir note
]


def load_hatvp():
    info = pd.read_csv(f"{HATVP_DIR}/1_informations_generales.csv", sep=";", encoding="utf-8")
    exo = pd.read_csv(f"{HATVP_DIR}/15_exercices.csv", sep=";", encoding="utf-8")
    clients = pd.read_csv(f"{HATVP_DIR}/4_clients.csv", sep=";", encoding="utf-8")
    collab = pd.read_csv(f"{HATVP_DIR}/3_collaborateurs.csv", sep=";", encoding="utf-8")
    return info, exo, clients, collab


CABINETS_YEARS = (2024, 2025)

# Cas ou deux inscriptions HATVP distinctes (representants_id differents)
# correspondent en realite a la meme organisation, suite a un changement de
# marque/fusion - signale par l'utilisateur pour Rivington/ESL & Network,
# verifie sur la fiche HATVP de ESL & NETWORK FRANCE SAS (SIREN 431853530) :
# c'est bien l'organisation "ESL Rivington", et l'ancienne inscription
# "RIVINGTON" (SIREN 533445318) a ete fermee le 01/01/2023 sur son propre
# 1_informations_generales.csv (dateCessation) - coherent avec une
# absorption/rebranding, pas deux cabinets distincts. Cle = denomination
# HATVP brute, valeur = nom affiche fusionne. Verifie qu'aucun autre cabinet
# de la liste des 14 acteurs ne presente le meme profil (une inscription avec
# dateCessation propre + une autre visiblement liee) - RIVINGTON est, a ce
# jour, le seul cas trouve dans les 26 cabinets jamais declares pour ces 14
# organisations (cf. conversation).
CABINET_NAME_ALIASES = {
    "RIVINGTON": "ESL Rivington",
    "ESL & NETWORK FRANCE SAS": "ESL Rivington",
}


def cabinets_by_year_for_org(clients, info, org_siret, years=CABINETS_YEARS):
    """Cabinets ayant declare cet acteur comme client sur 4_clients.csv, avec
    le ou les annees (parmi `years`) ou la relation pouvait etre active. Une
    annee Y est retenue si la relation a commence au plus tard le 31/12/Y
    (dateAjout, la seule date fiable du cote relation - voir plus bas) ET si
    le cabinet lui-meme etait encore inscrit a la HATVP a un moment de
    l'annee Y (dateCessation propre du cabinet sur 1_informations_generales.csv,
    NaN ou posterieure au 01/01/Y).

    Le champ dateCessation cote RELATION (4_clients.csv) n'est volontairement
    PAS utilise comme borne de fin, et le flag ancienClient est ignore : les
    deux se sont averes peu fiables pour dater une fin reelle de collaboration
    - verifie sur le cas ESL & Network/PMI, marque ancienClient=True avec une
    dateDesactivation de 2022, alors que 5 actions beneficiant explicitement
    a "PHILIP MORRIS FRANCE" sont bien declarees sur l'exercice HATVP 2025 de
    ESL & Network (dont une sur la fiscalite des sachets de nicotine,
    confirmee par l'utilisateur) - ancienClient/dateDesactivation semblent
    donc refleter une reclassification administrative cote HATVP, pas
    forcement un arret reel de la relation. Seule la dateCessation PROPRE du
    cabinet (fin d'inscription HATVP, un fait dur) sert donc de borne de fin.
    Consequence : "cabinet actif pour X en 2024" signifie "relation
    declaree existante et cabinet toujours inscrit a la HATVP en 2024", pas
    "a facture une action pour X en 2024" - c'est le niveau de precision
    maximal disponible avec les tables ouvertes par HATVP pour les clients."""
    if not org_siret:
        return []
    org_siren = str(org_siret)[:9]
    matches = clients[clients["identifiant_national_client"].astype(str).str.startswith(org_siren)].copy()
    if matches.empty:
        return []
    matches["dateAjout_dt"] = pd.to_datetime(matches["dateAjout"], format="%d-%m-%Y %H:%M", errors="coerce")

    cabinet_own_cessation = info.set_index("representants_id")["dateCessation"]
    cabinet_own_cessation_dt = pd.to_datetime(cabinet_own_cessation, format="%d-%m-%Y %H:%M", errors="coerce")

    years_by_name = {}
    for _, row in matches.iterrows():
        rid = row["representants_id"]
        name_row = info[info["representants_id"] == rid]
        if name_row.empty:
            continue
        display_name = CABINET_NAME_ALIASES.get(name_row.iloc[0]["denomination"], name_row.iloc[0]["denomination"])
        start = row["dateAjout_dt"]
        cabinet_end = cabinet_own_cessation_dt.get(rid)
        for year in years:
            year_start = pd.Timestamp(year, 1, 1)
            year_end = pd.Timestamp(year, 12, 31, 23, 59, 59)
            active = (pd.isna(start) or start <= year_end) and (pd.isna(cabinet_end) or cabinet_end >= year_start)
            if active:
                years_by_name.setdefault(display_name, set()).add(year)

    result = [{"name": name, "years": sorted(yrs)} for name, yrs in years_by_name.items()]
    result.sort(key=lambda r: r["name"])
    return result


def personnes_for_org(collab, rid):
    """Liste des personnes actuellement declarees comme chargees de la
    representation d'interets pour cet acteur (fiche HATVP, section
    "Personnes chargees de la representation d'interets") - un simple
    decompte nominatif, pas l'ETP (equivalent temps plein) de
    15_exercices.csv qui s'est revele trop approximatif/declaratif pour
    ce qu'on veut afficher. Deduplique par (nom, prenom) : le CSV HATVP
    contient parfois la meme personne listee deux fois (une fois avec sa
    fonction renseignee, une fois vide) - un artefact de saisie, pas deux
    personnes distinctes (constate sur Seita : "BRABANT Caroline" en double)."""
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


def main():
    info, exo, clients, collab = load_hatvp()
    dgs = json.load(open(DGS_PATH, encoding="utf-8"))
    dgs_by_folder = {r["folder_org_name"]: r for r in dgs}

    rows = []
    for display_name, categorie, hatvp_denom, dgs_folder in ACTEURS:
        row = {
            "acteur": display_name,
            "categorie": categorie,
            "hatvp_trouve": bool(hatvp_denom),
            "budget_hatvp_bas_2025": None,
            "budget_hatvp_haut_2025": None,
            "personnes_hatvp": [],
            "nb_personnes_hatvp": 0,
            "cabinets_hatvp": [],
            "nb_cabinets_hatvp": 0,
            "dgs_2025_montant_total": None,
            "dgs_2025_detail": None,
            "note": None,
        }

        if hatvp_denom:
            info_row = info[info["denomination"].str.strip() == hatvp_denom]
            if not info_row.empty:
                info_row = info_row.iloc[0]
                rid = info_row["representants_id"]
                org_siret = info_row["identifiant_national"]

                # NOTE : annee_fin est la convention validee (8/9 organisations de
                # reference matchent exactement sur le nombre d'actions). Pour les
                # organisations a exercice decale (Seita, Logista : octobre-septembre),
                # budget/ETP peuvent differer legerement du fichier Excel de
                # reference - probablement un ecart de fraicheur de donnees entre la
                # constitution du fichier et cette extraction (voir rapport), pas une
                # erreur de convention (annee_debut=2025 pointe vers l'exercice en
                # cours non encore cloture, donc 0/0 - pire que annee_fin).
                ex2025 = exo[(exo["representants_id"] == rid) & (exo["annee_fin"] == 2025)]
                if not ex2025.empty:
                    e = ex2025.iloc[0]
                    row["budget_hatvp_bas_2025"] = None if pd.isna(e["montant_depense_inf"]) else int(e["montant_depense_inf"])
                    row["budget_hatvp_haut_2025"] = None if pd.isna(e["montant_depense_sup"]) else int(e["montant_depense_sup"])
                    if e["nombre_activites"] == 0 and pd.isna(e["nombre_salaries"]) and (e["montant_depense_inf"] or 0) == 0:
                        row["note"] = (
                            "Exercice 2025 pas encore publie sur HATVP au moment de cette extraction "
                            "(0 activite, budget 0EUR, moyens non renseignes) - ne pas lire comme un "
                            "montant declare a zero, juste une donnee pas encore disponible."
                        )
                    elif e["nombre_activites"] == 0 and not (pd.isna(e["montant_depense_inf"]) or e["montant_depense_inf"] == 0):
                        # Cas LPV Company (identifie via verification systematique sur les 14
                        # acteurs, cf. conversation) : HATVP distingue la declaration des
                        # "actions" (activites concretes) de celle des "moyens" (budget/ETP).
                        # Une organisation peut n'avoir declare aucune action pour l'exercice
                        # tout en ayant bien declare ses moyens - le budget affiche ici reste
                        # donc valide, ce n'est pas une donnee manquante.
                        row["note"] = (
                            "Aucune action de lobbying declaree pour cet exercice sur HATVP (0 activite), "
                            "mais les moyens (budget/ETP) ont bien ete declares - ce sont deux declarations "
                            "distinctes sur HATVP ; le budget affiche ici est donc valide."
                        )

                cabinets = cabinets_by_year_for_org(clients, info, org_siret)
                row["cabinets_hatvp"] = cabinets
                row["nb_cabinets_hatvp"] = len(cabinets)

                # Personnes chargees de la representation d'interets (fiche HATVP,
                # section dediee) - remplace l'ancien affichage en ETP (juge trop
                # approximatif/declaratif), un simple decompte nominatif comme dans
                # le fichier Excel de reference. Pas specifique a un exercice/annee
                # (photo actuelle de la fiche HATVP), contrairement au budget.
                people = personnes_for_org(collab, rid)
                row["personnes_hatvp"] = people
                row["nb_personnes_hatvp"] = len(people)

                if display_name.startswith("Seita") or display_name == "Logista":
                    row["note"] = (
                        "Budget HATVP 2025 different du fichier Excel de reference pour cet "
                        "acteur (exercice a cheval octobre-septembre) - ecart de fraicheur des donnees "
                        "probable ; actions et cabinets HATVP restent coherents avec le fichier."
                    )

        if display_name == "Confederation des buralistes":
            row["note"] = (
                "Absence de declaration DGS 2025 : les buralistes ont un statut de 'preposes de "
                "l'administration des douanes' agissant sous contrat de gerance (article 568 du Code "
                "general des impots + arrete du 8 juillet 2010), juridiquement distinct de la categorie "
                "'distributeurs' visee par l'article L.3512-7 - confirme par un rapport d'ACT-Alliance "
                "contre le tabac (2025, 'Ressources et strategies d'influence des buralistes en France') "
                "qui demande explicitement d'etendre aux buralistes les obligations de transparence "
                "'deja imposees a l'industrie du tabac au titre de l'article L.3512-7', ce qui confirme "
                "qu'ils n'y sont actuellement pas soumis. Reste une deduction raisonnable et non une "
                "position officielle explicite de la DGS/HATVP elle-meme : aucune jurisprudence ni "
                "circulaire administrative etablissant formellement ce lien causal n'a ete trouvee."
            )

        if dgs_folder and dgs_folder in dgs_by_folder:
            d = dgs_by_folder[dgs_folder]
            row["dgs_2025_montant_total"] = d["total_declare"]
            row["dgs_2025_detail"] = {
                "montant_employes": d["montant_employes"],
                "cabinets": d["cabinets"],
                "montant_avantages": d["montant_avantages"],
            }

        rows.append(row)

    output = {
        "_notes": [
            "Perimetre legal DGS (article L.3512-7 du code de la sante publique, "
            "verifie sur Legifrance) : l'obligation de declaration vise explicitement "
            "les 'fabricants, importateurs et distributeurs de produits du tabac' et "
            "les organisations les representant - aucune mention des cigarettes "
            "electroniques/produits du vapotage, regis par un cadre distinct en droit "
            "francais. Ceci explique l'absence de declaration DGS 2025 pour les "
            "acteurs vapotage (France Vapotage, Fivape/CACE, Sovape, LPV Company) et "
            "pour Aiduce (association d'utilisateurs de cigarette electronique) : ils "
            "sont hors perimetre legal, pas des organisations qui auraient omis de "
            "declarer. En revanche, l'absence de declaration de la Confederation des "
            "buralistes N'EST PAS expliquee par ce meme motif (les buralistes vendent "
            "bien des produits du tabac, ils devraient a priori entrer dans le "
            "perimetre) - reste une question ouverte, non elucidee par cette extraction.",
        ],
        "acteurs": rows,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    for r in rows:
        budget = "-"
        if r["budget_hatvp_bas_2025"] is not None:
            budget = f"{r['budget_hatvp_bas_2025']:,} - {r['budget_hatvp_haut_2025']:,} EUR"
        dgs_txt = f"{r['dgs_2025_montant_total']:,} EUR" if r["dgs_2025_montant_total"] else "aucune declaration"
        print(f"{r['acteur']:55s} | {r['categorie']:35s} | budget={budget:25s} | "
              f"personnes={r['nb_personnes_hatvp']:>2} | cabinets={r['nb_cabinets_hatvp']:>2} | DGS2025={dgs_txt}")


if __name__ == "__main__":
    main()
