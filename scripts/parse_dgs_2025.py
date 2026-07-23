"""
Parse les 32 PDF d'export de declarations DGS "Transparence Tabac" 2025
(telecharges manuellement par l'utilisateur, page source protegee par
CAPTCHA donc non automatisable) situes dans :
C:\\Users\\MartinDrago\\Downloads\\declarations_2025\\Declarations 2025\\
dossier-<id> - <Nom>\\export-<id>-...pdf (1 PDF par dossier, verifie sur les 32).

Chaque PDF est un export du formulaire demarches-simplifiees.fr avec une
structure de sections stable (verifiee sur plusieurs echantillons) :
- Section 2 "Entreprise ou entite declarante" -> "Denomination sociale"
- Section 6 "Depenses de remuneration des personnels..." -> Oui/Non,
  si Oui : "Montant total annuel brut" + "Nombre de personnels remunerees"
- Section 7 "Depenses d'achats de prestations aupres des societes de
  conseil..." -> Oui/Non, si Oui : une ou plusieurs paires "Montant total
  annuel des achats de missions ou prestations..." + "Denomination sociale
  de la societe prestataire" (1 paire par cabinet)
- Section 8 "Avantages en nature ou en especes..." -> Oui/Non, si Oui :
  montant total (pas d'exemple "Oui" trouve dans l'echantillon, gere par
  precaution)

Pas de champ "portes tournantes" dans ce formulaire 2025 (verifie : absent
de tous les PDF) - contrairement au fichier Excel de reference qui a une
colonne "Nombre de portes tournantes" pour la DGS 2024. Cette donnee n'est
donc simplement pas disponible pour 2025, ce n'est pas un bug d'extraction.

Filtre applique (demande explicite) : une organisation dont le total
declare (remuneration personnels + achats cabinets + avantages) vaut 0 est
EXCLUE du tableau final.
"""

import glob
import json
import re

from pypdf import PdfReader

BASE_DIR = "C:/Users/MartinDrago/Downloads/declarations_2025/Declarations 2025"
OUTPUT_PATH = "data/dgs_2025_raw.json"

AMOUNT_CHARS = "[0-9  ]+"


def parse_amount(value):
    digits = re.sub("[^0-9]", "", value)
    return int(digits) if digits else None


def extract_org_name(text):
    m = re.search("Denomination sociale\n(.+)", normalize(text))
    return m.group(1).strip() if m else None


def normalize(text):
    replacements = {
        "é": "e", "è": "e", "ê": "e",
        "à": "a", "ç": "c",
    }
    out = text
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    return out


def extract_section(norm_text, question_pattern, end_pattern):
    m = re.search(question_pattern + "\\s*\\?\\s*\n(Oui|Non)\n", norm_text, re.DOTALL)
    if not m:
        return None, ""
    answer = m.group(1) == "Oui"
    start = m.end()
    end_m = re.search(end_pattern, norm_text[start:])
    section_text = norm_text[start:start + end_m.start()] if end_m else norm_text[start:]
    return answer, section_text


def parse_pdf(path):
    reader = PdfReader(path)
    raw_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    text = normalize(raw_text)

    org_name = extract_org_name(raw_text)

    has_employe, employe_section = extract_section(
        text,
        "Avez-vous effectue des depenses de remuneration des personnels employes.*?annee 2025",
        "7\\. Depenses d'achats",
    )
    montant_employes = 0
    nb_personnels = None
    if has_employe:
        m = re.search("Montant total annuel brut\\s*\n(" + AMOUNT_CHARS + ")", employe_section)
        if m:
            montant_employes = parse_amount(m.group(1)) or 0
        m = re.search("Nombre de personnels remunerees?\\s*\n(\\d+)", employe_section)
        if m:
            nb_personnels = int(m.group(1))

    has_cabinet, cabinet_section = extract_section(
        text,
        "Avez-vous effectue des depenses d'achats de prestations aupres des societes de conseil.*?annee 2025",
        "8\\. Avantages en nature",
    )
    cabinets = []
    if has_cabinet:
        amount_iter = list(re.finditer(
            "Montant total annuel des achats de missions ou prestations.*?association\\s*\n(" + AMOUNT_CHARS + ")\n",
            cabinet_section,
            re.DOTALL,
        ))
        name_iter = list(re.finditer(
            "Denomination sociale de la societe prestataire\\s*\n(.+)",
            cabinet_section,
        ))
        for amt_m, name_m in zip(amount_iter, name_iter):
            amount = parse_amount(amt_m.group(1))
            name = name_m.group(1).strip()
            cabinets.append({"name": name, "amount": amount})

    has_avantages, avantages_section = extract_section(
        text,
        "Avez-vous verse des avantages en nature ou en especes.*?annee 2025",
        "9\\. Je confirme",
    )
    montant_avantages = 0
    if has_avantages:
        m = re.search("[Mm]ontant total annuel.*?\n(" + AMOUNT_CHARS + ")", avantages_section)
        if m:
            montant_avantages = parse_amount(m.group(1)) or 0

    total_cabinets = sum(c["amount"] for c in cabinets if c["amount"])
    total_declare = montant_employes + total_cabinets + montant_avantages

    return {
        "org_name_pdf": org_name,
        "montant_employes": montant_employes,
        "nb_personnels": nb_personnels,
        "cabinets": cabinets,
        "nb_cabinets": len(cabinets),
        "total_cabinets": total_cabinets,
        "montant_avantages": montant_avantages,
        "total_declare": total_declare,
    }


def main():
    results = []
    for folder in sorted(glob.glob(BASE_DIR + "/dossier-*")):
        folder_name = folder.replace("\\", "/").split("/")[-1]
        m = re.match(r"dossier-(\d+) - (.+)", folder_name)
        dossier_id, folder_org_name = m.group(1), m.group(2)
        pdfs = glob.glob(folder + "/*.pdf")
        if len(pdfs) != 1:
            print("ANOMALIE : " + folder_name + " a " + str(len(pdfs)) + " PDF (attendu 1)")
            continue
        parsed = parse_pdf(pdfs[0])
        parsed["dossier_id"] = dossier_id
        parsed["folder_org_name"] = folder_org_name
        results.append(parsed)
        print("{:45s} total={:>10} (employes={}, cabinets={}/{}, avantages={})".format(
            folder_org_name, parsed["total_declare"], parsed["montant_employes"],
            parsed["total_cabinets"], parsed["nb_cabinets"], parsed["montant_avantages"]
        ))

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    zero = [r for r in results if r["total_declare"] == 0]
    nonzero = [r for r in results if r["total_declare"] > 0]
    print("")
    print("Total dossiers : " + str(len(results)))
    print("A 0 (exclus du tableau final) : " + str(len(zero)) + " -> " + str([r["folder_org_name"] for r in zero]))
    print("Avec depense > 0 (retenus) : " + str(len(nonzero)))


if __name__ == "__main__":
    main()
