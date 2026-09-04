"""
Pipeline de la section « Veille - Presse » du site EU Tobacco Lobby Watch.

Chaîne complète, dans l'ordre d'exécution (voir scripts/fetch_press_watch.py) :

1. sources.py    - définition des flux (Google News RSS par langue + flux directs
                   des sources prioritaires de la section 3 du cahier des charges)
2. feeds.py      - récupération et parsing RSS/Atom, fenêtre de dates
3. resolve.py    - résolution des liens de redirection news.google.com -> éditeur
4. extract.py    - extraction du texte réellement visible + détection paywall
5. classify.py   - prompt de classification (section 1) -> JSON strict par article
6. dedupe.py     - dédoublonnage par `entites_citees` normalisées (section 2)
7. synthesize.py - phrase de synthèse du jour (section 7)
8. store.py      - écriture accumulée dans data/press_watch.json

Le prompt de classification et le prompt de synthèse sont recopiés VERBATIM
depuis prompt_test_veille_presse_tabac_UE2.md (sections 1 et 7). Toute
modification du texte de ces prompts doit être répercutée dans le cahier des
charges, et inversement.
"""
