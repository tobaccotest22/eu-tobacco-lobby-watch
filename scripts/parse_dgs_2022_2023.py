"""
Parseur pour le format DGS 2022/2023 (fiche 1 page, different du formulaire
multi-pages "demarches-simplifiees" utilise en 2024/2025). Les cabinets sont
presentes en colonnes ("Prestataire 1/2/3/4"), et pypdf aplatit tout en une
seule ligne de texte quand plusieurs colonnes sont remplies - il faut les
positions x/y des mots (pdfplumber) pour retrouver quel montant va avec quel
nom de cabinet.

Approche retenue (2e version, la 1ere - bucketer sur les positions x du
libelle "Prestataire N" - s'est reveleee fausse : le decalage entre les
libelles d'en-tete et les colonnes de donnees varie d'un document a l'autre,
ce qui coupait des montants en plein milieu, ex. "28 800" -> "28" et "800"
dans 2 colonnes differentes chez PMI). A la place : sur chaque ligne de
donnees (montants, noms), on detecte les colonnes par un simple saut
horizontal (gap) entre mots consecutifs - un ecart de plus de ~20pt indique
une nouvelle colonne, un ecart plus petit reste dans le meme mot/nom. Cette
methode ne depend d'aucun gabarit fixe a 4 colonnes et s'adapte au nombre
reel de cabinets presents (1 a 4).

Validee sur 3 PDF (BAT 2023, BAT 2022, PMI 2023) avant generalisation, cf.
conversation. Ce script traite maintenant l'ensemble des dossiers 2022 et
2023 (43 + 35 PDF), un par un, en isolant les erreurs (un PDF en echec ne
bloque pas les autres - il est liste dans "_anomalies" pour revue manuelle).

Ecrit data/dgs_2022_raw.json et data/dgs_2023_raw.json.
"""

import glob
import json
import re
from collections import defaultdict

import pdfplumber

GAP_THRESHOLD = 20

FOLDERS = {
    2022: r"Z:\_Récap annuel d'activités\2026\Affaires publiques\National\Rapport Lobby FR 2026\DGS\Année 2022\Déclarations à publier",
    2023: r"Z:\_Récap annuel d'activités\2026\Affaires publiques\National\Rapport Lobby FR 2026\DGS\Année 2023\Déclarations à publier",
}


def group_lines(words, tol=2.5):
    """Regroupe les mots par ligne (meme 'top' a tol pres)."""
    lines = defaultdict(list)
    tops = []
    for w in words:
        top = w["top"]
        match = next((t for t in tops if abs(t - top) <= tol), None)
        if match is None:
            tops.append(top)
            match = top
        lines[match].append(w)
    return {t: sorted(ws, key=lambda w: w["x0"]) for t, ws in lines.items()}


def find_line_containing(lines, needle):
    for top, words in sorted(lines.items()):
        text = " ".join(w["text"] for w in words)
        if needle in text:
            return top, words
    return None, None


def words_after_label(words, label_word):
    """Renvoie les mots situes apres le dernier mot du libelle (ex.
    'association' ou 'prestataire'), identifie par son propre texte plutot
    que par une position x fixe - le libelle et les colonnes de donnees
    n'ont pas le meme decalage horizontal d'un document a l'autre."""
    idx = next((i for i, w in enumerate(words) if w["text"] == label_word), None)
    if idx is None:
        return []
    return words[idx + 1:]


def split_into_columns(words, gap=GAP_THRESHOLD):
    """Coupe une ligne de mots (deja triee par x0, deja debarrassee du
    libelle) en colonnes des qu'un ecart horizontal > gap separe deux mots
    consecutifs."""
    columns = []
    current = []
    prev_x1 = None
    for w in words:
        if prev_x1 is not None and w["x0"] - prev_x1 > gap:
            columns.append(current)
            current = []
        current.append(w)
        prev_x1 = w["x1"]
    if current:
        columns.append(current)
    return columns


def parse_amount(tokens):
    text = "".join(w["text"] for w in tokens)
    digits = re.sub(r"[^\d,]", "", text)
    digits = digits.split(",")[0]  # on ignore les centimes
    return int(digits) if digits else None


def find_on_any_page(pdf, needle):
    """Cherche la ligne contenant `needle` sur chaque page, dans l'ordre -
    la fiche tient normalement sur 1 page mais on reste robuste si une
    section deborde sur la page suivante."""
    for page in pdf.pages:
        words = page.extract_words()
        lines = group_lines(words)
        top, line_words = find_line_containing(lines, needle)
        if line_words:
            return line_words
    return None


def parse_pdf(path):
    with pdfplumber.open(path) as pdf:
        org_words = find_on_any_page(pdf, "Dénomination sociale")
        org_name = " ".join(w["text"] for w in org_words[2:]) if org_words else None

        rem_words = find_on_any_page(pdf, "Montant total annuel")
        montant_employes = None
        if rem_words:
            idx = next((i for i, w in enumerate(rem_words) if w["text"] == "€"), None)
            if idx is not None:
                montant_employes = parse_amount(rem_words[idx + 1:])

        amount_words = find_on_any_page(pdf, "association")
        amount_data = words_after_label(amount_words, "association") if amount_words else []
        amount_columns = split_into_columns(amount_data)
        montants_cabinets = [parse_amount(c) for c in amount_columns]

        name_words = find_on_any_page(pdf, "Dénomination sociale de la société prestataire")
        name_data = words_after_label(name_words, "prestataire") if name_words else []
        name_columns = split_into_columns(name_data)
        noms_cabinets = [" ".join(w["text"] for w in c) for c in name_columns]

        cabinets = [
            {"name": n, "amount": a}
            for n, a in zip(noms_cabinets, montants_cabinets)
        ]

        total_cabinets = sum(c["amount"] for c in cabinets if c["amount"])
        total_declare = (montant_employes or 0) + total_cabinets

        return {
            "org_name_pdf": org_name,
            "montant_employes": montant_employes,
            "cabinets": cabinets,
            "nb_cabinets": len(cabinets),
            "total_cabinets": total_cabinets,
            "total_declare": total_declare,
        }


def main():
    for year, folder in FOLDERS.items():
        results = []
        anomalies = []
        pdfs = sorted(glob.glob(folder + "/*.pdf"))
        print(f"=== {year} : {len(pdfs)} PDF ===")
        for path in pdfs:
            filename = path.replace("\\", "/").split("/")[-1]
            try:
                parsed = parse_pdf(path)
            except Exception as exc:
                print(f"  ERREUR {filename} : {exc}")
                anomalies.append({"file": filename, "error": str(exc)})
                continue

            parsed["source_file"] = filename
            parsed["source_year"] = year

            issues = []
            if not parsed["org_name_pdf"]:
                issues.append("nom d'organisation introuvable")
            if parsed["montant_employes"] is None:
                issues.append("montant salaries introuvable")
            if any(c["amount"] is None or not c["name"] for c in parsed["cabinets"]):
                issues.append("cabinet(s) avec nom ou montant manquant")
            if issues:
                anomalies.append({"file": filename, "issues": issues, "parsed": parsed})

            results.append(parsed)
            cabinets_txt = ", ".join(f"{c['name']}={c['amount']}" for c in parsed["cabinets"])
            print(f"  {filename:55s} | {str(parsed['org_name_pdf']):40s} | "
                  f"salaries={parsed['montant_employes']} | cabinets=[{cabinets_txt}]")

        output_path = f"data/dgs_{year}_raw.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"\n{len(results)} PDF traites, {len(anomalies)} anomalie(s) a revoir.")
        if anomalies:
            print("Anomalies :")
            for a in anomalies:
                print(f"  - {a['file']} : {a.get('issues', a.get('error'))}")
        print(f"Ecrit dans {output_path}\n")


if __name__ == "__main__":
    main()
