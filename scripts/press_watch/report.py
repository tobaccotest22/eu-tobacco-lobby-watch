"""
Génération du rapport Markdown d'une exécution (pour la vérification humaine
avant mise en ligne, cf. section 8 point 6 du cahier des charges).
"""

from datetime import date


def _md_escape(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def _acces(art: dict) -> str:
    if art.get("fetch_error"):
        return f"échec fetch ({art['fetch_error']})"
    if art.get("paywalled"):
        return "payant / partiel"
    return "libre"


def write_report(path, *, window, articles, published, review_records, excluded, errored,
                 dup_groups, dropped_ids, daily, discovery_meta, log, manual, dry_run):
    since, until = window
    L = []
    w = L.append

    w(f"# Rapport d'exécution — Veille Presse ({since} → {until})")
    w("")
    w(f"- Mode : **{'manuel (agent = modèle)' if manual else 'API Claude'}**"
      f"{' · dry-run' if dry_run else ''}")
    w(f"- Généré le : {date.today().isoformat()}")
    w(f"- Candidats classés : {len(articles)} — "
      f"publiés {len(published) - len(dropped_ids)}, revue {len(review_records)}, "
      f"exclus {len(excluded)}, erreurs {len(errored)}, doublons écartés {len(dropped_ids)}")
    w("")

    # --- flux -----------------------------------------------------------
    w("## 1. Flux interrogés")
    w("")
    w("| Flux | Entrées | État |")
    w("|---|---:|---|")
    for f in discovery_meta["feeds"]:
        state = f["error"] if f["error"] else "ok"
        w(f"| {_md_escape(f['name'])} | {f['entries']} | {_md_escape(state)} |")
    w("")

    # --- journal ------------------------------------------------------
    w("## 2. Journal de découverte")
    w("")
    for line in log:
        w(f"- {line}")
    w("")

    # --- tableau des candidats classés --------------------------------
    w("## 3. Candidats classés")
    w("")
    w("| Source | Titre | Date | Accès | Pertinent | Conf. | source_type | Angle |")
    w("|---|---|---|---|---|---|---|---|")
    for art in sorted(articles, key=lambda a: (a.get("published") or "", a.get("source_name") or "")):
        c = art.get("classified")
        if not c:
            w(f"| {_md_escape(art.get('source_name') or art.get('site_name'))} "
              f"| {_md_escape(art['title'])} | {art.get('published') or '?'} "
              f"| {_acces(art)} | ERREUR | — | — | {_md_escape(art.get('classification_error',''))} |")
            continue
        dup = " · **doublon écarté**" if art["id"] in dropped_ids else ""
        w(f"| {_md_escape(art.get('source_name') or art.get('site_name'))} "
          f"| {_md_escape(art['title'])} | {art.get('published') or '?'} "
          f"| {_acces(art)} | {'oui' if c['pertinent'] else 'non'} | {c['confiance']} "
          f"| {c['source_type']} | {_md_escape(c['angle'])}{dup} |")
    w("")

    # --- résumés des articles publiés ---------------------------------
    w("## 4. Articles retenus (résumés produits)")
    w("")
    kept = [a for a in published if a["id"] not in dropped_ids]
    if not kept:
        w("_Aucun._")
    for art in kept:
        c = art["classified"]
        w(f"### {_md_escape(art['title'])}")
        w(f"- {art.get('source_name') or art.get('site_name')} · {art.get('published') or '?'} "
          f"· {c['source_type']} · confiance {c['confiance']}"
          f"{' · sous abonnement' if c['sous_abonnement'] else ''}")
        w(f"- {art.get('final_url') or art['url']}")
        w(f"- **Angle** : {c['angle']}")
        w(f"- **Résumé** : {c['resume']}")
        w(f"- **entites_citees** : {', '.join(c['entites_citees'])}")
        if art.get("schema_warnings"):
            w(f"- ⚠️ schéma : {'; '.join(art['schema_warnings'])}")
        w("")

    # --- exclusions ---------------------------------------------------
    w("## 5. Articles exclus")
    w("")
    if not excluded:
        w("_Aucun._")
    else:
        w("| Source | Titre | source_type | Raison |")
        w("|---|---|---|---|")
        for art in excluded:
            c = art["classified"]
            w(f"| {_md_escape(art.get('source_name') or art.get('site_name'))} "
              f"| {_md_escape(art['title'])} | {c['source_type']} "
              f"| {_md_escape(c['raison_exclusion'])} |")
    w("")

    # --- doublons ---------------------------------------------------
    w("## 6. Doublons détectés")
    w("")
    if not dup_groups:
        w("_Aucun._")
    for g in dup_groups:
        w(f"- **Gardé** : {_md_escape(g['kept_title'])} ({_md_escape(g['kept_source'] or '')})")
        for d in g["dropped_detail"]:
            w(f"  - écarté : {_md_escape(d['title'])} ({_md_escape(d['source'] or '')})")
        w(f"  - entités communes : {', '.join(g['shared_entities'])}")
    w("")

    # --- file de revue --------------------------------------------
    w("## 7. File de validation humaine (confiance faible, dédoublonnée)")
    w("")
    if not review_records:
        w("_Aucun._")
    else:
        w("| Source | Titre | Date | Angle | Résumé |")
        w("|---|---|---|---|---|")
        for r in review_records:
            w(f"| {_md_escape(r.get('source_name'))} | {_md_escape(r['title'])} "
              f"| {r.get('published') or '?'} | {_md_escape(r.get('angle'))} "
              f"| {_md_escape(r.get('resume'))} |")
    w("")

    # --- synthèses du jour --------------------------------------------
    w("## 8. Texte de synthèse produit chaque jour")
    w("")
    for s in sorted(daily, key=lambda x: x["date"]):
        w(f"### {s['date']}  ·  {s['type']}  ·  {s['n_articles']} article(s)")
        w(f"> {s['resume_du_jour']}")
        if s["articles_source"]:
            w("")
            w("Sources : " + "; ".join(s["articles_source"]))
        w("")

    # --- pré-filtre écarté ------------------------------------------
    w("## 9. Écartés au pré-filtre thématique (pour contrôle des faux négatifs)")
    w("")
    pf = discovery_meta.get("prefiltered_out", [])
    if not pf:
        w("_Aucun._")
    else:
        w("| Source | Titre |")
        w("|---|---|")
        for d in pf[:80]:
            w(f"| {_md_escape(d['source'])} | {_md_escape(d['title'])} |")
        if len(pf) > 80:
            w(f"| … | (+{len(pf) - 80} autres) |")
    w("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
