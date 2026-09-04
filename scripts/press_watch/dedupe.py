"""
Dédoublonnage par `entites_citees` (section 2 du cahier des charges).

Règle retenue (confirmée par l'éval round 1 sur le cas réel 11a/11b) :
deux articles sont des doublons si
  - dates de publication à ±1 jour   ET
  - >= 3 entités FORTES communes après normalisation
    (organisations nommées ou chiffres-clés ; on exclut les termes génériques
     "commission européenne", "tpd", etc. pris isolément).

Normalisation avant comparaison — indispensable, sinon le recoupement 11a/11b
passe de ~8 entités communes à ~4 :
  - minuscules + suppression des accents
  - suppression des parenthèses et précisions : "Commission européenne (DG Trade)"
    -> "commission europeenne"
  - nombres : "49 organisations" / "49 organizations" / "49" -> jeton "num:49"
  - montants multilingues : "14 millions d'euros" / "14 million euros" / "€14m"
    -> jeton "eur:14" (ou "eur:14000000" si l'échelle est explicite)

En cas de doublon : on garde l'article prioritaire (accès libre > payant, puis
priorité de source pour l'angle UE, puis résumé le plus complet). Les autres
sont écartés et journalisés dans `duplicates`.
"""

import re
import unicodedata
from datetime import date, datetime

# Termes trop génériques pour compter comme « entité forte » isolément.
GENERIC = {
    "commission europeenne", "commission", "parlement europeen", "parlement",
    "conseil de l'ue", "conseil", "conseil de l'union europeenne",
    "union europeenne", "ue", "eu", "bruxelles", "brussels",
    "tpd", "ttd", "ted", "tad", "tpd3", "directive", "directive tabac",
    "directive sur le tabac", "tobacco products directive",
    "tobacco taxation directive", "tobacco excise directive",
    "oms", "who", "cclat", "fctc", "article 5.3",
    "industrie du tabac", "tobacco industry", "big tobacco",
    "consultation publique", "call for evidence", "commission",
}

_PARENS_RE = re.compile(r"\([^)]*\)")
_NUM_RE = re.compile(r"\d[\d\s.,]*")
_SCALE = {
    "millions": 1_000_000, "million": 1_000_000, "millionen": 1_000_000,
    "milioni": 1_000_000, "milione": 1_000_000, "m": 1_000_000, "mn": 1_000_000,
    "milliards": 1_000_000_000, "milliard": 1_000_000_000, "billion": 1_000_000_000,
    "miliardi": 1_000_000_000, "mrd": 1_000_000_000,
}
_MONEY_HINT = re.compile(r"(€|eur|euro|euros)", re.I)


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def normalize_entity(raw: str) -> str:
    s = _strip_accents(str(raw).lower())
    s = _PARENS_RE.sub(" ", s)
    s = s.replace("’", "'").replace(" ", " ")

    money = bool(_MONEY_HINT.search(s))
    num_match = _NUM_RE.search(s)
    if num_match:
        digits = re.sub(r"[^\d]", "", num_match.group(0).replace(",", "").replace(".", ""))
        if digits:
            value = int(digits)
            scale = 1
            tail = s[num_match.end():].strip().split()
            if tail and tail[0] in _SCALE:
                scale = _SCALE[tail[0]]
            if money or "€" in raw or "eur" in s:
                return f"eur:{value * scale}"
            if scale > 1:
                return f"num:{value * scale}"
            return f"num:{value}"

    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # petites variantes de sociétés
    s = s.replace("philip morris international", "philip morris")
    s = s.replace("pmi", "philip morris") if s == "pmi" else s
    s = s.replace("british american tobacco", "bat") if "british american tobacco" in s else s
    s = s.replace("japan tobacco international", "jti") if "japan tobacco international" in s else s
    return s


def strong_entities(entites: list[str]) -> set[str]:
    out = set()
    for e in entites or []:
        n = normalize_entity(e)
        if not n or n in GENERIC:
            continue
        if len(n) < 2:
            continue
        out.add(n)
    return out


def _to_date(v) -> date | None:
    if v is None or isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(v))
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _days_apart(a, b) -> int:
    a, b = _to_date(a), _to_date(b)
    if a is None or b is None:
        return 999
    return abs((a - b).days)


# Priorité de source pour l'angle UE (indice bas = gardé en priorité).
SOURCE_PRIORITY = [
    "the examination", "politico", "euractiv", "corporate europe observatory",
    "follow the money", "reuters", "the guardian", "euronews",
    "génération sans tabac", "generation sans tabac", "contre-feu", "stop",
    "tobaccotactics", "tabaknee", "il sole 24 ore", "vaping post",
    "tobacco journal", "tobacco reporter",
]


def _source_rank(name: str) -> int:
    low = (name or "").lower()
    for i, s in enumerate(SOURCE_PRIORITY):
        if s in low:
            return i
    return len(SOURCE_PRIORITY)


def _keeper(a: dict, b: dict) -> tuple[dict, dict]:
    """Renvoie (gardé, écarté)."""
    # 1. accès libre > payant
    for x, y in ((a, b), (b, a)):
        if not x.get("sous_abonnement") and y.get("sous_abonnement"):
            return x, y
    # 2. priorité de source
    ra = _source_rank(a.get("source_name") or a.get("site_name"))
    rb = _source_rank(b.get("source_name") or b.get("site_name"))
    if ra != rb:
        return (a, b) if ra < rb else (b, a)
    # 3. résumé le plus complet
    if len(a.get("resume") or "") >= len(b.get("resume") or ""):
        return a, b
    return b, a


def find_duplicates(articles: list[dict], min_shared: int = 3) -> list[dict]:
    """
    `articles` : dicts avec au moins id, title, published (date|None),
    entites_citees, sous_abonnement, source_name, resume.
    Renvoie une liste de groupes :
      {"kept": <id>, "dropped": [<id>...], "shared_entities": [...], "pairs": [...]}
    Ne modifie pas `articles`.
    """
    n = len(articles)
    ent = [strong_entities(x.get("entites_citees")) for x in articles]
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    pair_info: dict[tuple[int, int], list[str]] = {}
    for i in range(n):
        for j in range(i + 1, n):
            if _days_apart(articles[i].get("published"), articles[j].get("published")) > 1:
                continue
            shared = ent[i] & ent[j]
            if len(shared) >= min_shared:
                union(i, j)
                pair_info[(i, j)] = sorted(shared)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    result = []
    for members in groups.values():
        if len(members) < 2:
            continue
        kept_idx = members[0]
        for idx in members[1:]:
            kept_idx = articles.index(_keeper(articles[kept_idx], articles[idx])[0])
        dropped = [m for m in members if m != kept_idx]
        shared_all = set.intersection(*(ent[m] for m in members)) if members else set()
        result.append({
            "kept": articles[kept_idx]["id"],
            "kept_title": articles[kept_idx].get("title"),
            "kept_source": articles[kept_idx].get("source_name") or articles[kept_idx].get("site_name"),
            "dropped": [articles[m]["id"] for m in dropped],
            "dropped_detail": [
                {"id": articles[m]["id"], "title": articles[m].get("title"),
                 "source": articles[m].get("source_name") or articles[m].get("site_name")}
                for m in dropped
            ],
            "shared_entities": sorted(shared_all),
            "pairs": [
                {"a": articles[i].get("title"), "b": articles[j].get("title"),
                 "shared": sh}
                for (i, j), sh in pair_info.items()
                if i in members and j in members
            ],
        })
    return result
