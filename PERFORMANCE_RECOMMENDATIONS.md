# Propositions d’optimisation des performances

Ce document propose des optimisations concrètes pour accélérer l’exécution de `src/loterre_engine_v9_cli.py`.

## Hypothèses de chiffrage

Les gains ci-dessous sont des **estimations** basées sur des pipelines NLP Python comparables.
Ils doivent être confirmés par benchmark sur vos jeux de données (petit / moyen / gros).

- Machine cible: 8 vCPU, SSD, Python 3.11
- Corpus type: 10k à 500k lignes JSONL
- Dictionnaire: 5k à 200k entrées
- KPI principal: temps total d’exécution (wall time)
- KPI secondaires: docs/s, p95 latence doc, RSS max

## 1) Éviter de parser tout le fichier d’entrée en mémoire

**Constat**: `read_text_rows` lit tout le fichier (`Path(...).read_text`) puis fait `splitlines()`, ce qui augmente la mémoire et le temps de parsing sur de gros volumes.

**Proposition**:
- passer à un mode itératif ligne par ligne (`for line in f:`),
- traiter/annoter en flux (streaming) plutôt que construire une liste complète.

**Gains prévus**:
- **Temps total**: **+5% à +20%** (plus visible sur fichiers volumineux)
- **Mémoire pic**: **-40% à -80%**
- **Risque**: faible

## 2) Mutualiser les normalisations répétées

**Constat**: les appels à `normalize_text`/`normalize_token_list` sont nombreux et répétitifs.

**Proposition**:
- ajouter un petit cache LRU (ex: `functools.lru_cache`) sur les normalisations pures,
- pré-normaliser les formes des entrées dictionnaire une seule fois au chargement.

**Gains prévus**:
- **Temps total**: **+8% à +30%** (si répétition élevée des formes)
- **CPU**: réduction notable dans les boucles de matching
- **Risque**: faible à moyen (taille cache à borner)

## 3) Précompiler les regex utilisées dans `normalize_text`

**Constat**: des `re.sub` avec motifs littéraux sont appelés fréquemment.

**Proposition**:
- compiler les motifs supplémentaires une seule fois au niveau module,
- éviter les compilations implicites répétées.

**Gains prévus**:
- **Temps total**: **+1% à +6%**
- **CPU**: micro-gains cumulés
- **Risque**: faible

## 4) Charger spaCy en mode plus léger selon le besoin

**Constat**: le modèle spaCy peut exécuter des composants inutiles pour certaines passes.

**Proposition**:
- désactiver les composants non nécessaires (`disable=[...]`) lors de `spacy.load`,
- exécuter des chemins “fast mode” si seules tokenisation + lemmas sont nécessaires.

**Gains prévus**:
- **Temps NLP**: **+15% à +45%**
- **Temps total**: **+10% à +35%** selon la part NLP
- **Risque**: moyen (vérifier impact qualité)

## 5) Utiliser `nlp.pipe` partout avec batch tuning explicite

**Constat**: le code mentionne des batchs, mais l’efficacité dépend du bon usage systématique de `nlp.pipe`.

**Proposition**:
- centraliser le passage des textes par `nlp.pipe(texts, batch_size=..., n_process=...)`,
- exposer un réglage CLI clair pour `batch_size` et `n_process`.

**Gains prévus**:
- **Temps NLP**: **+20% à +60%**
- **Temps total**: **+15% à +50%** sur lots moyens/gros
- **Risque**: moyen (tuning dépend machine/corpus)

## 6) Réduire les conversions et allocations intermédiaires

**Constat**: certaines étapes construisent plusieurs listes/dicts temporaires (tokens plats, variantes, payloads).

**Proposition**:
- remplacer certaines listes intermédiaires par générateurs quand possible,
- réutiliser des structures préallouées dans les boucles chaudes,
- limiter les `dict` riches dans les chemins critiques (préférer tuples/slots si possible).

**Gains prévus**:
- **Temps total**: **+5% à +18%**
- **Mémoire pic**: **-10% à -35%**
- **Risque**: moyen (lisibilité/maintenance)

## 7) Optimiser le trie de séquences

**Constat**: `SeqTrie`/`TrieNode` sont déjà simples, mais peuvent être accélérés.

**Proposition**:
- trier les séquences par fréquence/longueur pour améliorer la probabilité de match long tôt,
- stocker des payloads compacts (IDs) et résoudre les métadonnées hors boucle critique,
- benchmarker une version Aho-Corasick tokenisée pour multi-match massif.

**Gains prévus**:
- **Trie optimisé**: **+5% à +20%**
- **Aho-Corasick tokenisé**: **+15% à +70%** (cas gros dictionnaire + texte dense)
- **Risque**: moyen à élevé (complexité implémentation)

## 8) Ajouter un vrai protocole de benchmark continu

**Constat**: des scripts de benchmark existent, mais pas forcément de garde-fou perf automatisé.

**Proposition**:
- fixer 2–3 scénarios de référence (petit/moyen/gros),
- mesurer `throughput docs/s`, latence p95, mémoire max,
- échouer CI si régression > seuil (ex: +10% runtime).

**Gains prévus**:
- **Gain direct runtime**: **0%**
- **Gain indirect**: évite les régressions cumulées (souvent **10% à 30%** sauvés sur 6–12 mois)
- **Risque**: faible

## 9) Prioriser les optimisations par ROI

Ordre recommandé d’implémentation:
1. streaming d’entrée + `nlp.pipe` systématique,
2. désactivation de composants spaCy non utiles,
3. cache LRU sur normalisation,
4. réduction des allocations dans boucles critiques,
5. expérimentation trie/Aho-Corasick.

## 10) Plan d’action rapide (1 à 2 jours)

- **J1 matin**: instrumenter timers par étape (I/O, NLP, matching, scoring).
- **J1 après-midi**: implémenter streaming + `nlp.pipe` + batch tuning.
- **J2 matin**: ajouter cache normalisation + regex précompilées.
- **J2 après-midi**: comparer benchmark avant/après, documenter les gains.

## Résumé chiffré (ordre d’impact attendu)

1. `nlp.pipe` + batch tuning: **+15% à +50%** total
2. spaCy allégé (`disable`): **+10% à +35%** total
3. cache normalisation: **+8% à +30%** total
4. streaming I/O: **+5% à +20%** total (+gros gain mémoire)
5. allocations intermédiaires: **+5% à +18%** total
6. trie/Aho-Corasick: **+5% à +70%** selon scénario
7. regex précompilées: **+1% à +6%** total
8. benchmark continu: **0% direct**, mais stabilise les gains

> Important: les gains ne s’additionnent pas linéairement; il faut mesurer **après chaque étape**.
