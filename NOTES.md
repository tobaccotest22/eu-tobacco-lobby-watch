# Notes de développement

## Incohérence de données dans le registre officiel des réunions du Parlement européen

`scripts/fetch_keyword_meetings.py` (recherche libre par mot-clé sur
`europarl.europa.eu/meps/en/search-meetings`, mis de côté pour l'instant, cf.
priorités ci-dessous) a mis en évidence que le champ `lobbyist_id` de l'export
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

## Priorités (état au 2026-07-10)

1. ✅ Fait : `data/entities.json` (46 organisations avec register_id),
   `scripts/fetch_lobbyfacts.py` (LobbyFacts + réunions EC + fiche registre
   officielle : budget/personnes/cabinets), `scripts/fetch_ep_meetings.py`
   (réunions PE par organisation + agrégat), `.github/workflows/update_data.yml`.
2. 🚧 En pause : `scripts/fetch_keyword_meetings.py` (total "tabac/nicotine,
   tous acteurs confondus" par recherche mot-clé) - fonctionnel mais
   nécessite la correction ci-dessus avant d'être intégré au tableau de bord.
3. En cours : `index.html` - tableau de bord statique à partir des données
   fiables déjà disponibles (sans la section mots-clés pour l'instant).
