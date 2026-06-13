# Analyse : Intégration de l'extraction terminologique dans loterre-annotate

**Date :** 2026-06-13  
**Auteur :** Stéphane Schneider  
**Version cible :** v2.0

---

## Contexte

loterre-annotate est un **annotateur par dictionnaire** : il cherche dans un texte les termes d'un vocabulaire connu (Loterre) et renvoie les occurrences avec leurs URIs. TermSuite fait l'inverse : il **extrait des candidats termes** d'un corpus sans vocabulaire préalable. Ce sont des outils complémentaires, pas concurrents.

L'objectif est d'offrir trois modes d'utilisation :

| Mode | Description |
|------|-------------|
| `--mode annotate` | Comportement actuel — lookup dans un vocabulaire Loterre |
| `--mode extract` | Extraction de candidats termes depuis le texte (sans vocabulaire) |
| `--mode extract+annotate` | Extraction puis croisement avec un vocabulaire Loterre |

---

## 1. Piper TermSuite vs Intégrer dans loterre-annotate

### Arguments pour le piping (TermSuite → loterre-annotate)

| Avantage | Détail |
|----------|--------|
| Maturité | TermSuite a 15 ans de R&D, C-value, détection de variantes éprouvés |
| Séparation des responsabilités | Chaque outil fait ce qu'il sait faire |
| Pas de travail de développement | Pipeline shell en quelques heures |

### Inconvénients du piping — rédhibitoires

- **Java** : TermSuite est une grosse dépendance UIMA/Java, compliquée à déployer, lente à démarrer (JVM cold start ~3-5s à chaque appel)
- **Double preprocessing** : TermSuite fait sa propre tokenisation/POS tagging, loterre-annotate refait tout avec spaCy — coût x2 sans bénéfice
- **Formats incompatibles** : glue code fragile nécessaire pour passer les sorties TermSuite à loterre
- **Maintenance croisée** : TermSuite est peu maintenu (dernier commit GitHub ~2020), dépendances obsolètes
- **Installation complexe** : nécessite Java, TreeTagger, et la configuration de plusieurs variables d'environnement

### Arguments pour l'intégration dans loterre-annotate

**L'infrastructure est déjà là.** loterre-annotate utilise spaCy avec tokenisation, POS tagging, lemmatisation sur chaque texte traité. L'extraction terminologique classique (C-value, noun chunks filtrés) repose exactement sur ces mêmes couches. Ajouter un module d'extraction, c'est **réutiliser le pipeline existant**, pas en ajouter un second.

- Pas de dépendance Java
- Aucun double preprocessing : tokens, POS, lemmes déjà calculés
- Croisement extraction/annotation natif et efficace
- Maintenance unique, format unifié
- CLI cohérente pour l'utilisateur

**Verdict : intégrer dans loterre-annotate.**

---

## 2. Peut-on égaler les performances de TermSuite ?

### Ce que fait TermSuite

TermSuite repose sur l'algorithme **C-value** (Frantzi et al. 1998) pour scorer les candidats multi-mots :

```
Tokenisation → POS/Lemme (TreeTagger) → Extraction noun chunks → C-value → Détection variantes
```

loterre-annotate fait déjà les deux premières étapes (tokenisation, POS, lemme via spaCy). Il manque : le scoring C-value et le groupement de variantes.

### L'algorithme C-value

C-value pénalise un terme candidat s'il apparaît fréquemment comme sous-chaîne d'un terme plus long. Par exemple, si *"réseau de neurones"* est fréquent, le score de *"réseau"* seul est réduit. C'est implémentable en Python pur en quelques centaines de lignes.

### Comparaison technologique (2025)

| Approche | Qualité | Vitesse | Effort dev | Notes |
|----------|---------|---------|------------|-------|
| **C-value Python** | = TermSuite | Rapide | Moyen | Bien documenté, reproductible, interprétable |
| **spaCy noun_chunks + TF-IDF** | Légèrement < | Très rapide | Faible | Bon pour corpus volumineux |
| **KeyBERT** (sentence-transformers) | > TermSuite | Moyen | Faible | Excellent pour l'anglais scientifique |
| **SciBERT/CamemBERT fine-tuné** | >> TermSuite | Lent | Élevé | Nécessite données d'entraînement annotées |

**Recommandation technologique** : C-value Python comme moteur de base (parité TermSuite garantie, interprétable, pas de GPU requis), avec option sentence-transformers activable pour le re-ranking sur textes scientifiques.

Le choix C-value est stratégique :
- Reproductibilité et explicabilité des scores
- Fonctionne en CPU sur tout serveur
- Algorithme validé scientifiquement depuis 25 ans
- Fonctionne bien sur le français et l'anglais sans adaptation

---

## 3. Architecture cible

```
                    ┌──────────────────────────────────┐
                    │         loterre-annotate          │
                    │                                   │
  texte/corpus ──►  │  spaCy pipeline (déjà existant)   │
                    │  tokenisation / POS / lemme        │
                    │                                   │
                    │         ┌──────────────┐          │
                    │  mode   │  EXTRACTEUR  │          │
                    │  extract│  C-value     │──► candidats (JSONL)
                    │   ────► │  noun chunks │          │
                    │         │  variantes   │          │
                    │         └──────┬───────┘          │
                    │                │                  │
                    │         ┌──────▼───────┐          │
                    │  mode   │  ANNOTATEUR  │          │
                    │  annot  │  (existant)  │──► annotations (JSONL)
                    │   ────► │  5-pass      │          │
                    │         │  Trie-match  │          │
                    │         └──────────────┘          │
                    └──────────────────────────────────┘
```

En mode `extract+annotate` : les candidats extraits par C-value sont croisés avec le vocabulaire Loterre via le moteur d'annotation existant. Chaque candidat reçoit un statut : `in_vocabulary` (avec URI) ou `not_in_vocabulary`.

---

## 4. Stratégie de développement step by step

### Phase 0 — Conception et spécification (2 jours)

- Définir le format de sortie des candidats termes (JSONL avec `term`, `score`, `frequency`, `in_vocabulary`, `uri`)
- Définir les paramètres CLI pour le mode extract (`--min-freq`, `--max-tokens`, `--lang`)
- Choisir le corpus de test de référence pour valider contre TermSuite
- Documenter les cas limites (termes d'un seul token, termes très fréquents)

### Phase 1 — Module d'extraction de base (3-5 jours)

- Implémenter la collecte des **noun chunks** via spaCy (`doc.noun_chunks`) avec filtres POS
- Filtres : longueur minimale/maximale, stopwords, ponctuation, seuil de fréquence minimale
- Comptage des occurrences et des fréquences de corpus
- Commande CLI : `--mode extract` → sortie JSONL des candidats bruts
- Tests unitaires sur corpus de référence français et anglais

### Phase 2 — Scoring C-value (3-4 jours)

- Implémenter l'algorithme C-value (Frantzi et al. 1998)
- Gérer correctement les **termes emboîtés** (*"neural network"* dans *"deep neural network"*)
- Paramètre de seuil configurable (`--cvalue-threshold`)
- Validation sur corpus biomédical et corpus physique (corpus Loterre existants)
- Comparaison quantitative sortie C-value Python vs sortie TermSuite sur les mêmes corpus

### Phase 3 — Intégration des 3 modes CLI (2-3 jours)

```bash
# Annotation seule (comportement actuel, inchangé)
loterre-annotate --mode annotate --dict P66 texte.txt

# Extraction seule
loterre-annotate --mode extract --lang fr texte.txt

# Extraction + annotation (nouveau mode combiné)
loterre-annotate --mode extract+annotate --dict P66 --lang fr texte.txt
```

En mode `extract+annotate` : les candidats C-value sont passés directement au moteur Trie existant. Le JSON de sortie enrichit chaque candidat avec `in_vocabulary: true/false` et l'URI si présent.

### Phase 4 — Détection de variantes (3-5 jours)

- **Variantes graphiques** : normalisation tirets/espaces, accents, casse
- **Variantes morphologiques** : regroupement par lemme spaCy (déjà disponible)
- **Variantes syntaxiques** : permutation N+Adj / Adj+N (critique pour le français)
- Groupement des variantes dans la sortie JSON (`canonical_form`, `variants: [...]`)

### Phase 5 — Option transformer (optionnel, 1 semaine)

- Intégrer **KeyBERT** ou **sentence-transformers** pour re-ranking des candidats
- Activable via `--extractor bert` (défaut : `--extractor cvalue`)
- Modèles recommandés : `paraphrase-multilingual-mpnet-base-v2` (fr+en), `allenai/scibert_scivocab_uncased` (anglais scientifique)
- Utile surtout sur textes courts ou termes très peu fréquents

### Phase 6 — Benchmark et évaluation (2-3 jours)

- Intégrer les métriques d'extraction dans `loterre_benchmark.py` existant
- Precision/Recall/F1 sur corpus annotés manuellement
- Comparaison directe avec TermSuite sur les mêmes corpus
- Documentation des résultats

---

## 5. Estimation des efforts

| Phase | Durée estimée | Priorité |
|-------|--------------|---------|
| Phase 0 — Conception | 2 jours | Obligatoire |
| Phase 1 — Extraction de base | 3-5 jours | Obligatoire |
| Phase 2 — C-value | 3-4 jours | Obligatoire |
| Phase 3 — Intégration CLI | 2-3 jours | Obligatoire |
| Phase 4 — Variantes | 3-5 jours | Recommandée |
| Phase 5 — Transformers | 5-7 jours | Optionnel |
| Phase 6 — Benchmark | 2-3 jours | Recommandée |
| **Total socle (phases 0-3)** | **~3 semaines** | |
| **Total complet (phases 0-6)** | **~6 semaines** | |

---

## 6. Risques et points d'attention

| Risque | Probabilité | Mitigation |
|--------|-------------|------------|
| C-value Python < TermSuite en qualité | Faible | Validation précoce sur corpus Phase 2 |
| Temps de traitement trop long sur gros corpus | Moyen | Profiling + batch processing |
| Ambiguïté des noun chunks spaCy sur textes bruités | Moyen | Filtres POS robustes + seuil fréquence |
| Conflits de format sortie extraction/annotation | Faible | Spécification format dès Phase 0 |

---

## Références

- Frantzi, K., Ananiadou, S., Mima, H. (2000). *Automatic recognition of multi-word terms: the C-value/NC-value method*. International Journal on Digital Libraries, 3(2), 115–130.
- TermSuite : https://termsuite.github.io/ / https://github.com/termsuite
- spaCy noun chunks : https://spacy.io/usage/linguistic-features#noun-chunks
- KeyBERT : https://github.com/MaartenGr/KeyBERT
- pke (Python Keyphrase Extraction, contient C-value) : https://github.com/boudinfl/pke
