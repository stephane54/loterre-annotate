"""PositionRank (Florescu & Caragea 2017) — alternative à C-value pour les
corpus trop petits pour que les statistiques de fréquence soient fiables (voir
planification/analyse_benchmarks_extraction.md, seuil ~50 000 tokens).

PageRank biaisé sur un graphe de co-occurrence de mots de contenu, où le score
initial de chaque mot dépend de sa position dans le document (les mots qui
apparaissent tôt comptent plus). Implémentation Python pure (itération de
puissance), sans dépendance graphe externe (pas de networkx).

Fichier indépendant de spaCy par design : prend des tuples (index, lemme, pos)
déjà extraits par l'appelant (loterre_extract_cli.py), pour rester testable et
cohérent avec la séparation des modules (règle Phase 0.5).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

_CONTENT_POS = frozenset({"NOUN", "PROPN", "ADJ"})


def build_cooccurrence_graph(
    per_doc_tokens: Iterable[list[tuple[int, str, str]]], window: int = 4
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Construit le graphe de co-occurrence pondéré et le poids de position
    cumulé par lemme, sur l'ensemble des documents.

    per_doc_tokens : une liste par document de tuples (index_token, lemme, pos).
    Seuls les mots de contenu (NOUN/PROPN/ADJ) sont retenus comme nœuds.

    Retourne (graph, position_weight) :
      graph[lemme_a][lemme_b] = poids de co-occurrence (cumulé sur le corpus)
      position_weight[lemme]  = somme de 1/(position+1) sur toutes les occurrences
    """
    graph: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    position_weight: dict[str, float] = defaultdict(float)

    for tokens in per_doc_tokens:
        content = [(i, lemma) for i, lemma, pos in tokens if pos in _CONTENT_POS]
        for idx, (i, lemma) in enumerate(content):
            position_weight[lemma] += 1.0 / (i + 1)
            for j in range(idx + 1, min(idx + 1 + window, len(content))):
                _, other = content[j]
                if other == lemma:
                    continue
                graph[lemma][other] += 1.0
                graph[other][lemma] += 1.0

    return graph, position_weight


def position_rank(
    graph: dict[str, dict[str, float]],
    position_weight: dict[str, float],
    alpha: float = 0.85,
    max_iter: int = 50,
    tol: float = 1e-6,
) -> dict[str, float]:
    """PageRank biaisé par la position (le vecteur de personnalisation est
    position_weight normalisé) — itération de puissance jusqu'à convergence."""
    nodes = list(position_weight.keys())
    if not nodes:
        return {}

    total_weight = sum(position_weight.values())
    if total_weight > 0:
        personalization = {n: position_weight[n] / total_weight for n in nodes}
    else:
        personalization = {n: 1.0 / len(nodes) for n in nodes}

    out_weight = {n: sum(graph.get(n, {}).values()) for n in nodes}
    scores = dict(personalization)

    for _ in range(max_iter):
        new_scores = {}
        max_delta = 0.0
        for n in nodes:
            incoming = 0.0
            for m, w in graph.get(n, {}).items():
                ow = out_weight.get(m, 0.0)
                if ow > 0:
                    incoming += (w / ow) * scores.get(m, 0.0)
            new_scores[n] = (1 - alpha) * personalization[n] + alpha * incoming
            max_delta = max(max_delta, abs(new_scores[n] - scores.get(n, 0.0)))
        scores = new_scores
        if max_delta < tol:
            break

    return scores


def score_candidates_positionrank(candidates, word_scores: dict[str, float]):
    """Affecte à chaque CandidateTerm le score PositionRank = somme des scores
    de ses lemmes constitutifs, et retourne la liste triée par score décroissant
    (même convention que loterre_cvalue.score_candidates)."""
    for c in candidates:
        lemma_tokens = c.lemma.split()
        c.score = sum(word_scores.get(t, 0.0) for t in lemma_tokens)
        c.rule = "positionrank"
    return sorted(candidates, key=lambda c: -c.score)
