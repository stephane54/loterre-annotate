#!/usr/bin/env python3
"""Generate French text corpora and gold standards for Loterre vocabularies.

Structure mirrors the English corpora in data/texts/:
  - Document 0 : texte réaliste riche (~30-40 occurrences)
  - Documents 1-10 : textes structurés "Dans l'étude X.Y, …"
    avec 3 termes par étude, variation flexionnelle sur 1-2 termes par groupe.

Usage:
    python3 scripts/generate_fr_corpus.py
Produces: data/texts/{P66,27X,9SD,8HQ,B9M,BVM,QX8}_fr.jsonl
"""
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ── Flexion helpers ────────────────────────────────────────────────────────────

_INVARIABLE = frozenset({"processus", "corpus", "virus", "campus", "nexus", "biais",
                          "temps", "cours", "sens", "poids", "bras", "bas", "tas",
                          "choix", "voix", "flux", "reflux", "silex", "lupus"})

def pluralize(word: str) -> str:
    """Minimal French pluralizer for a single word."""
    if not word or word[0].isupper():
        return word          # proper noun or empty
    if word in _INVARIABLE or word.endswith(("s", "x", "z")):
        return word          # invariable
    if word.endswith("al") and word not in {"bal", "cal", "carnaval", "festival", "récital"}:
        return word[:-2] + "aux"
    if word.endswith("eau") or word.endswith("au"):
        return word + "x"
    return word + "s"

def pluralize_term(term: str) -> str:
    """Pluralize the first noun of a French compound term."""
    words = term.split()
    if not words:
        return term
    first = words[0]
    if first[0].isupper():
        return term           # proper name: invariable
    words[0] = pluralize(first)
    # If second-to-last word is a noun directly followed by ADJ (no preposition):
    # also pluralize the adjective
    if len(words) >= 2 and words[-1][0].islower() and not any(
            w in {"de", "du", "des", "à", "au", "aux", "par", "en", "pour",
                  "sur", "sous", "avec", "sans", "le", "la", "les", "un", "une",
                  "d'", "l'", "que", "qui"} for w in words[1:-1]):
        words[-1] = pluralize(words[-1])
    return " ".join(words)

def feminize(word: str) -> str:
    """Feminine form — only for clear adjective patterns; unchanged otherwise."""
    if word.endswith("eur"):   return word[:-3] + "euse"
    if word.endswith("eux"):   return word[:-3] + "euse"
    if word.endswith("if"):    return word[:-2] + "ive"
    if word.endswith("el"):    return word[:-2] + "elle"
    if word.endswith("en"):    return word + "ne"
    # No default fallback: nouns and other adj patterns are left unchanged
    return word

def is_proper(pref: str) -> bool:
    """Return True if pref is a proper noun (must not be flexed)."""
    # Starts with uppercase letter, or apostrophe+uppercase, or parenthesis
    stripped = pref.lstrip("'\"")
    return bool(stripped) and (stripped[0].isupper() or stripped[0] == "(")

def variant(pref: str, mode: str) -> str:
    """Return a flexional variant of pref: 'pl' = plural, 'fem' = feminine last adj.
    Proper nouns are returned unchanged.
    """
    if is_proper(pref):
        return pref
    if mode == "pl":
        return pluralize_term(pref)
    if mode == "fem":
        words = pref.split()
        if len(words) >= 2 and not is_proper(words[-1]):
            words[-1] = feminize(words[-1])
        return " ".join(words)
    return pref

# ── Dictionary loading ─────────────────────────────────────────────────────────

def load_dict(path: Path, skip_proper=False, min_words=2, max_words=8) -> list[dict]:
    """Load dictionary entries, optionally filtering short / proper-name entries."""
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            lbl = e.get("label") or e.get("pref") or ""
            if not lbl or not e.get("id"):
                continue
            words = lbl.split()
            if len(words) < min_words or len(words) > max_words:
                continue
            if skip_proper and lbl[0].isupper():
                continue
            out.append(e)
    return out

def load_proper(path: Path, max_words=4) -> list[dict]:
    """Load proper-noun entries (place names, etc.)."""
    out = []
    seen = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            pref = e.get("pref") or e.get("label") or ""
            if not pref or not e.get("id") or pref in seen:
                continue
            if len(pref.split()) > max_words:
                continue
            seen.add(pref)
            out.append(e)
    return out

# ── Text / offset helpers ──────────────────────────────────────────────────────

def find_offsets(text: str, surface: str) -> tuple[int, int] | None:
    """Find first occurrence of surface (case-sensitive then insensitive)."""
    idx = text.find(surface)
    if idx >= 0:
        return idx, idx + len(surface)
    idx = text.lower().find(surface.lower())
    if idx >= 0:
        return idx, idx + len(surface)
    return None

def make_match(text: str, surface: str, pref: str, ark: str,
               rule: str = "lemma_pattern_seq") -> dict | None:
    sp = find_offsets(text, surface)
    if sp is None:
        return None
    return {"found": surface, "pref": pref, "id": ark,
            "start": sp[0], "end": sp[1], "rule": rule}

# ── Corpus generators ──────────────────────────────────────────────────────────

def dedup_by_pref(entries: list[dict]) -> list[dict]:
    """Remove duplicate pref values, keeping first occurrence."""
    seen: set[str] = set()
    out = []
    for e in entries:
        p = e.get("pref", "")
        if p and p not in seen:
            seen.add(p)
            out.append(e)
    return out

def build_structured_docs(template: str, groups: list[list[dict]]) -> list[dict]:
    """
    Build documents 1-10.  groups[i] = list of 3 entry dicts.
    template must contain {i}, {j}, {t}.
    Applies flexional variant cyclically: pl / fem / none.
    Each term appears in its own sentence; offsets are located within that sentence.
    """
    docs = []
    modes = ["pl", "fem", "none"]
    for doc_i, grp in enumerate(groups):
        sentences: list[str] = []
        entry_meta: list[tuple] = []  # (surface, pref, ark)
        for sub_j, entry in enumerate(grp, 1):
            pref = entry["pref"]
            ark  = entry["id"]
            mode = modes[(doc_i + sub_j) % 3]
            surface = variant(pref, mode)
            sentence = template.format(i=doc_i + 1, j=sub_j, t=surface)
            sentences.append(sentence)
            entry_meta.append((surface, pref, ark))

        text = " ".join(sentences)
        matches = []
        cursor = 0  # track position in concatenated text
        for k, (sentence, (surface, pref, ark)) in enumerate(zip(sentences, entry_meta)):
            # Find where this sentence starts in text
            sent_pos = text.find(sentence, cursor)
            if sent_pos < 0:
                cursor = 0
                sent_pos = text.find(sentence)
            if sent_pos >= 0:
                local_idx = sentence.find(surface)
                if local_idx >= 0:
                    abs_start = sent_pos + local_idx
                    matches.append({
                        "found": surface, "pref": pref, "id": ark,
                        "start": abs_start, "end": abs_start + len(surface),
                        "rule": "lemma_pattern_seq",
                    })
                cursor = sent_pos + len(sentence)

        docs.append({"id": doc_i + 1, "value": text, "expected_matches": matches})
    return docs

# ── P66 — Psychologie cognitive ───────────────────────────────────────────────

def gen_P66_fr(dict_path: Path) -> list[dict]:
    entries = dedup_by_pref(load_dict(dict_path, skip_proper=True, min_words=2))
    # Prefer multi-word psychology terms (length 2-6 tokens)
    selected = [e for e in entries
                if 2 <= len(e["pref"].split()) <= 6
                and not e["pref"].startswith("P.") ][:90]
    if len(selected) < 90:
        selected = entries[:90]
    selected = selected[:90]

    # Document 0 — texte riche
    DOC0_TERMS = [
        ("mémoire à long terme", "mémoires à long terme"),
        ("mémoire à court terme", "mémoire à court terme"),
        ("mémoire de travail", "mémoires de travail"),
        ("effet de récence", "effets de récence"),
        ("effet de primauté", "effet de primauté"),
        ("encodage", "encodages"),
        ("rappel libre", "rappels libres"),
        ("interférence proactive", "interférences proactives"),
        ("interférence rétroactive", "interférence rétroactive"),
        ("consolidation de la mémoire", "consolidation de la mémoire"),
        ("attention sélective", "attentions sélectives"),
        ("mémoire épisodique", "mémoires épisodiques"),
        ("mémoire sémantique", "mémoire sémantique"),
        ("processus de récupération", "processus de récupération"),
        ("oubli motivé", "oubli motivé"),
    ]
    # Build doc 0 from dict
    doc0_entries = {e["pref"]: e for e in entries}
    doc0_text_parts = [
        "La recherche en psychologie cognitive distingue plusieurs systèmes mnésiques. "
        "Les {t0} permettent de conserver des informations sur de longues périodes, "
        "tandis que la {t1} assure le maintien temporaire des données en cours de traitement. "
        "Les {t2} jouent un rôle central dans la planification et le raisonnement. "
        "L'étude des {t3} montre une sensibilité accrue aux mots récents, "
        "alors que l'{t4} avantage les éléments présentés en début de liste. "
        "Le chercheur analyse les {t5} en contexte de double tâche. "
        "Les participants effectuent des {t6} immédiatement après l'apprentissage. "
        "Les {t7} perturbent les souvenirs récemment encodés, "
        "contrairement à l'{t8} qui altère les traces antérieures. "
        "La {t9} survient principalement pendant le sommeil. "
        "L'{t10} permet de focaliser les ressources cognitives sur les stimuli pertinents. "
        "Les {t11} contiennent des épisodes autobiographiques datés et localisés, "
        "alors que la {t12} stocke les connaissances générales. "
        "Les {t13} varient selon le degré de profondeur d'élaboration. "
        "L'{t14} est plus fréquent pour les souvenirs chargés émotionnellement."
    ]
    text_template = " ".join(doc0_text_parts)
    # Fill in terms
    surfaces = [t[1] for t in DOC0_TERMS]
    text0 = text_template.format(**{f"t{i}": s for i, s in enumerate(surfaces)})
    matches0 = []
    for i, (pref_key, surface) in enumerate(DOC0_TERMS):
        e = doc0_entries.get(pref_key)
        if e:
            m = make_match(text0, surface, pref_key, e["id"])
            if m:
                matches0.append(m)

    # Documents 1-10
    template = "Dans l'étude {i}.{j}, le protocole évalue les {t} au cours d'une session de mémoire contrôlée."

    groups = [selected[i*3:(i+1)*3] for i in range(10)]
    structured = build_structured_docs(template, groups)

    return [{"id": "0", "value": text0, "expected_matches": matches0}] + structured


# ── 27X — Archéologie ─────────────────────────────────────────────────────────

def gen_27X_fr(dict_path: Path) -> list[dict]:
    entries = dedup_by_pref(load_dict(dict_path, skip_proper=False, min_words=2))
    common = [e for e in entries if not e["pref"][0].isupper()][:60]
    named  = [e for e in entries if e["pref"][0].isupper()][:30]
    selected = (common + named)[:90]

    # Doc 0
    doc0_text = (
        "L'archéologie de terrain recouvre des méthodes très diverses. "
        "La stratigraphie archéologique permet de dater les couches successives d'occupation. "
        "Les fouilles préventives révèlent souvent des structures architecturales bien conservées. "
        "L'analyse céramique constitue un outil de datation relative incontournable. "
        "Les techniques de datation au carbone 14 précisent les chronologies absolues. "
        "Les relevés photogrammétriques facilitent la documentation des vestiges. "
        "L'étude des mobiliers funéraires éclaire les pratiques rituelles des sociétés anciennes. "
        "Les analyses ostéologiques renseignent sur les régimes alimentaires et les maladies. "
        "La prospection géophysique localise les anomalies souterraines sans excavation. "
        "Les corpus céramiques permettent de retracer les réseaux d'échanges commerciaux. "
        "L'enregistrement des contextes stratigraphiques conditionne la validité des interprétations. "
        "Les études paléobotaniques révèlent l'environnement végétal des sites anciens. "
        "L'archéologie expérimentale reconstitue les gestes techniques disparus."
    )
    # Map prefs to entries
    d0_terms = []
    for e in entries:
        for kw in ("stratigraphie", "fouille", "céramique", "datation", "analyse", "structure"):
            if kw in e["pref"].lower():
                d0_terms.append(e)
                break
    matches0 = []
    for e in d0_terms[:10]:
        pref = e["pref"]
        surf = variant(pref, "pl") if not pref[0].isupper() else pref
        m = make_match(doc0_text, surf, pref, e["id"])
        if m is None:
            m = make_match(doc0_text, pref, pref, e["id"])
        if m:
            matches0.append(m)

    template = "Dans le rapport de fouilles {i}.{j}, l'analyse comparative recense les {t} au sein du même corpus de données archéologiques."
    groups = [selected[i*3:(i+1)*3] for i in range(10)]
    structured = build_structured_docs(template, groups)

    return [{"id": "0", "value": doc0_text, "expected_matches": matches0}] + structured


# ── 9SD — Géographie mondiale ─────────────────────────────────────────────────

def gen_9SD_fr(dict_path: Path) -> list[dict]:
    # For 9SD, we use proper place names
    entries = load_proper(dict_path, max_words=3)
    # Prefer multi-word place names
    multi = [e for e in entries if len(e["pref"].split()) >= 2][:60]
    single = [e for e in entries if len(e["pref"].split()) == 1][:30]
    selected = (multi + single)[:90]

    doc0_text = (
        "La géographie mondiale couvre une grande diversité de territoires. "
        "L'Afrique australe regroupe plusieurs États aux économies en développement. "
        "L'Amérique du Sud est traversée par la cordillère des Andes. "
        "L'Asie du Sud-Est constitue une région d'une biodiversité exceptionnelle. "
        "L'Europe centrale a connu de profondes transformations politiques depuis 1989. "
        "L'Océanie rassemble des archipels dispersés sur l'ensemble du Pacifique. "
        "L'Asie centrale relie traditionnellement l'Europe à l'Extrême-Orient. "
        "L'Amérique centrale subit régulièrement des phénomènes naturels extrêmes. "
        "Le Moyen-Orient demeure une zone géopolitique particulièrement stratégique. "
        "L'Afrique subsaharienne concentre les plus fortes croissances démographiques mondiales."
    )
    matches0 = []
    for e in entries[:8]:
        m = make_match(doc0_text, e["pref"], e["pref"], e["id"])
        if m:
            matches0.append(m)

    template = "Dans l'atlas {i}.{j}, la description géographique comprend {t} dans le même ensemble territorial."
    groups = [selected[i*3:(i+1)*3] for i in range(10)]
    structured = build_structured_docs(template, groups)

    return [{"id": "0", "value": doc0_text, "expected_matches": matches0}] + structured


# ── 8HQ — Chimie / Éléments périodiques ──────────────────────────────────────

def gen_8HQ_fr(dict_path: Path) -> list[dict]:
    # 8HQ: chemical elements — single words mostly
    entries_raw = []
    seen_prefs = set()
    with dict_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            pref = e.get("pref") or ""
            if not pref or not e.get("id") or pref in seen_prefs:
                continue
            seen_prefs.add(pref)
            entries_raw.append(e)

    # Prefer canonical element names (single-word prefs)
    elements = [e for e in entries_raw if len((e.get("pref") or "").split()) == 1][:90]

    # Doc 0 — rich chemistry text
    doc0_text = (
        "Le tableau périodique des éléments recense 118 éléments chimiques connus. "
        "L'hydrogène, le plus léger de tous, est le constituant principal des étoiles. "
        "L'hélium est utilisé pour refroidir les aimants supraconducteurs. "
        "Le carbone forme la base de toute chimie organique. "
        "L'azote constitue 78 % de l'atmosphère terrestre. "
        "L'oxygène est indispensable à la respiration des organismes aérobies. "
        "Le sodium réagit vivement avec l'eau en dégageant de l'hydrogène. "
        "Le magnésium brûle avec une flamme blanche intense. "
        "L'aluminium est le métal le plus abondant dans la croûte terrestre. "
        "Le silicium est la base de l'industrie des semi-conducteurs. "
        "Le phosphore existe sous plusieurs formes allotropiques. "
        "Le soufre est essentiel à la synthèse de nombreux acides. "
        "Le chlore est utilisé comme désinfectant depuis le XIXe siècle. "
        "Le potassium joue un rôle clé dans la transmission nerveuse. "
        "Le calcium est le constituant principal des os et des dents. "
        "Le fer est le métal le plus produit et utilisé dans l'industrie. "
        "Le cuivre est un excellent conducteur thermique et électrique. "
        "Le zinc protège l'acier contre la corrosion par galvanisation. "
        "L'or est utilisé en électronique pour sa résistance à l'oxydation. "
        "L'uranium est le combustible de base des réacteurs nucléaires."
    )
    d0_prefs = ["hydrogène", "hélium", "carbone", "azote", "oxygène",
                "sodium", "magnésium", "aluminium", "silicium", "phosphore",
                "soufre", "chlore", "potassium", "calcium", "fer",
                "cuivre", "zinc", "or", "uranium"]
    elem_map = {e["pref"].lower(): e for e in elements}
    matches0 = []
    for p in d0_prefs:
        e = elem_map.get(p)
        if e:
            # Elements in French text start with lowercase after article
            for surf in [p, p.capitalize()]:
                m = make_match(doc0_text, surf, e["pref"], e["id"])
                if m:
                    matches0.append(m)
                    break

    template = "Dans l'expérience {i}.{j}, l'analyse élémentaire étudie {t}, élément chimique du tableau périodique."
    # For elements, no flexion: they are proper nouns
    groups = [elements[i*3:(i+1)*3] for i in range(10)]

    docs_structured = []
    for doc_i, grp in enumerate(groups):
        parts = []
        matches = []
        for sub_j, e in enumerate(grp, 1):
            pref = e["pref"]
            sentence = template.format(i=doc_i+1, j=sub_j, t=pref)
            parts.append(sentence)
        text = " ".join(parts)
        for sub_j, e in enumerate(grp, 1):
            m = make_match(text, e["pref"], e["pref"], e["id"])
            if m:
                matches.append(m)
        docs_structured.append({"id": doc_i + 1, "value": text, "expected_matches": matches})

    return [{"id": "0", "value": doc0_text, "expected_matches": matches0}] + docs_structured


# ── B9M — Biologie animale / éthologie ───────────────────────────────────────

def gen_B9M_fr(dict_path: Path) -> list[dict]:
    all_entries = dedup_by_pref(load_dict(dict_path, skip_proper=False, min_words=2))
    # Prefer genuine biology/ethology terms
    bio_kws = {"animal", "comportement", "locomotion", "social", "cognitif",
               "apprentissage", "communication", "évolution", "reproduction",
               "territoire", "migration", "prédation", "alimentation", "outil",
               "signal", "reconnaissance", "perception", "moteur", "cerveau",
               "neuronal", "sensoriel", "auditif", "visuel", "brachiation",
               "posture", "bipédie", "quadrupédie", "masse", "cycle", "histoire"}
    preferred = [e for e in all_entries
                 if any(kw in e["pref"].lower() for kw in bio_kws)]
    rest = [e for e in all_entries if e not in preferred]
    entries = (preferred + rest)[:100]
    selected = entries[:90]

    doc0_text = (
        "L'éthologie étudie le comportement des animaux dans leur milieu naturel. "
        "La communication acoustique joue un rôle crucial chez de nombreux mammifères. "
        "Les histoires évolutives des espèces sont retracées par phylogénétique moléculaire. "
        "L'utilisation d'outils a été observée chez plusieurs espèces de primates. "
        "Le centre de masse corporelle détermine l'équilibre postural lors de la locomotion. "
        "La locomotion quadrupède est adaptée aux déplacements sur substrats instables. "
        "Les cycles de communication rythment les interactions sociales au sein des groupes. "
        "Les comportements de coopération optimisent la chasse collective chez les carnivores. "
        "La cognition sociale permet d'anticiper les actions des congénères. "
        "Les systèmes de signalisation chimique régulent les comportements reproducteurs. "
        "L'apprentissage par observation accélère l'acquisition de nouvelles compétences. "
        "Les stratégies de recherche alimentaire dépendent des ressources disponibles. "
        "La reconnaissance individuelle est essentielle au maintien des hiérarchies sociales."
    )
    d0_prefs_kw = ["communication", "histoire", "outil", "masse", "quadrupédie",
                   "cycle", "comportement", "cognition", "apprentissage", "stratégie"]
    matches0 = []
    for e in entries:
        pref = e["pref"]
        if any(kw in pref.lower() for kw in d0_prefs_kw):
            surf = variant(pref, "pl")
            m = make_match(doc0_text, surf, pref, e["id"])
            if m is None:
                m = make_match(doc0_text, pref, pref, e["id"])
            if m:
                matches0.append(m)
            if len(matches0) >= 15:
                break

    template = "Dans l'étude {i}.{j}, l'analyse éthologique porte sur les {t} dans un contexte d'observation en milieu naturel."
    groups = [selected[i*3:(i+1)*3] for i in range(10)]
    structured = build_structured_docs(template, groups)

    return [{"id": "0", "value": doc0_text, "expected_matches": matches0}] + structured


# ── BVM — Géographie française ────────────────────────────────────────────────

def gen_BVM_fr(dict_path: Path) -> list[dict]:
    entries = load_proper(dict_path, max_words=4)
    # Prefer multi-word French place names
    multi = [e for e in entries if len(e["pref"].split()) >= 2][:60]
    single = [e for e in entries if len(e["pref"].split()) == 1][:30]
    selected = (multi + single)[:90]

    doc0_text = (
        "La France métropolitaine regroupe 101 départements et régions d'outre-mer. "
        "La France d'outre-mer comprend des territoires disséminés sur tous les océans. "
        "Paris constitue la métropole la plus peuplée de l'Union européenne. "
        "La Bretagne est connue pour son identité culturelle et linguistique forte. "
        "La Provence-Alpes-Côte d'Azur attire chaque année des millions de touristes. "
        "L'Occitanie regroupe deux anciennes régions administratives depuis 2016. "
        "La Nouvelle-Aquitaine est la plus grande région métropolitaine par sa superficie. "
        "Le Grand Est partage des frontières avec l'Allemagne, le Luxembourg et la Belgique. "
        "Les Hauts-de-France connaissent une reconversion économique après le déclin industriel. "
        "L'Île-de-France concentre plus de 18 % de la population française totale. "
        "La Normandie abrite de nombreux sites du débarquement allié de juin 1944. "
        "La Bourgogne-Franche-Comté est réputée pour ses vignobles et sa gastronomie. "
        "La région Centre-Val de Loire est traversée par le plus long fleuve de France."
    )
    matches0 = []
    for e in entries[:10]:
        m = make_match(doc0_text, e["pref"], e["pref"], e["id"])
        if m:
            matches0.append(m)

    template = "Dans l'inventaire territorial {i}.{j}, l'étude géographique recense {t} dans le même périmètre administratif."
    groups = [selected[i*3:(i+1)*3] for i in range(10)]
    structured = build_structured_docs(template, groups)

    return [{"id": "0", "value": doc0_text, "expected_matches": matches0}] + structured


# ── QX8 — Géosciences ────────────────────────────────────────────────────────

def gen_QX8_fr(dict_path: Path) -> list[dict]:
    entries = dedup_by_pref(load_dict(dict_path, skip_proper=False, min_words=2))
    common = [e for e in entries if not e["pref"][0].isupper()][:75]
    named  = [e for e in entries if e["pref"][0].isupper()][:15]
    selected = (common + named)[:90]

    doc0_text = (
        "Les géosciences étudient l'histoire et la structure interne de la Terre. "
        "Les structures géomorphologiques témoignent de millions d'années d'érosion. "
        "Les paramètres géographiques déterminent la distribution des écosystèmes. "
        "Les anneaux de croissance d'arbre reconstituent les paléoclimats régionaux. "
        "La profondeur de compensation des carbonates contrôle la sédimentation océanique. "
        "Le rapport des isotopes stables du carbone trace les cycles biogéochimiques. "
        "Les cycles biogéochimiques gouvernent les flux de matière entre les réservoirs. "
        "Les éruptions volcaniques modifient la composition atmosphérique à l'échelle mondiale. "
        "Les failles tectoniques concentrent l'activité sismique dans les zones de subduction. "
        "Les dépôts sédimentaires enregistrent les variations climatiques passées. "
        "La datation radiométrique établit des chronologies absolues pour les roches anciennes. "
        "Les modèles numériques de circulation océanique simulent les courants marins profonds. "
        "Les paléosols indiquent les conditions d'humidité et de végétation des périodes antérieures."
    )
    d0_kws = ["géomorpho", "géographi", "anneau", "profondeur", "isotope",
              "cycle", "volcan", "tectoni", "sédiment", "datation", "paléo"]
    matches0 = []
    for e in entries:
        pref = e["pref"]
        if any(kw in pref.lower() for kw in d0_kws):
            surf = variant(pref, "pl") if not pref[0].isupper() else pref
            m = make_match(doc0_text, surf, pref, e["id"])
            if m is None:
                m = make_match(doc0_text, pref, pref, e["id"])
            if m:
                matches0.append(m)
            if len(matches0) >= 15:
                break

    template = "Dans l'étude géoscientifique {i}.{j}, l'analyse porte sur les {t} dans le même contexte géologique."
    groups = [selected[i*3:(i+1)*3] for i in range(10)]
    structured = build_structured_docs(template, groups)

    return [{"id": "0", "value": doc0_text, "expected_matches": matches0}] + structured


# ── Write output ──────────────────────────────────────────────────────────────

def write_jsonl(docs: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    total_matches = sum(len(d.get("expected_matches", [])) for d in docs)
    print(f"  {path.name}: {len(docs)} documents, {total_matches} expected_matches")


GENERATORS = {
    "P66_fr": (gen_P66_fr, "fr_annot_P66.jsonl"),
    "27X_fr": (gen_27X_fr, "fr_annot_27X.jsonl"),
    "9SD_fr": (gen_9SD_fr, "fr_annot_9SD.jsonl"),
    "8HQ_fr": (gen_8HQ_fr, "fr_annot_8HQ.jsonl"),
    "B9M_fr": (gen_B9M_fr, "fr_annot_B9M.jsonl"),
    "BVM_fr": (gen_BVM_fr, "fr_annot_BVM.jsonl"),
    "QX8_fr": (gen_QX8_fr, "fr_annot_QX8.jsonl"),
}

if __name__ == "__main__":
    dicts_dir = ROOT / "data" / "dicts"
    texts_dir = ROOT / "data" / "texts"
    print("Generating French corpora …")
    for vocab_id, (gen_fn, dict_file) in GENERATORS.items():
        dict_path = dicts_dir / dict_file
        if not dict_path.exists():
            print(f"  SKIP {vocab_id}: {dict_path} not found")
            continue
        print(f"  {vocab_id} …", end=" ", flush=True)
        try:
            docs = gen_fn(dict_path)
            write_jsonl(docs, texts_dir / f"{vocab_id}.jsonl")
        except Exception as ex:
            print(f"ERROR: {ex}")
    print("Done.")
