# Notes de développement

## Incohérence de données dans le registre officiel des réunions du Parlement européen

`scripts/fetch_keyword_meetings.py` (recherche libre par mot-clé sur
`europarl.europa.eu/meps/en/search-meetings`, intégré à `index.html` depuis le
2026-07-17, cf. priorités ci-dessous) a mis en évidence que le champ `lobbyist_id` de l'export
CSV est parfois vide alors que le nom de l'organisation est bien renseigné en
toutes lettres dans `attendees` - y compris pour des organisations qu'on
suit déjà avec un register_id connu (ex : plusieurs réunions listent
"British American Tobacco" en texte mais sans le `lobbyist_id`
"2427500988-58" correspondant, alors que d'autres réunions avec la même
organisation l'ont correctement).

Exemple observé (recherche mot-clé "tobacco", 2026) :
```
Tobacco Taxation Directive,257027,NAVARRETE ROJAS Fernando,2026-03-11,Member,,British American Tobacco,        <- lobbyist_id vide
Tematiche Sanitarie,197607,FIOCCHI Pietro,2025-12-16,Member,,British American Tobacco,2427500988-58              <- lobbyist_id présent
```

Ce n'est pas un bug de notre script : c'est une incohérence dans la manière
dont certains eurodéputés (ou leurs équipes) déclarent leurs réunions - le
nom est saisi à la main mais pas toujours relié à l'identifiant du registre.

**À corriger plus tard** : quand on reprendra `fetch_keyword_meetings.py`,
matcher aussi par nom d'organisation (en plus du `lobbyist_id`) pour éviter
de classer à tort ces réunions comme provenant d'un acteur "hors liste".

## Priorités (état au 2026-07-17)

1. ✅ Fait : `data/entities.json` (46 organisations avec register_id),
   `scripts/fetch_lobbyfacts.py` (LobbyFacts + réunions EC + fiche registre
   officielle : budget/personnes/cabinets), `scripts/fetch_ep_meetings.py`
   (réunions PE par organisation + agrégat), `scripts/fetch_budget_history.py`
   (historique budget LobbyFacts par année), `.github/workflows/update_data.yml`.
2. ✅ Intégré : `scripts/fetch_keyword_meetings.py` alimente désormais la
   section "Dernières réunions" de `index.html` (réunions Parlement hors de
   nos organisations suivies, via `_aggregate.ep_meetings_outside_our_46`),
   avec une liste d'exclusion manuelle pour les ONG de santé publique.
   La correction "matcher aussi par nom d'organisation" ci-dessus reste à
   faire : en l'état, une organisation déjà suivie peut apparaître comme
   "hors liste" si son `lobbyist_id` est vide sur une réunion donnée (dans ce
   cas elle s'affiche simplement sous son nom, sans lien vers sa fiche
   registre, ce qui n'est pas trompeur mais reste une piste d'amélioration).
3. `index.html`, `statistiques.html`, `organisations.html` : tableau de bord
   réparti sur 3 pages (accueil condensé avec sections dépliables,
   statistiques/tendances, liste complète des organisations).
