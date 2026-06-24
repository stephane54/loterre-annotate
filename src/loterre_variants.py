"""Détection de variantes terminologiques (Phase 4, v2.0).

Catégories linguistiques inspirées de TermSuite (CNRS/TTC, dépôt
termsuite-resources, Apache 2.0), généralisées en mécanismes structurels
plutôt que reproduites comme ~450 règles par langue très spécifiques (voir
planification/planif_extraction_terminologique.md §Phase 4 pour le détail
du choix) :

  - morph_inflection : même séquence de lemmes, surface différente (gratuit —
    CandidateTerm.lemma le donne déjà, ex. "résultat"/"résultats")
  - graphical        : même séquence de lemmes après normalisation
    accents/casse/tirets/espaces (ex. "macro-économie"/"macroéconomie")
  - morph_prefix     : lemmes identiques sauf un token lié par un préfixe
    connu (ex. "machine synchrone"/"machine asynchrone" — TermSuite
    "AN-prefAN"/"NA-NprefA")
  - syn_expansion    : le squelette de contenu (NOUN/PROPN/ADJ, mots-outils
    retirés) d'un candidat est une sous-séquence contiguë de l'autre — couvre
    aussi de façon générique la réduction N N <-> N de/of N (insertion d'une
    préposition+déterminant en est un cas particulier), généralisation des
    familles TermSuite S-Ed/S-Eg/S-I/S-PI/S-R2
  - syn_permutation  : même multiset de lemmes de contenu, ordre différent
    (généralisation de la famille TermSuite S-P)
  - morph_derivation : lemmes identiques sauf un token adjectif/nom lié par
    les tables de dérivation TermSuite vendorisées
    (resources/termsuite_morphology/) — couvre l'alternance N+Adj <->
    N+Prep+N (ex. "énergie éolienne"/"énergie du vent", TermSuite
    "S-PID-NA-P"/"S-R2D-NN", gated par deriv() chez TermSuite)

Synonymie explicitement hors scope : relation différente de la variation de
forme (TermSuite la traite à part, "SemanticGatherer") — la confondre
romprait la définition de "variante".

Chaque candidat n'est regroupé que par UNE seule passe, dans l'ordre listé
ci-dessus (du plus fiable/structurel au plus permissif) — pas de cascade.

Fichier séparé du reste de l'extraction (règle Phase 0.5) : ne dépend que de
loterre_extraction_base.CandidateTerm.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from loterre_extraction_base import CandidateTerm

_RESOURCE_DIR = Path(__file__).resolve().parent.parent / "resources" / "termsuite_morphology"

_CONTENT_POS = frozenset({"NOUN", "PROPN", "ADJ", "VERB"})
# VERB inclus : les chunks candidats viennent déjà du filtre is_valid_candidate()
# (au moins un NOUN/PROPN/ADJ), donc un VERB à l'intérieur est presque toujours
# un modificateur en -ing mal étiqueté (gérondif/participe utilisé comme nom
# composé, ex. "spacing effect"/"sandwich effect" où spaCy tague "spacing"/
# "sandwich" en VERB) plutôt qu'un vrai verbe — un faux regroupement syn_expansion
# constaté en validation (squelette réduit à "effect" pour les deux, les faisant
# coïncider à tort) si on le traite comme mot-outil.

# Préfixes privatifs/négatifs courants — repris de l'esprit des règles
# TermSuite "AN-prefAN"/"NA-NprefA" (liste fermée volontairement courte,
# pas une ressource lourde).
_PREFIXES = {
    "fr": ("anti", "hyper", "non", "dés", "dé", "in", "im", "ir", "a", "pro"),
    "en": ("anti", "hyper", "non", "dis", "in", "im", "ir", "un", "pro"),
}


def content_skeleton(pattern: list[dict[str, str]]) -> list[str]:
    """Lemmes des tokens de contenu (NOUN/PROPN/ADJ), mots-outils retirés —
    base de comparaison pour l'insertion/expansion et la permutation."""
    return [t["lemma"] for t in pattern if t["pos"] in _CONTENT_POS]


def content_skeleton_with_pos(pattern: list[dict[str, str]]) -> list[tuple[str, str]]:
    """Comme content_skeleton(), mais garde le POS de chaque token de contenu
    — nécessaire pour morph_derivation (derive_match a besoin de la catégorie
    grammaticale, pas seulement du lemme)."""
    return [(t["lemma"], t["pos"]) for t in pattern if t["pos"] in _CONTENT_POS]


def normalize_graphical_key(lemma_seq: str) -> str:
    """Clé insensible aux tirets/espaces/casse/accents — regroupe les
    variantes purement typographiques d'un composé.

    Exception : une séquence entièrement en capitales (probable acronyme,
    ex. "GRACE" un nom de mission) garde sa casse — la passer en minuscules
    la confondrait avec un mot ordinaire homographe ("grâce") qui n'a aucun
    rapport, un faux regroupement constaté en validation X64."""
    if lemma_seq.isupper() and len(lemma_seq) > 1:
        return lemma_seq
    decomposed = unicodedata.normalize("NFKD", lemma_seq.lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[-\s']+", "", stripped)


def _pos_category(pos: str) -> str:
    return "A" if pos == "ADJ" else "N" if pos in ("NOUN", "PROPN") else pos


@lru_cache(maxsize=4)
def load_derivation_rules(lang: str):
    """Charge les tables de dérivation TermSuite vendorisées
    (resources/termsuite_morphology/{lang}/) pour *lang*. Retourne
    (suffix_rules, suppletive_groups) :
      - suffix_rules : liste de (cat_from, cat_to, suf_from, suf_to), triée
        par longueur de suf_from décroissante (suffixes les plus spécifiques
        testés d'abord)
      - suppletive_groups : dict mot_normalisé -> id de classe d'équivalence

    Fichiers manquants ou vides (ex. en/suppletives-bank.txt) -> tables
    vides, pas une erreur (toutes les langues n'ont pas de paires curées).
    """
    lang_dir = _RESOURCE_DIR / lang
    suffix_path = lang_dir / "suffix-derivation-bank.txt"
    suppl_path = lang_dir / "suppletives-bank.txt"

    suffix_rules: list[tuple[str, str, str, str]] = []
    if suffix_path.exists():
        for line in suffix_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            cats = parts[0].split()
            if len(cats) != 2:
                continue
            cat_from, cat_to = cats
            suf_from = "" if parts[1] == "-" else parts[1].lstrip("-")
            suf_to = "" if parts[2] == "-" else parts[2].lstrip("-")
            suffix_rules.append((cat_from, cat_to, suf_from, suf_to))
    suffix_rules.sort(key=lambda r: -len(r[2]))

    suppletive_groups: dict[str, int] = {}
    if suppl_path.exists():
        gid = 0
        for line in suppl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tokens = [tok.split(":")[0].lower() for tok in line.split("\t") if tok.strip()]
            tokens = [t for t in tokens if t]
            if len(tokens) < 2:
                continue
            for tok in tokens:
                suppletive_groups[tok] = gid
            gid += 1

    return suffix_rules, suppletive_groups


def derive_match(lang: str, word_a: str, pos_a: str, word_b: str, pos_b: str) -> bool:
    """True si *word_a* (POS *pos_a*) et *word_b* (POS *pos_b*) sont liés par
    une règle de dérivation TermSuite par suffixe — adjectif <-> nom de la
    même famille, ex. "pulmonaire" (ADJ) / "poumon" (NOUN).

    Restreint aux paires inter-catégories (A<->N) : les règles N<->N de la
    table TermSuite (nom déverbal, ex. EN "N N -ing -" -> "modeling"/"model")
    relient des concepts trop souvent distincts pour ce projet (le nom
    d'action et l'objet ne sont pas une "même terminologie", contrairement à
    l'alternance adjectif/nom qui a motivé cette passe) — faux positifs
    constatés en validation X64/P66 (ex. EN "processing"/"process",
    "usage"/"use") et retirés en excluant cat_from==cat_to.

    Les classes supplétives (suppletives-bank.txt) ne sont PAS utilisées ici,
    volontairement : ce fichier sert chez TermSuite à décomposer des FORMES
    COMBINANTES à l'intérieur d'un composé (ex. "psycho-" ~ "esprit" pour
    analyser "psychogenèse"), pas à déclarer deux mots entiers synonymes —
    les utiliser en comparaison directe a produit de faux rapprochements
    grossiers en validation (ex. "psychologie"/"esprit", "calcul"/"mesure",
    "mère"/"partie") et a été retiré.
    """
    if word_a == word_b:
        return False
    suffix_rules, _ = load_derivation_rules(lang)
    cat_a, cat_b = _pos_category(pos_a), _pos_category(pos_b)

    for cat_from, cat_to, suf_from, suf_to in suffix_rules:
        if cat_from == cat_to:
            continue
        for w_from, c_from, w_to, c_to in (
            (word_a, cat_a, word_b, cat_b),
            (word_b, cat_b, word_a, cat_a),
        ):
            if c_from != cat_from or c_to != cat_to:
                continue
            if suf_from and not w_from.endswith(suf_from):
                continue
            stem = w_from[: len(w_from) - len(suf_from)] if suf_from else w_from
            if stem + suf_to == w_to:
                return True

    return False


_MIN_PREFIX_STEM_LEN = 4  # évite les faux positifs sur radical court (ex.
# "age"/"image" : "im"+"age" coïncide avec un préfixe connu sans aucun lien
# morphologique réel — un radical de 3 caractères ou moins est trop générique
# pour fiabiliser le rapprochement, constaté en validation X64).


def _is_prefix_pair(lang: str, tok_a: tuple[str, str], tok_b: tuple[str, str]) -> bool:
    word_a, word_b = tok_a[0], tok_b[0]
    if word_a == word_b:
        return False
    shorter, longer = (word_a, word_b) if len(word_a) <= len(word_b) else (word_b, word_a)
    if len(shorter) < _MIN_PREFIX_STEM_LEN or not longer.endswith(shorter):
        return False
    prefix_part = longer[: len(longer) - len(shorter)]
    return prefix_part in _PREFIXES.get(lang, ())


def _is_contiguous_subsequence(short: tuple, long_: tuple) -> bool:
    ls, ll = len(short), len(long_)
    if ls == 0 or ls >= ll:
        return False
    for start in range(ll - ls + 1):
        if long_[start : start + ls] == short:
            return True
    return False


def _canonical_key(c: CandidateTerm) -> tuple:
    # Canonique = fréquence la plus haute ; égalité -> le plus de tokens
    # (même convention que le tie-break de loterre_embed.score_candidates_embed) ;
    # égalité -> ordre alphabétique pour la déterminisme.
    return (-c.frequency, -len(c.term.split()), c.term)


def _assign_cluster(cluster: list[CandidateTerm], variant_type: str) -> None:
    if len(cluster) < 2:
        return
    canonical = min(cluster, key=_canonical_key)
    for c in cluster:
        if c is canonical or c.canonical_form is not None:
            continue
        c.canonical_form = canonical.term
        c.variant_type = variant_type


def _ungrouped(candidates: list[CandidateTerm]) -> list[CandidateTerm]:
    return [c for c in candidates if c.canonical_form is None]


def _greedy_assign_from_adjacency(
    pool: list[CandidateTerm], adjacency: dict[int, set[int]], variant_type: str
) -> None:
    """Affecte canonical_form/variant_type à partir d'une relation directe
    (adjacency[i] = indices dans *pool* directement reliés à i) SANS
    transitivité : pas de composantes connexes (union-find).

    Sous-séquence/préfixe/dérivation ne sont PAS des relations d'équivalence
    (ni transitives, ni symétriques en un sens utile) — fusionner par
    composantes connexes ferait dériver un cluster entier à travers des
    intermédiaires sans relation directe entre les extrêmes (ex. "semantic
    memory" et "controlled memory assessment" partagent juste le mot
    "memory" via une chaîne, sans squelette de contenu directement
    sous-séquence l'un de l'autre — un faux regroupement constaté et corrigé
    pendant la validation).

    À la place : on traite les candidats du plus canonique (fréquence la
    plus haute) au moins canonique ; chaque candidat encore canonique à son
    tour "réclame" ses voisins directs non encore réclamés. Un variant
    pointe donc toujours vers un candidat réellement et directement relié,
    jamais vers un intermédiaire qui devient lui-même variant d'un autre.
    """
    order = sorted(range(len(pool)), key=lambda i: _canonical_key(pool[i]))
    claimed: set[int] = set()
    for i in order:
        if i in claimed:
            continue
        for j in adjacency.get(i, ()):
            if j == i or j in claimed or pool[j].canonical_form is not None:
                continue
            claimed.add(j)
            pool[j].canonical_form = pool[i].term
            pool[j].variant_type = variant_type


def _group_single_token_diff(candidates, lang: str, variant_type: str, predicate) -> None:
    """Bucket par longueur de séquence puis comparaison par paire (cher
    uniquement à l'intérieur d'un bucket, qui reste petit en pratique car
    --min-tokens/--max-tokens bornent la longueur des candidats). Affectation
    directe (_greedy_assign_from_adjacency), pas de composantes connexes."""
    by_length: dict[int, list[CandidateTerm]] = {}
    for c in _ungrouped(candidates):
        by_length.setdefault(len(c.pattern), []).append(c)

    for length, group in by_length.items():
        if length < 1:
            continue
        n = len(group)
        adjacency: dict[int, set[int]] = {}
        for i in range(n):
            for j in range(i + 1, n):
                ci, cj = group[i], group[j]
                diff_positions = [
                    k for k in range(length) if ci.pattern[k]["lemma"] != cj.pattern[k]["lemma"]
                ]
                if len(diff_positions) != 1:
                    continue
                k = diff_positions[0]
                tok_i = (ci.pattern[k]["lemma"], ci.pattern[k]["pos"])
                tok_j = (cj.pattern[k]["lemma"], cj.pattern[k]["pos"])
                if predicate(lang, tok_i, tok_j):
                    adjacency.setdefault(i, set()).add(j)
                    adjacency.setdefault(j, set()).add(i)

        _greedy_assign_from_adjacency(group, adjacency, variant_type)


def _group_function_word_variants(candidates: list[CandidateTerm]) -> None:
    """syn_expansion (cas particulier) : squelette de contenu identique mais
    séquence de lemmes complète différente — un mot-outil a été inséré/retiré
    SANS changer le contenu (ex. "panne réseau"/"panne de réseau"). Ce cas ne
    change pas la longueur du squelette de contenu, donc _group_expansion()
    (sous-séquence stricte, squelettes de longueurs différentes) ne le
    couvrirait pas — bucket exact séparé, avant la comparaison par sous-séquence."""
    buckets: dict[tuple, list[CandidateTerm]] = {}
    for c in _ungrouped(candidates):
        skeleton = tuple(content_skeleton(c.pattern))
        if not skeleton:
            continue
        buckets.setdefault(skeleton, []).append(c)
    for cluster in buckets.values():
        distinct_lemmas = {c.lemma for c in cluster}
        if len(distinct_lemmas) > 1:
            _assign_cluster(cluster, "syn_expansion")


def _group_expansion(candidates: list[CandidateTerm]) -> None:
    """syn_expansion : index inversé sur les lemmes de contenu pour limiter
    la comparaison par paire aux candidats partageant au moins un lemme
    (évite une comparaison O(n²) sur l'ensemble du corpus). Affectation
    directe (_greedy_assign_from_adjacency) : la sous-séquence n'est pas une
    relation d'équivalence, donc pas de composantes connexes — voir sa
    docstring pour le faux regroupement que ça évite."""
    _group_function_word_variants(candidates)

    pool = _ungrouped(candidates)
    skeletons = {id(c): tuple(content_skeleton(c.pattern)) for c in pool}
    pool = [c for c in pool if skeletons[id(c)]]
    if len(pool) < 2:
        return

    index_of = {id(c): i for i, c in enumerate(pool)}
    lemma_index: dict[str, list[int]] = {}
    for c in pool:
        for lemma in set(skeletons[id(c)]):
            lemma_index.setdefault(lemma, []).append(index_of[id(c)])

    adjacency: dict[int, set[int]] = {}
    checked: set[tuple[int, int]] = set()
    for c in pool:
        i = index_of[id(c)]
        skel_c = skeletons[id(c)]
        neighbours: set[int] = set()
        for lemma in skel_c:
            neighbours.update(lemma_index.get(lemma, ()))
        neighbours.discard(i)
        for j in neighbours:
            pair = (min(i, j), max(i, j))
            if pair in checked:
                continue
            checked.add(pair)
            skel_other = skeletons[id(pool[j])]
            if skel_c == skel_other:
                continue  # même multiset+ordre -> géré par une autre passe
            shorter, longer = (skel_c, skel_other) if len(skel_c) < len(skel_other) else (skel_other, skel_c)
            if _is_contiguous_subsequence(shorter, longer):
                adjacency.setdefault(i, set()).add(j)
                adjacency.setdefault(j, set()).add(i)

    _greedy_assign_from_adjacency(pool, adjacency, "syn_expansion")


def _group_derivation(candidates: list[CandidateTerm], lang: str) -> None:
    """morph_derivation : bucket par longueur de squelette de CONTENU (pas la
    séquence complète — une préposition insérée ne change pas cette longueur,
    voir docstring de l'appel dans group_variants()), puis paire différant
    d'une seule position de contenu liée par les tables de dérivation."""
    by_length: dict[int, list[CandidateTerm]] = {}
    for c in _ungrouped(candidates):
        skel = content_skeleton_with_pos(c.pattern)
        if skel:
            by_length.setdefault(len(skel), []).append(c)

    for length, group in by_length.items():
        n = len(group)
        skeletons = [content_skeleton_with_pos(c.pattern) for c in group]
        adjacency: dict[int, set[int]] = {}
        for i in range(n):
            for j in range(i + 1, n):
                si, sj = skeletons[i], skeletons[j]
                diff_positions = [k for k in range(length) if si[k][0] != sj[k][0]]
                if len(diff_positions) != 1:
                    continue
                k = diff_positions[0]
                if derive_match(lang, si[k][0], si[k][1], sj[k][0], sj[k][1]):
                    adjacency.setdefault(i, set()).add(j)
                    adjacency.setdefault(j, set()).add(i)

        _greedy_assign_from_adjacency(group, adjacency, "morph_derivation")


def group_variants(candidates: list[CandidateTerm], lang: str) -> None:
    """Regroupe *candidates* par variantes, en mutant en place
    canonical_form/variant_type — ne change ni l'ordre ni la longueur de la
    liste (additif, voir CandidateTerm)."""
    if len(candidates) < 2:
        return

    # Pass 1 : morph_inflection -- même séquence de lemmes
    buckets: dict[str, list[CandidateTerm]] = {}
    for c in candidates:
        buckets.setdefault(c.lemma, []).append(c)
    for cluster in buckets.values():
        _assign_cluster(cluster, "morph_inflection")

    # Pass 2 : graphical -- même clé normalisée (accents/casse/tirets/espaces)
    buckets = {}
    for c in _ungrouped(candidates):
        buckets.setdefault(normalize_graphical_key(c.lemma), []).append(c)
    for cluster in buckets.values():
        _assign_cluster(cluster, "graphical")

    # Pass 3 : morph_prefix -- un seul token diffère, lié par un préfixe connu
    _group_single_token_diff(candidates, lang, "morph_prefix", _is_prefix_pair)

    # Pass 4 : syn_expansion -- squelette de contenu, sous-séquence contiguë
    _group_expansion(candidates)

    # Pass 5 : syn_permutation -- même multiset de lemmes de contenu, ordre différent
    buckets = {}
    for c in _ungrouped(candidates):
        skeleton = tuple(content_skeleton(c.pattern))
        if len(skeleton) < 2:
            continue
        buckets.setdefault(tuple(sorted(skeleton)), []).append(c)
    for cluster in buckets.values():
        distinct_orders = {tuple(content_skeleton(c.pattern)) for c in cluster}
        if len(distinct_orders) > 1:
            _assign_cluster(cluster, "syn_permutation")

    # Pass 6 : morph_derivation -- même squelette de CONTENU sauf une position,
    # liée par les tables TermSuite. Comparaison sur le squelette de contenu
    # (pas la séquence complète, contrairement à morph_prefix) : couvre
    # l'alternance N+Adj <-> N+Prep+N ("énergie éolienne"/"énergie du vent")
    # où la longueur totale diffère (préposition insérée) mais le squelette de
    # contenu a la même longueur (2 mots de contenu des deux côtés).
    _group_derivation(candidates, lang)
