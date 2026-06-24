"""Scoring par embeddings Loterre (Phase 5, v2.0).

Note chaque candidat par sa similarité cosinus au terme le **plus proche**
(plus proche voisin, max) des termes déjà connus du vocabulaire Loterre
ciblé — alternative à C-value/PositionRank, qui ne savent pas distinguer
"fréquent" de "spécifique au domaine" (voir
planification/planif_extraction_terminologique.md §Phase 5, et le cas
documenté sur le vocabulaire X64 : locutions méta-discursives dominant le
classement sur un corpus académique générique).

Plus proche voisin plutôt que centroïde (moyenne) : un vocabulaire Loterre
mélange des sous-catégories sémantiquement très différentes (ex. X64 :
noms de langues/ethnies à un seul mot pour 58-61% des concepts, mais aussi
des notions linguistiques abstraites multi-mots) — un centroïde unique
brouille cette diversité en un point moyen, et favorise mécaniquement les
candidats courts puisqu'ils dominent la composition du vocabulaire (voir
planification/analyse_benchmarks_extraction.md, entrée ACTER semi-supervisé
du 2026-06-23 : le centroïde généralise mal sur un vocabulaire divisé).

Fichier séparé de loterre_engine_v9_cli.py (règle Phase 0.5) : ne dépend que
de loterre_extraction_base.CandidateTerm. Le modèle sentence-transformers
est chargé paresseusement — aucun coût pour les extracteurs ncvalue/graph.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Sequence

from loterre_extraction_base import CandidateTerm

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache(maxsize=1)
def get_embed_model():
    """Charge le modèle sentence-transformers (paresseux, caché — un seul
    chargement par process, jamais déclenché si --extractor != embed).

    HF_HUB_OFFLINE forcé à "1" (sauf si déjà défini par l'appelant) : le
    modèle est toujours dans le cache local une fois téléchargé (Makefile
    `models-embed`), donc aucun appel réseau n'est nécessaire — cohérent
    avec la contrainte projet "pas d'accès cloud" (CLAUDE.md). Sans ça,
    sentence-transformers tente quand même de contacter le Hub avant de
    retomber sur le cache, et reste bloqué de longues minutes en cas de
    coupure réseau (constaté en usage réel le 2026-06-24)."""
    import os
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(_MODEL_NAME)


def load_vocabulary_terms(dict_path: str | Path) -> list[str]:
    """Lit le dictionnaire JSONL cible (format `label`/`pattern`/`id`/`pref`)
    et retourne les libellés préférés (`pref`) uniques, dédupliqués par `id`
    — plusieurs lignes (variantes de surface) partagent le même concept."""
    seen_ids: set[str] = set()
    terms: list[str] = []
    with open(dict_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            concept_id = entry.get("id")
            if concept_id in seen_ids:
                continue
            seen_ids.add(concept_id)
            pref = entry.get("pref")
            if pref:
                terms.append(pref)
    return terms


def _normalize_rows(embeddings):
    import numpy as np
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return embeddings / norms


def embed_vocabulary_terms(model, terms: Sequence[str]):
    """Encode *terms* en batch et retourne la matrice normalisée des
    embeddings (un vecteur par terme, pas une moyenne) — base pour la
    similarité au plus proche voisin dans score_candidates_embed()."""
    embeddings = model.encode(list(terms), batch_size=64, show_progress_bar=False)
    return _normalize_rows(embeddings)


def score_candidates_embed(candidates: list[CandidateTerm], model, vocab_embeddings) -> list[CandidateTerm]:
    """Affecte à chaque CandidateTerm sa similarité cosinus au terme le plus
    proche (max) du vocabulaire cible — pas à la moyenne (centroïde) de
    l'ensemble, qui généralise mal sur un vocabulaire sémantiquement divers
    (voir docstring du module). Retourne la liste triée par score décroissant
    (même convention que loterre_cvalue.score_candidates) ; à score égal —
    fréquent en pratique, beaucoup de candidats atteignent 1.0 (correspondance
    exacte) —, départage par nombre de tokens décroissant pour ne pas laisser
    les unitermes (mécaniquement plus fréquents, donc placés avant par un tri
    stable) masquer systématiquement les multitermes à score identique."""
    if not candidates:
        return []
    terms = [c.term for c in candidates]
    embeddings = model.encode(terms, batch_size=64, show_progress_bar=False)
    embeddings_norm = _normalize_rows(embeddings)

    similarities = embeddings_norm @ vocab_embeddings.T  # (n_candidats, n_termes_vocab)
    # clip : la précision float32 peut produire 1.0000002 au lieu de 1.0
    # pour un candidat identique à un terme du vocabulaire.
    max_similarities = similarities.max(axis=1).clip(-1.0, 1.0)

    for c, score in zip(candidates, max_similarities):
        c.score = float(score)
        c.rule = "embed"

    return sorted(candidates, key=lambda c: (-c.score, -len(c.term.split())))


def filter_by_embed_threshold(candidates: Sequence[CandidateTerm], threshold: float) -> list[CandidateTerm]:
    return [c for c in candidates if c.score >= threshold]
