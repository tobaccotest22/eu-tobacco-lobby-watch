"""
Définition des sources du flux de découverte (section 3 du cahier des charges).

Deux familles :

1. GOOGLE_NEWS_QUERIES : requêtes Google News RSS, une série par langue
   (fr / en / de / it). C'est le filet large. Google News tourne sur
   l'infrastructure de Google et renvoie titre + date + média + court extrait
   même pour les sites qui bloquent le fetch direct (Politico, Euractiv — cf.
   section 9). Les liens renvoyés sont des redirections news.google.com à
   résoudre (resolve.py).

2. DIRECT_FEEDS : flux RSS/Atom directs des sources prioritaires et des blogs
   spécialisés déjà identifiés. Vérifiés un par un (voir colonne « vérifié »).
   Ceux marqués actif=False sont conservés pour mémoire mais pas interrogés.

Le champ `access` ("libre" | "souvent_payant" | "payant") n'est qu'indicatif
pour le rapport ; la détection réelle du paywall se fait à l'extraction.
"""

# --- Mots-clés de pré-filtrage (léger) -------------------------------------
#
# Sert uniquement à écarter le bruit évident avant l'appel LLM (un titre qui ne
# contient AUCUN de ces termes, dans aucune langue, a très peu de chances d'être
# dans le périmètre). Le vrai tri est fait par le prompt de classification.
# On reste volontairement permissif.

TOPIC_KEYWORDS = [
    # tabac / nicotine (multi-langue)
    "tabac", "tabak", "tabacco", "tobacco", "nicotine", "nikotin", "nicotina",
    "vape", "vaping", "vapote", "e-cigarette", "e-zigarette", "cigarette électronique",
    "sigaretta elettronica", "snus", "sachet de nicotine", "nicotine pouch",
    "nikotinbeutel", "puff", "heated tobacco", "tabac chauffé",
    # cadre réglementaire UE
    "tpd", "ttd", "ted", "tad", "tpd3", "directive", "richtlinie", "direttiva",
    "call for evidence", "consultation", "konsultation", "consultazione",
    "trilogue", "trilog", "ecofin", "econ",
    # institutions / lobbying UE
    "bruxelles", "brussels", "brüssel", "commission européenne", "european commission",
    "europäische kommission", "commissione europea", "parlement européen",
    "european parliament", "europäisches parlament", "parlamento europeo",
    "eurodéput", "mep ", "meps", "conseil de l'ue", "council of the eu",
    "lobby", "lobbying", "lobbyist", "article 5.3", "cclat", "fctc",
    "philip morris", "british american tobacco", " bat ", "japan tobacco", "jti",
    "imperial brands", "transparency register", "registre de transparence",
]


def _gnews(query: str, lang: str, gl: str) -> dict:
    ceid = f"{gl}:{lang}"
    from urllib.parse import quote
    url = (
        "https://news.google.com/rss/search?q="
        + quote(query)
        + f"&hl={lang}&gl={gl}&ceid={quote(ceid)}"
    )
    return {"kind": "google_news", "lang": lang, "query": query, "url": url}


# NB : les requêtes Google News trop composées (plusieurs groupes OR + opérateur
# `when:`) renvoient souvent 0 résultat — testé le 2026-09-04. On garde donc des
# requêtes SIMPLES (2-3 termes), quitte à laisser passer du bruit : le pré-filtre
# thématique puis le prompt de classification font le tri. La fenêtre de dates
# est réappliquée dans feeds.py à partir de la date de publication (Google News
# renvoie ~1 mois d'historique).

GOOGLE_NEWS_QUERIES = [
    # -- français --------------------------------------------------------
    _gnews("directive européenne tabac", "fr", "FR"),
    _gnews("tabac lobbying Bruxelles", "fr", "FR"),
    _gnews("taxe tabac Union européenne", "fr", "FR"),
    _gnews("nicotine directive Bruxelles", "fr", "FR"),
    _gnews("TPD révision tabac", "fr", "FR"),
    # -- anglais --------------------------------------------------------
    _gnews("EU tobacco directive revision", "en", "US"),
    _gnews("tobacco lobbying Brussels", "en", "US"),
    _gnews("Tobacco Products Directive", "en", "US"),
    _gnews("tobacco tax directive EU Council", "en", "US"),
    _gnews("nicotine pouches EU tax", "en", "US"),
    # -- allemand -----------------------------------------------------
    _gnews("Tabak Richtlinie Brüssel", "de", "DE"),
    _gnews("Tabaksteuer EU", "de", "DE"),
    _gnews("Tabaklobby Brüssel", "de", "DE"),
    _gnews("Tabakproduktrichtlinie Revision", "de", "DE"),
    # -- italien ----------------------------------------------------
    _gnews("direttiva tabacco UE", "it", "IT"),
    _gnews("tabacco Bruxelles lobbying", "it", "IT"),
    _gnews("tassa tabacco Unione europea", "it", "IT"),
    _gnews("revisione direttiva tabacco", "it", "IT"),
]


# Flux directs. `verified` = testé pendant le câblage (2026-09-04).
DIRECT_FEEDS = [
    {"name": "Corporate Europe Observatory", "lang": "en", "access": "libre",
     "url": "https://corporateeurope.org/rss.xml", "active": True, "verified": "2026-09-04 (39 entrées)"},
    {"name": "Vaping Post (FR)", "lang": "fr", "access": "libre",
     "url": "https://fr.vapingpost.com/feed/", "active": True, "verified": "2026-09-04 (20 entrées)"},
    {"name": "pro-rauchfrei", "lang": "de", "access": "libre",
     "url": "https://pro-rauchfrei.de/feed/", "active": True, "verified": "2026-09-04 (10 entrées)"},
    {"name": "Tobacco Reporter", "lang": "en", "access": "libre",
     "url": "https://tobaccoreporter.com/feed/", "active": True, "verified": "2026-09-04 (10 entrées)"},
    # Flux qui renvoient un <channel> vide à notre UA (bug de cache plugin ou
    #   protection anti-bot côté hébergeur — vérifié 2026-09-04, tous UA testés).
    #   Ces éditeurs restent couverts par Google News (leurs articles y sont
    #   bien indexés). À re-tester périodiquement.
    {"name": "Génération Sans Tabac", "lang": "fr", "access": "libre",
     "url": "https://www.generationsanstabac.org/fr/feed/", "active": False,
     "verified": "2026-09-04 : <channel> vide, couvert via Google News"},
    {"name": "STOP (exposetobacco)", "lang": "en", "access": "libre",
     "url": "https://exposetobacco.org/feed/", "active": False,
     "verified": "2026-09-04 : <channel> vide, couvert via Google News"},
    {"name": "TabakNee", "lang": "en", "access": "libre",
     "url": "https://www.tabaknee.nl/?format=feed&type=rss", "active": False,
     "verified": "2026-09-04 : <channel> vide, couvert via Google News"},
    {"name": "TobaccoTactics", "lang": "en", "access": "libre",
     "url": "https://tobaccotactics.org/feed/", "active": True, "verified": "2026-09-04 (5 entrées)"},
    {"name": "Tobacco Journal International", "lang": "en", "access": "libre",
     "url": "https://www.tobaccojournal.com/feed/", "active": True, "verified": "2026-09-04 (20 entrées)"},
    # The Examination : pas de flux RSS public trouvé au 2026-09-04 — couvert
    #   via Google News (source prioritaire, articles bien indexés).
    # Contre-Feu : pas de flux RSS confirmé — passe par Google News.
]


def topic_prefilter(text: str) -> bool:
    """True si le texte (titre + extrait) mérite un appel de classification."""
    if not text:
        return False
    low = text.lower()
    return any(kw in low for kw in TOPIC_KEYWORDS)
