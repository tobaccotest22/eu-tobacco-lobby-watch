# Veille Presse — rapport de test avant mise en ligne

> **Statut : à valider.** Rien n'est branché sur le site. Ce document est le
> rapport demandé au §8 point 6 du cahier des charges
> (`prompt_test_veille_presse_tabac_UE2.md`) : le pipeline a tourné sur une
> fenêtre de 4 jours réels (2026-09-01 → 2026-09-04) **sans affichage public**.
> Merci de le relire (et de le faire relire à Claude côté chat) avant tout
> passage en production.

Généré : 2026-09-04 · branche `feat/press-watch-pipeline` · exécution
`--from-candidates` + `--classifications` (voir « Méthode » plus bas).

---

## 1. Méthode

| Étape | Comment elle a tourné pour ce test |
|---|---|
| Découverte | Code réel : `scripts/fetch_press_watch.py` a interrogé les 24 flux (Google News fr/en/de/it + 6 flux directs) et récupéré le texte réellement visible à chaque URL. |
| Résolution des liens Google News | Code réel : décodage `news.google.com/rss/articles/…` via l'appel interne `batchexecute` (rpc `Fbv4je`). |
| Classification (prompt §1) | **Simulée** : faute de clé API pour le test, Claude (Sonnet 5) a joué le rôle du modèle, en appliquant le prompt §1 recopié verbatim au texte réellement récupéré. En production : un appel `messages.create` par article (`ANTHROPIC_API_KEY` en secret GitHub). |
| Dédoublonnage (§2) | Code réel : `press_watch/dedupe.py`. |
| Synthèse du jour (§7) | **Simulée** de la même façon (prompt §7 verbatim, à partir des seules sorties de classification). |
| Écriture | Code réel : `data/press_watch.dryrun.json` (le vrai `data/press_watch.json` n'a pas été touché). |

> Autrement dit : toute la plomberie (découverte, fetch, résolution de liens,
> dédoublonnage, agrégation, format de sortie) est le code de production. Seuls
> les deux appels LLM ont été rejoués à la main, exactement comme au round 1 de
> l'éval du prompt.

---

## 2. Découverte — volumétrie

- **~900 entrées brutes** collectées sur les 24 flux (891 sur ce passage).
- **33** dans la fenêtre 2026-09-01 → 2026-09-04 (les autres sont plus anciennes).
- **30 URL uniques** après résolution des liens et dédoublonnage par URL.
- **0 lien Google News non résolu** (le décodeur `batchexecute` a fonctionné sur
  tous les liens `news.google.com` de la fenêtre ; sur un passage antérieur à
  6 jours, 30/30 résolus également, alors qu'une résolution naïve échouait sur
  30/48).
- **30 candidats** après le pré-filtre thématique (0 écarté sur ce passage ; sur
  la fenêtre 6 jours, 1 seul écarté : un article Euronews sur l'adhésion de
  l'Islande à l'UE — à juste titre).

### État des flux

| Flux | Statut | Note |
|---|---|---|
| Corporate Europe Observatory, Vaping Post FR, pro-rauchfrei, Tobacco Reporter, TobaccoTactics, Tobacco Journal International | ✅ | flux directs, RSS valides |
| Google News fr / en / it (13 requêtes) | ✅ | 3 à 100 entrées par requête |
| Google News de (4 requêtes) | ✅ 3/4 | `Tabakproduktrichtlinie Revision` renvoie 0 sur la fenêtre (pas une anomalie) |
| **Génération Sans Tabac, STOP, TabakNee** (flux directs) | ⚠️ désactivés | leur `/feed/` renvoie un `<channel>` vide à tout user-agent (bug de cache plugin ou anti-bot). **Couverts via Google News** (leurs articles y sont bien indexés — GST est effectivement remonté dans ce test). À re-tester périodiquement. |
| **The Examination** (flux direct) | ⚠️ absent | pas de flux RSS public trouvé. Couvert via Google News (article #16 de l'éval bien remonté). |
| **Politico, Euractiv** (fetch direct) | ⚠️ | domaines qui bloquent le crawler (cf. §9 du cahier). **Mais Google News fournit titre + date + extrait** via `batchexecute` : l'article Euractiv « Swedish election leaves EU tobacco tax deal in limbo » est bien remonté (repris aussi par Tobacco Journal International, cf. §5). |

---

## 3. Résultat global (4 jours)

| | Nombre |
|---|---:|
| Candidats classés | 30 |
| **Publiés** (pertinent + confiance ≥ moyenne, après dédoublonnage) | **6** |
| En file de validation humaine (confiance faible) | 2 (après dédoublonnage interne de 4 → 2) |
| Exclus | 20 |
| Erreurs de classification | 0 |
| Doublons écartés (pool publiable) | 0 |

---

## 4. Articles publiés (6) — résumés produits

| # | Date | Source | Titre | Angle | Confiance |
|---|---|---|---|---|---|
| 1 | 01/09 | Tobacco Journal International | Swedish vote may delay EU tax agreement | élections suédoises → retard possible de l'accord sur la directive accise tabac | haute |
| 2 | 02/09 | Vaping Post | TPD et lobbying de Big Tobacco : la médiatrice européenne ouvre une enquête | enquête de la médiatrice sur les liens DG TRADE ↔ industrie du tabac | haute |
| 3 | 02/09 | Tageblatt.lu | Frieden kritisiert EU-Tabaksteuer… | le Luxembourg conteste les taux minimaux d'accise tabac de l'UE | moyenne |
| 4 | 03/09 | The Examination | EU countries clash over nicotine pouch taxes, stalling broader tobacco talks | blocage suédois de la taxe minimale sur les sachets de nicotine au Conseil | haute |
| 5 | 03/09 | Génération Sans Tabac | EU Reporter, une tribune bruxelloise au service de l'industrie du tabac | décryptage d'un média bruxellois relayant les arguments pro-industrie | moyenne |
| 6 | 04/09 | Follow the Money | Big Tobacco stops Brussels from getting tough on vaping, despite proven harm | enquête sur le lobbying pro-vape de l'industrie à Bruxelles | haute |

Résumés complets et `entites_citees` : voir la section 4 du rapport machine
détaillé, `docs/press-watch-test-run-machine.md` (généré automatiquement par
`--report`). Points de contrôle :

- **#6 (Follow the Money)** : `sous_abonnement = true`, résumé préfixé
  « Accès abonné — », entièrement construit sur l'encadré public
  « This article in 1 minute » (récupéré intégralement par l'extracteur). Aucune
  information au-delà de ce qui est public.
- **#5 (GST)** : classé `blog_specialise` (analyse originale d'une ONG sur son
  propre site), pas `contenu_sponsorise` — conforme à la règle §1 révisée.
  ⚠️ le pipeline a récupéré la version `/en/` (traduction anglaise) d'un texte
  français ; `langue_source` a été mis à `fr`. À surveiller : GST publie en
  FR **et** EN sous des URL différentes → risque de doublon FR/EN (ici un seul
  est remonté).
- **#3 (Tageblatt)** : c'est le **cas limite « article multi-sujets »** du round 2
  (§5.2 du cahier). L'article parle surtout de la visite de Costa (Ukraine, union
  des marchés de capitaux, budget UE) ; la fiscalité tabac est **un** point de
  friction, mais **titré**. Classé `pertinent: true, confiance: moyenne` — le
  résumé attribue clairement la portée limitée (« traite la fiscalité du tabac
  comme l'un des points de friction, sans détailler la négociation »). À trancher :
  est-ce le bon appel, ou faut-il exiger que le sujet UE soit l'objet principal ?
- **#1 vs #4** : même dossier (blocage suédois / directive fiscale au Conseil),
  mais **2 jours d'écart** et angles différents (retard lié aux élections vs
  blocage estival sur les sachets). Le dédoublonnage **ne les fusionne pas**
  (fenêtre ±1 jour) — c'est le comportement voulu ; la synthèse du jour les relie.

---

## 5. Articles exclus (20) — échantillon avec raison

| Source | Titre | Raison |
|---|---|---|
| Vaping Post | Au-delà du buzz : ARGUS Multi-Ohm Cartridge… | publi-rédactionnel (`contenu_sponsorise`) : promo produit, chiffres fournis par la marque |
| Vaping Post | Royaume-Uni : l'UKVIA tape du poing sur la table | sujet national (Royaume-Uni, hors UE) |
| Vaping Post | Vapoter à l'adolescence… espérance de vie | santé publique générale, ni TPD/TTD ni lobbying UE |
| Tobacco Reporter ×8 | Altria/FDA, Reynolds/Wyden, Indonésie, Malaisie, Trump/pasteur, Reynolds/Altria brevets, Hongrie contrebande, Australie tabac illicite | sujets nationaux hors UE ou contrebande |
| Tobacco Journal International ×6 | Davidoff/ProCigar, Australie baisse accise, HMRC accise vape UK, Malawi recettes tabac, CDC conseiller (US), « Creating change » (initiative eau potable) | hors périmètre / national hors UE / RSE |
| Tobacco Journal International | More than a filter | publi-rédactionnel (`contenu_sponsorise`) : initiative RSE du secteur |

Tableau complet : section 5 du rapport machine.

**Observation** : le gros du bruit vient de **Tobacco Reporter** et **Tobacco
Journal International** (presse professionnelle du secteur) qui couvrent
massivement l'actualité industrielle mondiale. Le pré-filtre les laisse passer
(ils contiennent « tobacco », « EU »…) et c'est la classification qui tranche.
14 exclusions sur 20 viennent de ces deux flux. C'est le fonctionnement attendu
(pré-filtre permissif, LLM décideur) mais ça a un coût en appels API — voir
« Points à décider ».

---

## 6. File de validation humaine (2 après dédoublonnage)

Les 4 dépêches luxembourgeoises « Frieden maintient son opposition à la taxe
tabac de l'UE » (Virgule.lu ×2, Luxemburger Wort ×2) : **articles non
récupérables** (HTTP 302/403, cookie-wall Mediahuis). Seul le titre est visible.

- **Étiquette d'accès `non_recupere`** (voir §6-bis) — distincte de
  `sous_abonnement`. Le résumé est réécrit avec le préfixe
  « Article non récupéré — » au lieu de « Accès abonné — ».
- Classées `pertinent: true` (c'est l'**exception §1** : un État membre qui se
  positionne dans la négociation TTD au Conseil, pas une loi nationale).
- **Jamais publiées automatiquement** : le pipeline force en file de revue tout
  article `non_recupere`, même si le modèle était confiant sur le titre (ici de
  toute façon `confiance: faible`).
- Le dédoublonnage interne à la file les a fusionnées 4 → 2 (une par journée).
- Le même événement est **par ailleurs publié** via l'article Tageblatt (#3),
  lui lisible. → un relecteur peut soit valider une des dépêches en complément,
  soit les ignorer puisque Tageblatt couvre déjà le sujet.

⚠️ **Limite acceptée** (§8.5) : le dédoublonnage ne croise pas la file de revue
et le pool publiable. Ici l'article Tageblatt (publié) et les dépêches Frieden
(revue) ne sont pas rapprochés automatiquement. Pas corrigé pour l'instant.

---

## 6-bis. Étiquettes d'accès

Le pipeline distingue trois états, **calculés à partir de ce qui s'est réellement
passé à l'extraction** (pas par le modèle) :

| `acces` | Sens | Affichage | Exemple du test |
|---|---|---|---|
| `libre` | article intégralement lisible | — | The Examination, Vaping Post, Tageblatt… |
| `sous_abonnement` | l'éditeur expose un **teaser public volontaire** (chapô, encadré « This article in 1 minute »). Contenu partiellement connu et fiable. | « sous abonnement » + résumé préfixé « Accès abonné — » | **Follow the Money** (encadré récupéré intégralement) |
| `non_recupere` | **échec technique** (cookie-wall, HTTP 3xx/4xx, corps inextricable). On ne sait pas ce que contient l'article. | « non récupéré » + résumé préfixé « Article non récupéré — » | les **4 dépêches Mediahuis Luxembourg** |

Le champ `sous_abonnement` du JSON de classification (mis à `true` par le modèle
dès que le texte est incomplet) est conservé mais **n'est plus l'info
d'affichage** : c'est `acces` qui fait foi.

---

## 7. Texte de synthèse produit chaque jour

> **2026-09-01** · `evenement_unique` · 1 article
> Selon Tobacco Journal International (reprenant Euractiv), l'incertitude
> politique née des élections législatives suédoises pourrait retarder l'accord
> du Conseil sur la révision de la directive fiscale tabac (TED), la Suède
> risquant de s'abstenir lors d'un vote envisagé à l'ECOFIN du 9 octobre.

> **2026-09-02** · `plusieurs_sujets` · 2 articles
> La médiatrice européenne a ouvert (le 18 août) une enquête sur la gestion par
> la DG TRADE de la Commission de ses contacts avec l'industrie du tabac, sur
> plainte de Contre-Feu (Vaping Post). Par ailleurs, lors de la visite d'António
> Costa à Luxembourg, le Premier ministre Luc Frieden a réaffirmé l'opposition
> luxembourgeoise aux taux minimaux d'accise tabac envisagés par Bruxelles
> (Tageblatt).

> **2026-09-03** · `plusieurs_sujets` · 2 articles
> The Examination détaille le blocage par la Suède de la taxe minimale sur les
> sachets de nicotine, qui enlise la révision de la directive fiscale tabac au
> Conseil. En parallèle, Génération Sans Tabac décrypte comment le média
> bruxellois EU Reporter relaie les arguments pro-industrie en s'appuyant sur une
> décision de la FDA américaine sur les sachets Zyn.

> **2026-09-04** · `evenement_unique` · 1 article
> Follow the Money publie une enquête (accès abonné, teaser public) selon laquelle
> l'industrie du tabac a investi des millions dans la recherche et le lobbying
> pour imposer à Bruxelles le récit d'une moindre nocivité des nouveaux produits
> nicotinés — récit qu'elle relie au rejet par le Parlement européen, en juin, de
> la révision de la directive fiscale sur le tabac.

**Sur ces 4 jours, la synthèse tient debout** : elle privilégie les faits datés
(enquête de la médiatrice, blocage au Conseil, vote du PE de juin), attribue à
chaque source, et ne force pas de lien narratif entre la piste « médiatrice » et
la piste « Luxembourg » le 02/09 (`plusieurs_sujets`).

---

## 8. Points à décider — arbitrages retenus (2026-09-04)

1. **Coût API / volume de bruit Tobacco Reporter + TJI.**
   → **Retenu : laisser tourner tel quel** (coût Sonnet minime), mesurer une
   semaine, durcir le pré-filtre pour ces deux flux seulement si besoin. Pas de
   changement pour l'instant.

2. **Cas limite « multi-sujets » (#3 Tageblatt).**
   → **Retenu : on ne touche pas à la règle.** Un seul exemple ne suffit pas à
   l'ajuster. À revoir si le cas se répète (round 2 §5.2 du cahier).

3. **Articles non récupérables vs sous abonnement.**
   → **Fait.** Étiquette `acces` à trois états (`libre` / `sous_abonnement` /
   `non_recupere`), voir §6-bis. Les articles `non_recupere` ne sont jamais
   publiés automatiquement.

4. **Flux directs GST / STOP / TabakNee en panne (channel vide).**
   → **Retenu : on s'appuie sur Google News** pour ces trois sources (leurs
   articles y sont bien indexés). Re-test périodique, pas d'investigation lourde.

5. **Dédoublonnage revue ↔ publiés.**
   → **Retenu : ne pas sur-ingénierer.** Non implémenté. La limite est
   documentée (§6). À faire seulement si ça gêne en pratique.

6. **Round 2 du cahier des charges (§5, 3 cas limites).**
   → **Retenu : surveiller les premières semaines**, non bloquant pour démarrer.

### Reste à faire avant de merger et de brancher le rendu HTML

- **Test avec la vraie clé API** (§10) : une nuit récente, appel API réel (non
  simulé), comparé à la simulation de cette même nuit.

---

## 9. Ce qui est prêt (code, non branché)

- `scripts/press_watch/` + `scripts/fetch_press_watch.py` — voir `NOTES.md`.
- `.github/workflows/press_watch.yml` — `workflow_dispatch` + `--dry-run`
  uniquement. Passage en production = 4 lignes à décommenter + le secret
  `ANTHROPIC_API_KEY`.
- `data/press_watch.json` — squelette vide, référencé par aucune page.
- **Aucune modification de `index.html` / `common.js` / `styles.css`.** Le rendu
  HTML de la section « Veille – Presse » n'est pas encore écrit : il viendra dans
  une PR séparée, après ce feu vert.

---

## 10. Test avec la vraie clé API (à faire avant de merger)

**Objectif** (formulé par le demandeur) : vérifier que l'appel API réel produit
le **même type de sortie** que la simulation — pas re-tester le raisonnement.

**Marche à suivre une fois `ANTHROPIC_API_KEY` ajouté aux secrets du dépôt :**

1. Lancer le workflow `Veille Presse (dry-run…)` en `workflow_dispatch` avec
   `since = 2026-09-03`, `until = 2026-09-03` (journée avec 2 publiés + du bruit
   à exclure : The Examination + Génération Sans Tabac, ~7 candidats).
   Le workflow tourne **sans `--classifications`** → appels API réels ; **avec
   `--dry-run`** → n'écrit ni le site ni `data/press_watch.json`, publie juste
   le rapport en artefact.
2. Récupérer l'artefact `press-watch-report` et me le transmettre.
3. Je compare, pour cette même journée, la sortie réelle à la simulation de ce
   rapport (§4 et §7), sur :
   - mêmes articles classés `pertinent` / exclus / en revue ?
   - `source_type`, `sous_abonnement`, `acces`, `confiance` cohérents ?
   - JSON strict bien parsé, aucun `schema_warning` inattendu ?
   - résumés en français, préfixes « Accès abonné — » / « Article non récupéré — »
     corrects ?
   - le texte de synthèse du jour est du même ordre (fait daté privilégié,
     attribution aux sources) ?

> Le workflow accepte déjà `since`/`until` comme entrées (`workflow_dispatch`).
> Rien d'autre à préparer côté code.
