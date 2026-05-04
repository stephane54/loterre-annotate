# Loterre v10 — stratégie d’exécution rapide

## Objectif

Préparer une version rapide :

```text
fast path → linguistic path → semantic path
```

Le principe est de ne pas appliquer spaCy, embeddings ou LLM sur tout le texte.

## Architecture

```text
texte
↓
fast exact matcher
↓
si non ambigu → sortie directe
↓
si ambigu → spaCy + filtres v9
↓
si encore ambigu → reranker sémantique
```

## Roadmap v10

1. Précompiler les dictionnaires.
2. Matcher exact avant spaCy.
3. Envoyer à spaCy uniquement les cas ambigus.
4. Ajouter un reranker uniquement pour les cas encore ambigus.
5. Générer HTML / Markdown après coup.
