"""
Parse les declarations DGS "Transparence Tabac" 2024 (memes formulaire et
structure de sections que 2025, verifie manuellement sur BAT 2024 :
sections 6/7/8 identiques, seule l'annee change dans le texte). Situees
dans un dossier PLAT (pas de sous-dossier dossier-<id> par organisme comme
en 2025) : DGS/Annee 2024/Annexe 2 - dossiers_transparence-tabac-campagne-2025/
avec des fichiers nommes <NOM ORGANISME>-<siret ou id>.pdf (35 PDF, 1 par
organisme).

Reprend la logique de scripts/parse_dgs_2025.py (memes regex de sections),
adaptee a l'annee 2024 et a l'arborescence plate.
"""

import glob
import json
import re

from pypdf import PdfReader

FOLDER = (
    r"Z:\_Récap annuel d'activités\2026\Affaires publiques\National"
    r"\Rapport Lobby FR 2026\DGS\Année 2024"
    r"\Annexe 2 - dossiers_transparence-tabac-campagne-2025"
)
OUTPUT_PATH = "data/dgs_2024_raw.json"

AMOUNT_CHARS = "[0-9  ]+"


def parse_amount(value):
    digits = re.sub("[^0-9]", "", value)
    return int(digits) if digits else None


def normalize(text):
    replacements = {
        "é": "e", "è": "e", "ê": "e",
        "à": "a", "ç": "c",
    }
    out = text
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    return out


def extract_org_name(text):
    m = re.search("Denomination sociale\n(.+)", normalize(text))
    return m.group(1).strip() if m else None


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
        "Avez-vous effectue des depenses de remuneration des personnels employes.*?annee 2024",
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
        "Avez-vous effectue des depenses d'achats de prestations aupres des societes de conseil.*?annee 2024",
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
        "Avez-vous verse des avantages en nature ou en especes.*?annee 2024",
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
    anomalies = []
    pdfs = sorted(glob.glob(FOLDER + "/*.pdf"))
    print(f"=== 2024 : {len(pdfs)} PDF ===")
    for path in pdfs:
        filename = path.replace("\\", "/").split("/")[-1]
        try:
            parsed = parse_pdf(path)
        except Exception as exc:
            print(f"  ERREUR {filename} : {exc}")
            anomalies.append({"file": filename, "error": str(exc)})
            continue

        parsed["source_file"] = filename
        parsed["source_year"] = 2024

        if not parsed["org_name_pdf"]:
            anomalies.append({"file": filename, "issue": "nom d'organisation introuvable"})

        results.append(parsed)
        cabinets_txt = ", ".join(f"{c['name']}={c['amount']}" for c in parsed["cabinets"])
        print(f"  {filename:55s} total={parsed['total_declare']:>10} "
              f"(employes={parsed['montant_employes']}, cabinets=[{cabinets_txt}], "
              f"avantages={parsed['montant_avantages']})")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    zero = [r for r in results if r["total_declare"] == 0]
    print(f"\nTotal dossiers : {len(results)}")
    print(f"A 0 : {len(zero)} -> {[r['source_file'] for r in zero]}")
    if anomalies:
        print(f"Anomalies : {anomalies}")
    print(f"Ecrit dans {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
