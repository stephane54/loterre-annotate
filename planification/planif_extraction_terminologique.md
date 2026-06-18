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

## 3. Objectifs non fonctionnels

| Objectif | Contrainte |
|----------|------------|
| **Rapidité** | Le mode `extract` ne doit pas être significativement plus lent que le mode `annotate` actuel. NC-value et PositionRank sont O(n) ou O(n log n) — pas d'opération quadratique sur grands corpus. MiniLM embedding : ~100–300 ms/doc en CPU, acceptable en CLI. |
| **Mesure de qualité — annotation** | Gold standards existants dans `data/jsonl/` (P66_en, P66_fr, etc.) — pipeline benchmark déjà en place |
| **Mesure de qualité — extraction** | Corpus **ACTER** (Rigouts Terryn et al., LREC 2018) : FR + EN, 4 domaines techniques, ~18 900 termes annotés manuellement, format IOB. GitHub : https://github.com/AylaRT/ACTER. Métriques : Precision/Recall/F1 sur termes extraits vs gold. |

---

## 4. Architecture cible

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

### Phase 0 — Conception, spécification et upgrade modèles (3-4 jours)

**Décisions de conception actées (validées) :**

Schéma `candidate` — sortie JSONL stable entre les 3 modes (champs vocabulaire à `null` quand non applicables, pour éviter le branchement côté consommateur) :

```json
{
  "term": "spectrométrie de masse",
  "lemma": "spectrométrie de masse",
  "pattern": [
    {"pos": "NOUN", "lemma": "spectrométrie"},
    {"pos": "ADP", "lemma": "de"},
    {"pos": "NOUN", "lemma": "masse"}
  ],
  "frequency": 3,
  "score": 0.82,
  "rule": "ncvalue",
  "occurrences": [{"start": 120, "end": 145}, {"start": 980, "end": 1005}],
  "in_vocabulary": true,
  "uri": "http://data.loterre.fr/ark:/67375/...",
  "pref": "spectrométrie de masse"
}
```

- `lemma` : séquence lemmatisée complète — clé de regroupement des variantes (Phase 4)
- `pattern` : détail POS+lemme par token, même format que les dictionnaires Loterre existants — un candidat validé peut être copié tel quel comme nouvelle entrée
- Mode `annotate` : sortie `matches` inchangée à 100 % (zéro régression)
- Mode `extract` : sortie `candidates`, champs vocabulaire à `null`
- Mode `extract_annotate` : sortie `candidates`, champs vocabulaire renseignés

Paramètres CLI :

```bash
--mode {annotate,extract,extract_annotate}   # nouveau, défaut "annotate" → comportement v1.0 inchangé
--min-freq INT          # défaut 2 — seuil fréquence NC-value
--min-tokens INT        # défaut 1
--max-tokens INT        # défaut 6
--extractor {ncvalue,graph,embed,auto}   # défaut "auto"
--extractor-auto-threshold INT  # défaut 50000 tokens — bascule ncvalue/positionrank
--max-terms INT         # défaut None (illimité) — garde les N meilleurs candidats triés par score décroissant
```

`--mode extract` et `extract_annotate` ignorent `--execution-strategy` (fast/hybrid n'ont pas de sens pour l'extraction — besoin du pipeline spaCy complet POS+lemme).

Corpus de référence : **ACTER** dès la Phase 1 (pas seulement Phase 6) — domaines insuffisance cardiaque + énergie éolienne, FR+EN. Comparaison TermSuite secondaire.

Cas limites documentés :

| Cas | Risque | Traitement prévu |
|-----|--------|-------------------|
| Termes à un seul token | `log2(1) = 0` → C-value toujours nul par formule | Score de fallback par fréquence brute, pas C-value |
| Expressions très fréquentes non terminologiques ("dans cet article") | Faux positifs en tête de classement | Stopword-list dédiée, pas seulement filtre POS |
| Termes emboîtés | Calcul C-value doit connaître les sur-termes | Construire une carte de containment avant scoring |
| Corpus très court | NC-value peu fiable | Bascule automatique vers PositionRank sous le seuil |
| Casse/accents FR | Incohérence de comptage | Réutiliser `normalize_text` existant, ne pas réinventer |

**Tâches techniques :**

- **Upgrade spaCy 3.7 → 3.8** dans `requirements.txt`
- **Ajout scispaCy v0.6.x** + modèle `en_core_sci_sm` pour l'anglais scientifique
- FR : passer de `fr_core_news_sm` à `fr_core_news_lg`
- **Génération des dictionnaires EN — pipeline natif** : `scripts/build_dictionaries/build_dictionaries.py` remplace entièrement la dépendance externe à `~/app/terms_tools` (CSV vocab → JSONL pattern POS+lemme), en réutilisant `load_model()` de loterre-v9
  - Découverte en cours de route : l'ancien pipeline `terms_tools` générait les dictionnaires avec des modèles **transformers** (`en_core_web_trf`, `fr_dep_news_trf`), incohérents avec les modèles légers utilisés au runtime — le pipeline natif élimine cette incohérence en plus de supprimer la dépendance
  - Détection automatique des deux formats CSV (loterre `_fr`/`§§` vs MX `Fre`/`|`) depuis les en-têtes
  - Validé caractère pour caractère contre les dictionnaires de production existants (`long-term memory` → pattern identique avec `OP:"?"` sur le tiret)
  - Commande : `python3 scripts/build_dictionaries/build_dictionaries.py --all --lang en`
- Vérification des gold standards EN après régénération (benchmarks existants)

### Phase 0.5 — Préparation architecturale ciblée (1 jour)

Constat issu de l'analyse du code existant (`loterre_engine_v9_cli.py`, `loterre_cli.py`, `loterre_fast_path.py`) : **pas de réarchitecture complète nécessaire**, le moteur d'annotation est stable et ne doit pas être modifié. Mais deux manques bloqueraient un développement propre de l'extraction s'ils ne sont pas traités en amont :

- **Créer `src/loterre_extraction_base.py`** avec une dataclass `CandidateTerm` (`name`, `start`, `end`, `score`, `rule`, `metadata`) — évite que chaque nouveau module d'extraction réinvente sa propre structure de candidat (actuellement les matches sont des dicts ad-hoc créés à 4 endroits différents dans le moteur)
- **Centraliser le chargement spaCy** dans une fonction unique réutilisable — actuellement `load_model()` est appelé séparément dans 3 chemins d'exécution (EZS, multiprocess, single-process) ; un module d'extraction ne doit pas dupliquer ce pattern une 4ᵉ fois

**Règle à respecter pendant tout le développement v2.0** : ne pas toucher à `match_document()` ni à la stratégie 5 passes du moteur existant. Tout le nouveau code (NC-value, PositionRank, embeddings) va dans des **fichiers séparés**, avec la même frontière subprocess que celle déjà utilisée par `loterre_fast_path.py`. Un peu de duplication (normalisation de texte, dedupe) est acceptable en échange de zéro risque de régression sur le moteur d'annotation testé.

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

### Phase 5 — Scoring par embeddings Loterre (3-4 jours)

Utiliser les termes des vocabulaires Loterre existants comme référence d'embeddings pour deux objectifs sans GPU ni fine-tuning :

- **Filtrage du bruit** : calculer la similarité cosinus entre chaque candidat et le centroïde des embeddings des termes Loterre du vocabulaire cible ; éliminer les candidats trop éloignés
- **Enrichissement** : candidats à score élevé mais absents du vocabulaire → signalés comme suggestions d'ajout à Loterre

Modèle : `paraphrase-multilingual-MiniLM-L12-v2` (118 Mo, CPU, FR+EN)  
Activable via `--extractor embed` (défaut : `--extractor ncvalue`)  
Gain estimé : +5–8 % F1 sur le filtrage du bruit

### Phase 6 — Benchmark et évaluation (3-4 jours)

- Intégrer les métriques d'extraction dans `loterre_benchmark.py` existant
- **Gold standard d'extraction : corpus ACTER** (Rigouts Terryn et al., LREC 2018)
  - GitHub : [AylaRT/ACTER](https://github.com/AylaRT/ACTER) — CC BY-NC-SA 4.0
  - Langues : EN + FR (+ NL)
  - Domaines : insuffisance cardiaque, énergie éolienne, équitation, corruption
  - ~18 900 termes annotés manuellement, format IOB
  - Évaluation : Precision / Recall / F1 sur termes extraits vs gold (token-level)
- Comparaison directe avec **D-Terminer** (Rigouts Terryn, LT3/UGent) comme baseline transformer :
  - F1 de référence sur ACTER : 0.09–0.46 selon le domaine (mBERT + RNN, GPU)
  - Plafond général des méthodes transformer sur ATE : ~0.50–0.70 F1
  - Notre objectif : atteindre un F1 comparable sans GPU, en non supervisé
- Comparaison secondaire avec TermSuite sur les mêmes corpus
- Documentation des résultats par domaine et par langue

---

## 5. Estimation des efforts

| Phase | Durée estimée | Priorité |
|-------|--------------|---------|
| Phase 0 — Conception + upgrade modèles | 3-4 jours | Obligatoire |
| Phase 0.5 — Préparation architecturale ciblée | 1 jour | Obligatoire |
| Phase 1 — Extraction de base | 3-5 jours | Obligatoire |
| Phase 2 — C-value | 3-4 jours | Obligatoire |
| Phase 3 — Intégration CLI | 2-3 jours | Obligatoire |
| Phase 4 — Variantes | 3-5 jours | Recommandée |
| Phase 5 — Scoring embeddings Loterre | 3-4 jours | Recommandée |
| Phase 6 — Benchmark ACTER + D-Terminer | 3-4 jours | Recommandée |
| **Total socle (phases 0-3)** | **~3-4 semaines** | |
| **Total complet (phases 0-6)** | **~5–6 semaines** | |

---

## 6. Guide des sessions de développement

### Estimation du temps total

| Périmètre | Heures effectives |
|-----------|:-----------------:|
| Socle phases 0–3 | 45–65 h |
| Complet phases 0–6 | 90–120 h |

En rythme partiel (2–3 h/jour) : **2 à 3 mois de calendrier.**  
En rythme soutenu (5–6 h/jour) : **3 à 5 semaines.**  
Les phases 2 (NC-value) et 4 (variantes françaises) sont les plus incertaines.

### Comment démarrer une session par phase

Le fichier `CLAUDE.md` à la racine du projet est chargé automatiquement par Claude Code à chaque nouvelle conversation. Il contient les contraintes, la stack technique, et les objectifs de qualité — pas besoin de les réexpliquer.

**Un prompt court par phase suffit :**

```
Phase 0 : "On commence la Phase 0 du plan planif_extraction_terminologique.md.
           Upgrade spaCy 3.8 + scispaCy, puis régénération des dicos EN."

Phase 1 : "On commence la Phase 1 du plan planif_extraction_terminologique.md.
           Implémente le module d'extraction de base (noun chunks + filtres POS)."

Phase 2 : "On commence la Phase 2 du plan planif_extraction_terminologique.md.
           Implémente NC-value."

Phase 3 : "On commence la Phase 3 du plan planif_extraction_terminologique.md.
           Intègre les 3 modes CLI et unifie le format de sortie JSONL."

Phase 4 : "On commence la Phase 4 du plan planif_extraction_terminologique.md.
           Détection de variantes."

Phase 5 : "On commence la Phase 5 du plan planif_extraction_terminologique.md.
           Scoring embeddings MiniLM sur les termes Loterre."

Phase 6 : "On commence la Phase 6 du plan planif_extraction_terminologique.md.
           Benchmark sur ACTER, comparaison avec D-Terminer."
```

Claude relira `CLAUDE.md` et ce document de planification au démarrage de chaque session pour se repositionner sans que tu aies besoin de tout réexpliquer.

---

## 7. Risques et points d'attention

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
