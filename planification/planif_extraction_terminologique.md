# Analyse : Intégration de l'extraction terminologique dans loterre-annotate

**Date :** 2026-06-13  
**Auteur :** Stéphane Schneider  
**Version cible :** v2.0

---

## Contexte

loterre-annotate est un **annotateur par dictionnaire** : il cherche dans un texte les termes d'un vocabulaire connu (Loterre) et renvoie les occurrences avec leurs URIs. TermSuite fait l'inverse : il **extrait des candidats termes** d'un corpus sans vocabulaire préalable. Ce sont des outils complémentaires, pas concurrents.

L'objectif est d'offrir trois modes d'utilisation :

| Sous-commande | Description |
|------|-------------|
| `annotate` | Comportement actuel — lookup dans un vocabulaire Loterre |
| `extract` | Extraction de candidats termes depuis le texte (sans vocabulaire) |
| `extract_annotate` | Extraction puis croisement avec un vocabulaire Loterre |

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
loterre_cli.py {annotate,extract,extract_annotate} ...   # sous-commande positionnelle obligatoire (voir Phase 3)
--min-freq INT          # défaut 2 — seuil fréquence NC-value
--min-tokens INT        # défaut 1
--max-tokens INT        # défaut 6
--extractor {ncvalue,graph,embed,auto}   # défaut "auto"
--extractor-auto-threshold INT  # défaut 50000 tokens — bascule ncvalue/positionrank
--max-terms INT         # défaut None (illimité) — garde les N meilleurs candidats triés par score décroissant
```

`extract` et `extract_annotate` n'ont pas de `--execution-strategy` (fast/hybrid n'ont pas de sens pour l'extraction — besoin du pipeline spaCy complet POS+lemme), c'est un paramètre propre à la sous-commande `annotate`.

Corpus de référence : **ACTER** dès la Phase 1 (pas seulement Phase 6) — domaines insuffisance cardiaque + énergie éolienne, FR+EN. Comparaison TermSuite secondaire.

Cas limites documentés :

| Cas | Risque | Traitement prévu |
|-----|--------|-------------------|
| Termes à un seul token | `log2(1) = 0` → C-value toujours nul par formule | Score de fallback par fréquence brute, pas C-value |
| Expressions très fréquentes non terminologiques ("dans cet article") | Faux positifs en tête de classement | Stopword-list dédiée, pas seulement filtre POS |
| Termes emboîtés | Calcul C-value doit connaître les sur-termes | Construire une carte de containment avant scoring |
| Corpus très court | NC-value peu fiable | Bascule automatique vers PositionRank sous le seuil |
| Casse/accents FR | Incohérence de comptage | Réutiliser `normalize_text` existant, ne pas réinventer |

**Tâches techniques — statut réel après tests (2026-06-18) :**

| Tâche prévue | Décision finale | Pourquoi |
|--------------|-----------------|----------|
| Upgrade spaCy 3.7 → 3.8 | **Abandonné — reste en 3.7.x** | `en_core_sci_sm` 0.5.4 a une dépendance pip dure `spacy<3.8.0` dans ses propres métadonnées (pas seulement la lib wrapper scispaCy) ; pas de bénéfice à monter en 3.8 sans ce modèle |
| Ajout scispaCy `en_core_sci_sm` comme modèle EN par défaut | **Testé et rejeté** | Sur P66 (vocabulaire multidisciplinaire, pas biomédical) : 26 % de désaccords lemme/POS vs 18 % avec `en_core_web_sm`, soit −8 pts de F1 mesurés. scispaCy reste disponible mais n'est plus le défaut dans `resources/spacy_models.yaml` |
| FR : `fr_core_news_sm` → `fr_core_news_lg` | **Non retenu** | Pas testé séparément suite au rejet scispaCy — `fr_core_news_sm` reste le défaut runtime, cohérent avec le retour en arrière EN |
| Génération des dictionnaires — pipeline natif | **Fait, mais modèles différents du runtime (volontairement)** | `scripts/build_dictionaries/build_dictionaries.py` remplace la dépendance externe `~/app/terms_tools`, mais reproduit les modèles **transformers** historiques (`en_core_web_trf`/`fr_dep_news_trf`, voir `GENERATION_MODELS` dans le script) plutôt que `load_model()` — un essai de faire coïncider génération/runtime avait dégradé le F1 (voir `planification/journal_versions.md`) |
| Vérification des gold standards EN après régénération | **Validée sur 6/9 vocabs** | Régénéré et comparé : `27X_en` 2198/2198, `3JP_en` 5746/5746, `8HQ_en` 486/486, `B9M_en` 739/739, `BVM_en` 12143/12143 identiques à 100% (pattern+pref) ; `9SD_en` 12514/12515 (1 différence : acronyme `AND`/Andorre, ambiguïté CCONJ/PROPN sans contexte). **Test qualité confirmé** : F1 strictement identique au baseline sur les 6 vocabs (`27X` 74.7%, `3JP` 74.7%, `8HQ` 89.5%, `9SD` 94.4%, `B9M` 96.0%, `BVM` 85.0%). `JVR` (très gros vocab, 30k lignes CSV), `P66`, `QX8` (EN) et le lot FR restent en régénération arrière-plan — même méthode à appliquer à leur tour. `dictionary/` restauré à l'original après test (pas d'adoption partielle pour rester cohérent tant que le lot complet n'est pas validé) |

**Travaux non prévus au plan, réalisés en cours de route (bugs bloquants découverts pendant les tests) :**
- Fix moteur `dedupe()` : un terme composé ne perd plus face à ses propres fragments courts en cas de chevauchement par containment (ex. *"post-encoding stress effect"* vs *"encoding"* + *"stress"* séparés)
- Fix sortie `--silent` : champ `text` manquant, cassait le pipeline de rendu HTML et le convertisseur prédiction→gold
- Suppression de BOM UTF-8 sur 10 scripts shell
- **Baseline de non-régression établi** : `tests/baselines/annotation_baseline_v1.0.0.json` — F1 global 83,9 % sur 16 combinaisons vocab/langue (mode annotate v1.0, à utiliser comme référence pour détecter toute régression future, y compris pendant le développement v2.0)

### Phase 0.5 — Préparation architecturale ciblée — **Terminée (2026-06-18)**

Constat issu de l'analyse du code existant (`loterre_engine_v9_cli.py`, `loterre_cli.py`, `loterre_fast_path.py`) : **pas de réarchitecture complète nécessaire**, le moteur d'annotation est stable et ne doit pas être modifié.

- ✅ **`src/loterre_extraction_base.py` créé** avec la dataclass `CandidateTerm` (`term`, `lemma`, `pattern`, `frequency`, `score`, `rule`, `occurrences`, `in_vocabulary`, `uri`, `pref`) — champs alignés exactement sur le schéma JSONL `candidate` décidé en Phase 0, `to_dict()` validé
- ✅ **Chargement spaCy centralisé** via `get_nlp(lang)` — wrapper `lru_cache` autour de `load_model()` existant (pas de réimplémentation : `_worker_init` du multiprocess garde son propre chargement par process, c'est nécessaire ; EZS et single-process restent inchangés). `get_nlp()` évite qu'un futur mode `extract_annotate` charge le modèle deux fois (extraction + annotation) dans le même process — testé : deuxième appel retourne la même instance

**Règle à respecter pendant tout le développement v2.0** : ne pas toucher à `match_document()` ni à la stratégie 5 passes du moteur existant. Tout le nouveau code (NC-value, PositionRank, embeddings) va dans des **fichiers séparés**, avec la même frontière subprocess que celle déjà utilisée par `loterre_fast_path.py`. Un peu de duplication (normalisation de texte, dedupe) est acceptable en échange de zéro risque de régression sur le moteur d'annotation testé.

### Phase 1 — Module d'extraction de base — **Terminée (2026-06-18)**

- ✅ `src/loterre_extract_cli.py` — collecte des **noun chunks** via `get_nlp(lang, parser=True)` (`doc.noun_chunks` exige le parser, désactivé par défaut pour l'annotateur — voir Phase 0.5)
- ✅ Filtres : `clean_chunk_span()` retire les tokens non lexicaux en bord de chunk (déterminants, ponctuation…), `is_valid_candidate()` filtre par longueur min/max, présence de POS de contenu (NOUN/PROPN/ADJ), stopwords, ponctuation
- ✅ Comptage des occurrences et fréquences sur l'ensemble du corpus (pas par document)
- ✅ CLI autonome (`--text`, `--lang`, `--min-tokens`, `--max-tokens`, `--min-freq`, `--max-terms`, `--out`, `--silent`) — pas encore branché sur `--mode` de `loterre_cli.py` (prévu Phase 3)
- ✅ Test smoke `tests/smoke/test_extract_cli.sh` validé sur P66_en (84 candidats) et P66_fr (10 candidats) — schéma `CandidateTerm` correct, seuil `--min-freq` respecté
- Le champ `score` vaut la fréquence brute pour l'instant (`rule: "noun_chunk"`) — remplacé par le score NC-value en Phase 2
- Exemples de candidats pertinents extraits sur P66_en : *controlled memory assessment*, *scientific discourse*, *selective attention*, *source memory* (correspondent à de vrais termes du vocabulaire Loterre P66)

### Phase 2 — Scoring C-value — **Cœur de l'algorithme terminé (2026-06-18)**

- ✅ `src/loterre_cvalue.py` — algorithme C-value (Frantzi et al. 1998) implémenté
- ✅ **Termes emboîtés gérés correctement** : `build_containment_map()` détecte les sous-séquences de lemmes contenues dans des candidats plus longs. Validé mathématiquement sur P66_en : *"controlled memories"* (freq=48, contenu dans *"controlled memory assessment"* freq=52, P(a)=1) → C-value = log2(2)×(48-52/1) = **-4.0**, conforme à la formule
- ✅ Cas limite mono-token (Phase 0) traité : `single_token_score()` (repli fréquence normalisée) au lieu de C-value (toujours nul, log2(1)=0) — `rule="freq_single_token"` vs `rule="cvalue"`
- ✅ Seuil configurable `--cvalue-threshold` sur `loterre_extract_cli.py`
- ✅ Test smoke `tests/smoke/test_cvalue.sh` : vérifie le calcul exact sur un cas emboîté connu, le bon usage de la règle de repli mono-token, le tri par score, et le filtre de seuil
- ⏸️ **Non fait** : extension contexte nominal (NC-value complet) — nécessiterait le suivi des positions de tokens (`CandidateTerm` n'a que des offsets caractères actuellement) ; C-value seul donne déjà des résultats pertinents (voir exemple P66_en : *"controlled memory assessment"* score=82.4 domine largement les mots génériques fréquents comme *"study"*/*"protocol"*, score=1.0)
- ⏸️ **Non fait** : comparaison quantitative vs TermSuite — priorité secondaire (cf. décision Phase 0 : ACTER/D-Terminer sont les références principales, TermSuite secondaire)

### Complément Phase 2 — PositionRank + bascule automatique — **Terminé (2026-06-19)**

C-value a besoin d'un grand volume de texte pour être fiable (~50 000 tokens minimum, voir `planification/analyse_benchmarks_extraction.md` §Dépendance au volume) — sur un corpus court, ses statistiques de fréquence/emboîtement sont trop bruitées. Implémentation de l'alternative prévue dès la conception (`--extractor {ncvalue,graph,embed,auto}`, Phase 0) :

- ✅ `src/loterre_positionrank.py` — PositionRank (Florescu & Caragea 2017) en Python pur, sans dépendance graphe externe (pas de `networkx`) : graphe de co-occurrence pondéré entre mots de contenu (fenêtre configurable, défaut 4), score de position initial (`1/(index+1)`, les mots précoces comptent plus), PageRank biaisé par itération de puissance. Validé sur un exemple synthétique : un mot fréquent et précoce domine un mot rare et tardif
- ✅ `extract_candidates()` capture le graphe de co-occurrence et le nombre total de tokens en un seul passage spaCy (pas de retraitement du corpus selon l'extracteur choisi ensuite)
- ✅ `--extractor {ncvalue,graph,auto}` (défaut `auto`) et `--extractor-auto-threshold` (défaut `50000`) sur `loterre_extract_cli.py` — `auto` bascule sur `graph` (PositionRank) si le corpus a moins de tokens que le seuil, sinon `ncvalue` (C-value)
- ✅ Champs `total_tokens`/`extractor` ajoutés au payload JSON de sortie, pour que l'utilisateur voie quel algorithme a été utilisé
- ✅ Test smoke `tests/smoke/test_positionrank.sh` : bascule auto vérifiée dans les deux sens (seuil par défaut → graph sur P66_en à 2985 tokens ; seuil abaissé → ncvalue), `--extractor graph` explicite validé (scores positifs, triés)
- `--extractor embed` (scoring par embeddings, Phase 5 du plan) reste non implémenté — seuls `ncvalue`/`graph`/`auto` existent pour l'instant

### Phase 3 — Intégration des 3 modes CLI — **Terminée (2026-06-18)**

`--mode {annotate,extract,extract_annotate}` ajouté à `loterre_cli.py` dans un premier temps (nom canonique avec underscore, pas `+`, pour rester un identifiant argparse simple), puis **remplacé par des sous-commandes positionnelles** (`annotate`/`extract`/`extract_annotate`, voir §CLI ci-dessous) le 2026-06-19 pour plus de clarté (chaque sous-commande n'affiche que ses propres paramètres dans `--help`, au lieu d'une liste à plat avec des params ignorés selon le mode) :

```bash
# Annotation seule (comportement v1.0, inchangé — 0 régression vérifiée par diff)
python3 src/loterre_cli.py annotate --dict-id P66_en --profile term_recall --text texte.jsonl --silent

# Extraction seule (frontière subprocess vers loterre_extract_cli.py)
python3 src/loterre_cli.py extract --lang en --text texte.jsonl --silent

# Extraction + annotation (croisement par span exact)
python3 src/loterre_cli.py extract_annotate --dict-id P66_en --profile term_recall --text texte.jsonl --silent
```

- ✅ `run_extraction_subprocess()` réutilise le pattern subprocess existant (comme `run_engine_full_json()`)
- ✅ `extract_annotate` : exécute extraction + annotation sur le même texte, puis `cross_reference_candidates()` enrichit chaque candidat avec `in_vocabulary`/`uri`/`pref` — réutilise le moteur Trie existant tel quel via son JSON de sortie, aucune réimplémentation du lookup
- 🐛 **Bug trouvé et corrigé pendant les tests** : le croisement initial utilisait un simple chevauchement de span, ce qui attribuait à tort un candidat composé (*"controlled memory assessment"*) au `pref` d'un sous-terme qu'il contient (*"memory"*). Puis un second bug, plus subtil : les offsets caractères étant locaux à chaque document du corpus, deux occurrences de documents différents pouvaient partager le même `(start, end)` par coïncidence. Corrigé en ajoutant `doc_id` à `Occurrence` et en croisant par triplet `(doc_id, start, end)` exact
- ✅ Tests de régression `tests/smoke/test_extract_annotate_cli.sh` : `annotate` identique au comportement v1.0 (diff hors timings), `extract` fonctionnel via la CLI principale, `extract_annotate` sans aucun faux croisement (62 reconnus, 22 absents, 0 erreur)

**Refonte CLI en sous-commandes positionnelles — Terminée (2026-06-19)** : `--mode` (flag optionnel à plat) remplacé par une sous-commande obligatoire en position 1 (`argparse.add_subparsers(dest="mode", required=True)`), chaque sous-commande déclarant uniquement ses propres paramètres. Contrainte respectée : `--dict-id`/`--profile`/`--lang` restent optionnels au niveau argparse (pas `required=True`) car ils peuvent être fournis via `--config` YAML à la place (voir `resolve_effective_params()`). Pour éviter de régresser le coût de démarrage du mode `--execution-strategy fast` (qui ne doit pas charger spaCy), les paramètres d'extraction sont dupliqués localement dans `loterre_cli.py` (`_add_extraction_args()`) plutôt qu'importés depuis `loterre_extract_cli.py` — un import aurait chargé spaCy au niveau module, mesuré à ~1.3s, dans tous les appels CLI y compris ceux qui n'en ont pas besoin. Tous les appelants internes (tests smoke, `scripts/evaluation/run_eval.sh`, `scripts/benchmark/benchmark_fast_path.sh`, `src/loterre_benchmark.py`) mis à jour vers la nouvelle syntaxe.
- 🐛 **Bug pré-existant découvert et corrigé en cours de route** (sans lien avec la refonte CLI) : `tests/smoke/test_annotate_cli.sh` pipait `cat fichier.jsonl | python3 ... --config ...` alors que le `--config` fournit déjà `text:` — le moteur ne lisait jamais stdin, donc `cat` recevait SIGPIPE (exit 141) dès la 2ᵉ itération de la boucle, et `pipefail` arrêtait silencieusement le test après un seul vocabulaire sur 16. Corrigé en supprimant le pipe `cat` redondant.

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
