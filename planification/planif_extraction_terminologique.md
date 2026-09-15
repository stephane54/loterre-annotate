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
| **Rapidité** | Le mode `extract` ne doit pas être significativement plus lent que le mode `annotate` actuel. PositionRank est O(n) ou O(n log n). MiniLM embedding : ~100–300 ms/doc en CPU, acceptable en CLI. **Hypothèse initiale corrigée le 2026-09-10** : cette ligne affirmait à tort que NC-value l'était aussi ("pas d'opération quadratique sur grands corpus") — en réalité `build_containment_map()` (`loterre_cvalue.py`) est **O(n²)** sur le nombre de candidats (double boucle explicite), découvert en mesurant le coût de `--all-candidate-patterns` sur un gros corpus (12s→66s, ×5,4, ACTER htfl ~16k candidats — voir `planification/analyse_benchmarks_extraction.md`, entrée 2026-09-10). Resté praticable jusque-là uniquement parce que le volume de candidats était resté modeste ; devient le facteur limitant dès qu'on augmente ce volume (grammaire de motifs étendue, ou simplement un très gros corpus). Pas corrigé dans le code à ce jour — connu et documenté, pas résolu. |
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
--min-freq INT          # défaut 3 — seuil fréquence NC-value
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

### Phase 4 — Détection de variantes — **Terminée (2026-06-23)**

Demande explicite : un mécanisme à motivation linguistique, en reprenant les règles par langue de **TermSuite** (CNRS/TTC, dépôt `termsuite-resources`, Apache 2.0).

- ✅ **Recherche TermSuite préalable** : lecture directe de `{fr,en}-variants.yaml` (~450 règles/langue, patterns POS + condition position-à-position : égalité, stem, `deriv()`, `prefix()`, `synonym()`, décomposition de composé). Taxonomie réelle : graphique (édition/casse/accents), morphologique (composés à tiret, préfixe, synonymie), syntaxique (insertion/expansion, permutation, réduction N N↔N P N, alternance dérivationnelle N+Adj↔N+Prep+N).
- ✅ **Généralisation plutôt que réplication exhaustive** (~450 règles/langue disproportionné, contraire à la contrainte "pas de ressource massive") — 6 mécanismes structurels dans `src/loterre_variants.py`, chaque candidat regroupé par UNE seule passe (ordre du plus fiable au plus permissif) :

  | variant_type | Mécanisme | Généralise (familles TermSuite) |
  |---|---|---|
  | `morph_inflection` | Même séquence de lemmes (déjà disponible, `CandidateTerm.lemma`) | inflexion |
  | `graphical` | Clé normalisée accents/casse/tirets/espaces sur les lemmes (acronymes tout-capitales exclus) | composés à tiret/espace |
  | `morph_prefix` | Lemmes identiques sauf un token lié par un préfixe d'une petite liste par langue (longueur de radical minimale) | `AN-prefAN`/`NA-NprefA` |
  | `syn_expansion` | Squelette de contenu (NOUN/PROPN/ADJ/VERB, mots-outils retirés) sous-séquence contiguë de l'autre, **ou** squelette identique avec mot-outil différent | `S-Ed/S-Eg/S-I/S-PI/S-R2` (couvre aussi N N↔N de/of N) |
  | `syn_permutation` | Même multiset de lemmes de contenu, ordre différent | `S-P` |
  | `morph_derivation` | Squelette de contenu identique sauf une position adjectif/nom, liée par les tables de dérivation TermSuite vendorisées | `S-PID-NA-P`/`S-R2D-NN` (alternance N+Adj↔N+Prep+N) |

  Synonymie explicitement **hors scope** (TermSuite la traite à part, `SemanticGatherer` — relation différente d'une variante de forme).
- ✅ **Tables de dérivation vendorisées** : `resources/termsuite_morphology/{fr,en}/{suffix-derivation-bank,suppletives-bank}.txt`, récupérées telles quelles depuis `termsuite-resources` (Apache 2.0, CNRS 2015), en-tête d'attribution ajouté. FR : 303 règles de suffixe + 319 lignes de classes supplétives. EN : 17 règles de suffixe seulement (pas de classes supplétives curées côté anglais), confirmant que cette alternance est nettement plus productive en français.
- ✅ **Sortie additive** : deux champs optionnels sur `CandidateTerm` (`canonical_form`, `variant_type`), `candidates` reste une liste plate — aucun changement de comportement existant (`cross_reference_candidates()`, tri/troncature `--max-terms`, etc. inchangés). **Option CLI explicite `--detect-variants`** (défaut désactivé, décision utilisateur) sur `loterre_extract_cli.py` et les sous-commandes `extract`/`extract_annotate` de `loterre_cli.py`.
- 🐛 **Quatre bugs trouvés et corrigés pendant la validation** (sur X64/P66/corpus paléoclimatologie réel) :
  1. **Faux regroupement par transitivité** : sous-séquence/préfixe/dérivation ne sont PAS des relations d'équivalence — un regroupement par composantes connexes (union-find) faisait dériver un cluster entier à travers des intermédiaires sans relation directe entre les extrêmes (ex. *"semantic memory"* groupé à tort sous *"controlled memory assessment"*, reliés seulement via une chaîne de candidats partageant juste le mot *"memory"*). Corrigé par une affectation directe sans transitivité (`_greedy_assign_from_adjacency` : traite les candidats du plus canonique au moins canonique, chacun ne réclame que ses voisins **directement** vérifiés).
  2. **Gérondifs anglais mal étiquetés VERB** : spaCy tague parfois en VERB des modificateurs en *-ing* utilisés comme nom composé (*"spacing effect"*, *"sandwich effect"* — "spacing"/"sandwich" tagués VERB), les faisant disparaître à tort du squelette de contenu (qui ne gardait que NOUN/PROPN/ADJ) et coïncider artificiellement. Corrigé en ajoutant VERB aux POS de contenu (le candidat a déjà passé le filtre noun-chunk, un VERB à l'intérieur est presque toujours un mot de contenu mal étiqueté, pas un vrai verbe).
  3. **Dérivation N↔N et classes supplétives trop permissives** : les règles N↔N de la table TermSuite (nom déverbal, ex. EN *"modeling"*/*"model"*, *"processing"*/*"process"*) et les classes supplétives (FR, ex. *"psychologie"*/*"esprit"*, *"calcul"*/*"mesure"*) reliaient des concepts trop souvent distincts. Corrigé : `morph_derivation` restreint aux paires inter-catégories A↔N ; classes supplétives retirées (ce fichier sert chez TermSuite à décomposer des formes combinantes à l'intérieur d'un composé, pas à déclarer deux mots entiers synonymes).
  4. **Préfixe court coïncident** (*"age"*/*"images"*, "im"+"age") et **acronyme confondu avec un homographe** (*"GRACE"* nom de mission / *"grâce"* mot courant, la casse "normalisée" les faisant coïncider). Corrigés par une longueur de radical minimale (`morph_prefix`) et une exception pour les séquences tout-capitales (`graphical`).
  Limite résiduelle acceptée (non résolue, documentée) : `morph_prefix` reste un faux positif occasionnel sur des mots latins où le "préfixe" est historique mais plus séparable synchroniquement (ex. *"information"*/*"formation"*, *"propositions"*/*"position"*) — nécessiterait un vrai lexique de dérivation pour trancher, hors contrainte "pas de ressource lourde".
- ✅ **Validation sur 3 profils de vocabulaire distincts** (composition mono-mot vs multi-mots) :

  | Corpus | Vocabulaire | % multi-mots | Candidats | Groupés | Détail |
  |---|---|---:|---:|---:|---|
  | X64 (EN) | X64 | 38% | 1232 | 367 (29.8%) | syn_expansion 164, morph_inflection 198, morph_prefix 5 |
  | X64 (FR) | X64 | 42% | 2427 | 792 (32.6%) | syn_expansion 324, morph_inflection 447, morph_prefix 14, graphical 5, morph_derivation 2 |
  | P66 (EN) | P66 | 89% | 203 | 36 (17.7%) | syn_expansion 35, morph_inflection 1 |
  | P66 (FR) | P66 | — | 84 | 17 (20.2%) | syn_expansion 13, morph_inflection 4 |
  | Paléoclimatologie (échantillon 794 docs réels) | QX8 | 49% | 2322 | 875 (37.7%) | syn_expansion 635, morph_inflection 237, morph_prefix 3 |

  Échantillons inspectés manuellement par catégorie sur chaque corpus (comme pour la validation du tri plus proche voisin en Phase 5) — propres après les 4 corrections ci-dessus.
- ✅ **Performance** : 794 documents réels (corpus paléoclimatologie, extrapolé ~70 Mo/17 499 docs au total) traités en 44s avec `--detect-variants` — pas de ralentissement notable, conforme à la contrainte "extract pas significativement plus lent qu'annotate".
- ✅ Test smoke `tests/smoke/test_variants.sh` : un cas construit à la main par catégorie + test de bout en bout (additif, zéro régression sans le flag).
- ⏸️ **Non fait, documenté comme limitation acceptée** : décomposition de composés agglutinés/à tiret au sens des règles `M-S-NN`/`M-I-*` de TermSuite (ex. EN "windmill"↔"wind mill" — la graphique couvre déjà ce cas via la clé normalisée tirets/espaces, qui suffit en pratique) ; synonymie (hors scope, relation différente).

### Phase 5 — Scoring par embeddings Loterre — **Terminée (2026-06-23)**

Déclenchée directement par le diagnostic X64 (voir Phase 2/journal) : C-value et PositionRank ne distinguent pas "fréquent" de "spécifique au domaine", et remontent des locutions méta-discursives au-dessus des vrais termes sur un corpus académique générique.

- ✅ `src/loterre_embed.py` — `get_embed_model()` (chargement paresseux et caché de `paraphrase-multilingual-MiniLM-L12-v2` via `sentence-transformers`), `load_vocabulary_terms()` (lit le dictionnaire JSONL cible, déduplique par `id`), `embed_vocabulary_terms()` (matrice normalisée, un vecteur par terme), `score_candidates_embed()` (similarité cosinus candidat ↔ **terme le plus proche du vocabulaire** — `max`, pas moyenne — `rule="embed"`)
- ✅ `--extractor embed` ajouté aux choix existants (`ncvalue`/`graph`/`auto`) ; nouveau `--dict` (chemin du dictionnaire cible, requis avec `embed`) et `--embed-threshold` (filtre par score minimal) sur `loterre_extract_cli.py` et les sous-commandes `extract`/`extract_annotate` de `loterre_cli.py`. `auto` ne bascule jamais vers `embed` (il faut le demander explicitement — nécessite un dictionnaire, contrairement à ncvalue/graph)
- ✅ **Enrichissement** : `CandidateTerm.enrichment_suggestion` (nouveau champ) — posé à `True` dans `run_extract_annotate_mode()` (après `cross_reference_candidates()`) pour les candidats absents du vocabulaire (`in_vocabulary=False`) avec score ≥ `--enrichment-threshold` (défaut **0.95**, voir révision ci-dessous)
- ✅ **Validation empirique sur X64** (le cas qui a motivé cette phase) : top 20 par score, candidats reconnus dans le vocabulaire —

  | | C-value | PositionRank | embed (centroïde, min-freq≥10) | **embed (plus proche voisin, min-freq défaut 2)** |
  |---|---|---|---|---|
  | EN | 7/20 | 9/20 | 13/20 | **20/20** |
  | FR | 0/20 (4/20 après fix élision) | 0/20 | 9-10/20 | **20/20** |

  Avec de vrais termes en tête de classement (EN : *semiotics, linguistics, philology, lexicon* ; FR : *sémantique, créole, langue, anglais, énoncés*) — comparé à *"one hand"*/*"l'auteur"* en tête avec C-value.
- 🔄 **Révision (2026-06-23, suite) : centroïde → plus proche voisin (max)**. Diagnostic du pourquoi `embed` remontait beaucoup de termes simples sur X64 : le vocabulaire est composé à 58-61% de concepts à un seul mot (noms de langues/ethnies, ex. X64 est un vocabulaire de type Ethnologue) — un centroïde unique (moyenne) brouille cette diversité et favorise mécaniquement les candidats courts. `embed_vocabulary_terms()` encode désormais chaque terme du vocabulaire séparément ; `score_candidates_embed()` calcule la similarité au **max** sur toute la matrice, pas à la moyenne. Résultat : passage de 13/20 (EN) et 9-10/20 (FR) à **20/20 dans les deux langues**, et ceci **sans avoir besoin de relever `--min-freq`** (le réglage 5-10 nécessaire avec le centroïde n'est plus requis). Détail dans `analyse_benchmarks_extraction.md`, entrée du 2026-06-23 (plus proche voisin).
- 🐛 **Limite résiduelle, distincte de la précédente** : le passage au plus proche voisin résout le problème de classement (top-N) mais PAS le filtrage par seuil — au `--min-freq` par défaut (2), du bruit court/peu fréquent (*"era"*, *"de"*, *"co"*, *"pas"*, un nom propre cité) obtient désormais des scores 0.93-0.96, dans la même plage que de vrais candidats d'enrichissement légitimes. **`--enrichment-threshold` recalibré empiriquement de 0.5 à 0.95** après test de plusieurs seuils (0.5/0.8/0.9/0.95/0.98/0.99) sur X64 : à l'ancien défaut 0.5, 77% des candidats (1856/2406) étaient signalés comme suggestions d'enrichissement, bruit inclus ; à 0.95 la liste reste raisonnable, à 0.98-0.99 elle devient courte et quasi sans bruit (phonetics, poetics, linguistics, semiotics, sociolinguistics, data...). Le `--min-freq` existant reste recommandé en complément sur gros corpus.
- Modèle : `paraphrase-multilingual-MiniLM-L12-v2` (118 Mo, CPU, FR+EN), `sentence-transformers` ajouté à `requirements.txt`. Cible Makefile `models-embed` pour le pré-télécharger.
- Test smoke : `tests/smoke/test_embed.sh` (erreur claire sans `--dict`, tri par score, filtre par seuil — seuil de test relevé de 0.5 à 0.8 car le plus proche voisin donne des scores systématiquement plus hauts que l'ancien centroïde).

### Phase 6 — Benchmark ACTER — **Terminée (2026-06-23)**

- ✅ **Gold standard d'extraction : corpus ACTER** (Rigouts Terryn et al., LREC 2018 / LRE 2020)
  - GitHub : [AylaRT/ACTER](https://github.com/AylaRT/ACTER) — CC BY-NC-SA 4.0, v1.5
  - Langues : **EN + FR uniquement** (NL ignoré, hors contrainte du projet)
  - 4 domaines : `corp` (corruption), `equi` (équitation), `htfl` (insuffisance cardiaque), `wind` (énergie éolienne)
  - Pas committé dans le repo (73 Mo, licence à part) — cloné à la demande dans `corpus_acter/` (`make corpus-acter`, gitignoré)
- ✅ **Nouveau script `scripts/evaluation/acter_eval.py`** : la tokenisation gold (LeTs Preprocess) est differente SpaCy — les tokens gold sont réalignés sur des offsets caractères dans le texte brut par marche séquentielle (`align_gold_tokens()`), puis comparés au niveau caractère (aucune dépendance à un tokeniseur commun). Évaluation **token-level** (protocole ACTER), sans entités nommées.
  - `--extractor embed` exclu de la comparaison "à froid" principale : nécessite un vocabulaire Loterre cible, qu'ACTER n'a pas — extraction "à froid" comme D-Terminer/TermSuite. Variante expérimentale semi-supervisée ajoutée à part (voir plus bas).
  - 🐛 **Piège trouvé en validant** : comparer l'ensemble brut des candidats donnait des scores *identiques* entre `ncvalue` et `graph` — logique, ils partagent la même extraction noun-chunk en amont, seul leur **classement** diffère. Corrigé en coupant au top-N (N = nombre de termes gold uniques du domaine) avant de scorer, pour comparer le classement et non l'ensemble brut.
  - 🐛 **`--min-freq` par défaut (2) trop strict pour ACTER** : ces corpus de domaine restreint contiennent énormément de termes spécifiques à occurrence unique, éliminés avant même le scoring. `--min-freq 1` recommandé (et utilisé par `make benchmark-acter`) — sans ce changement, le nombre de candidats bruts était parfois *inférieur* au nombre de termes gold, rendant la coupure top-N sans effet.
- ✅ **Résultats mesurés** (`--min-freq 1`, top-N par domaine, sans NE) :

  | Domaine | Lang | Docs | ncvalue F1 | graph (PositionRank) F1 |
  |---|---|---:|---:|---:|
  | corp | en | 12 | 0.34 | 0.33 |
  | corp | fr | 12 | 0.35 | 0.34 |
  | equi | en | 34 | 0.36 | **0.58** |
  | equi | fr | 78 | 0.28 | **0.54** |
  | htfl | en | 190 | 0.53 | **0.55** |
  | htfl | fr | 210 | 0.41 | **0.51** |
  | wind | en | 5 | 0.44 | **0.52** |
  | wind | fr | 2 | 0.28 | **0.50** |
  | **TOTAL** | | | **0.391** | **0.496** |

  PositionRank devance C-value sur les 8 combinaisons domaine/langue, parfois largement (equi : +0.22 à +0.26 F1). **F1 global 0.496 sans GPU, sans fine-tuning, en Python pur** — au sommet de la fourchette D-Terminer (mBERT+RNN, GPU) documentée en CLAUDE.md (0.32–0.50) et dans ce document (0.09–0.46 selon domaine) ; C-value (0.391) reste dans la fourchette basse-moyenne.
- ✅ **Variante expérimentale : `embed` semi-supervisé** (ajoutée sur demande, après le benchmark principal) — la moitié des termes gold d'un domaine sert de vocabulaire de référence, l'autre moitié ("held-out", jamais montrée au système) est l'objectif à retrouver. **Résultat initial (centroïde, 8 combinaisons) : F1 = 0.306** — *moins bon* que C-value (0.391) et PositionRank (0.496) à froid, même avec la moitié des réponses données.
  **Revalidé le 2026-06-23 après le passage centroïde → plus proche voisin** (même changement que ci-dessus en Phase 5) : `F1 = 0.364` (P=0.728, R=0.243, tp=9287/fp=3477/fn=28930, micro-moyenne sur les 8 combinaisons) — **amélioration nette sur précision ET rappel** (P : 0.461→0.728, R : 0.229→0.243) par rapport au centroïde. Reste *en dessous* de C-value (0.391) et nettement sous PositionRank (0.496) à froid, mais l'écart se réduit. Confirme que le plus proche voisin généralise mieux que le centroïde même sur un vocabulaire de référence artificiellement restreint (sous-ensemble du même domaine) — pas seulement sur un vocabulaire Loterre établi de grande taille comme X64. Détail par domaine dans `acter_results_embed_seeded.json`/`acter_results.md`. Reste une comparaison non légitime à froid (le système voit une partie de la réponse) — indicatif, pas un score de référence.
- ⏸️ **Non fait** : comparaison TermSuite (secondaire, pas prioritaire — D-Terminer déjà comparable)
- `make corpus-acter` (clone), `make benchmark-acter` (lance l'évaluation, écrit `benchmark_results/acter/acter_results.{json,md}` + variante embed dans `acter_results_embed_seeded.json`)

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

## 8. Réflexion — améliorer le rappel `embed` sur ressources restreintes *(ouverte le 2026-09-04, reprise et avancée le 2026-09-07 — signal structurel implémenté et mesuré, voir ci-dessous ; suite du fil sur la génération de candidats en §9)*

**Point de départ** : suite au recadrage produit "l'objectif principal est la mise à jour de ressource" (donc un vocabulaire cible existe toujours — voir `CLAUDE.md` §Objectif produit principal), le choix par défaut de `--extractor embed` pour `extract_annotate` a été confirmé pertinent. Mais son profil mesuré sur ACTER (précision correcte 0.55–0.85, **rappel bas 0.17–0.34** sur les termes jamais vus) pose la question : comment améliorer ce rappel sans violer les contraintes projet (CPU, pas de fine-tuning, pas de modèle massif) ?

**Pistes explorées dans cette session, dans l'ordre** :

1. **Diagnostic générique de "qualité" du vocabulaire cible** (densité interne, scission seed/held-out sur le vocabulaire seul) — **testé et invalidé** : le vocabulaire ACTER `wind` est le plus dense de tous les cas testés (médiane 0.874, au-dessus de X64 à 0.828) et donne pourtant le pire F1 réel (0.286). Ni la densité ni la taille ne discriminent les cas qui marchent des cas qui échouent (voir `docs/README.md` §5.4 et `planification/analyse_benchmarks_extraction.md`). **Scripts créés puis supprimés** (`vocab_quality_check.py`/`_all.py`) — ne pas les recréer sans une nouvelle hypothèse testable, celle-ci a échoué empiriquement.
2. **Régénération native des dictionnaires** (`build_dictionaries.py`) pour réduire l'écart lemme/POS runtime/génération — **écartée** : le script utilise déjà volontairement des modèles différents du runtime (`en_core_web_trf`/`fr_dep_news_trf`), un essai antérieur de les faire coïncider a dégradé le F1 (décision déjà tranchée, voir §4 ci-dessus ligne ~195 et `CLAUDE.md`). Sans rapport direct avec le rappel `embed` de toute façon.
3. **Enrichir le seed avec une ressource connexe du domaine** (autres vocabulaires Loterre du registre / thésaurus externes type MeSH-AGROVOC-Eurovoc / extraction `ncvalue`/`graph` sur corpus domaine pour élargir le seed) — **pas encore tranché entre les 3 variantes**, question posée à l'utilisateur sans réponse ferme (a répondu "Other" puis a réorienté vers la piste 4). Risque identifié : dilution de la précision (bruit hors-domaine) contre gain de rappel espéré — à valider empiriquement avant tout choix.
4. **Rendre le modèle d'embedding moins sensible à l'OOV** (modèle plus robuste ou fine-tuning domaine) — **écartée d'emblée** : viole directement les contraintes non négociables du projet (pas de fine-tuning, pas de modèle massif, CPU uniquement).
5. **Scoring hybride `embed` + `ncvalue`/`graph`** — **implémenté le 2026-09-07, sous forme de double signal exposé (option 3), pas de fusion en un score unique.** Trois options de composition évaluées : (a) somme pondérée après normalisation min-max — écartée d'emblée, poids `α` à calibrer par essai et normalisation dépendante du corpus ; (b) Reciprocal Rank Fusion — pas de calibration d'échelle nécessaire, mais fusionner en un seul score reste risqué (voir ci-dessous) ; (c) **retenue** : garder les deux signaux séparés (`score`=embed, `structural_score`/`structural_rank`=C-value/PositionRank) plutôt que de les fusionner — un score composite aurait risqué de réintroduire le bruit de discours académique générique qu'`embed` (plus proche voisin) a justement été conçu pour filtrer (voir l'historique centroïde → plus proche voisin plus haut), et aurait cassé la lisibilité simple d'`enrichment_suggestion` (seuil de similarité) pour un curateur non technique.

**Ce qui a été implémenté** : `_attach_structural_signal()` dans `loterre_extract_cli.py` calcule, uniquement quand `--extractor embed` est actif, un second score C-value/PositionRank (même bascule "auto" selon le volume de corpus que le choix normal d'extracteur) sur les mêmes candidats, stocké dans des champs dédiés (`structural_score`/`structural_rule`/`structural_rank`) qui n'écrasent jamais `score`/`rule` (le signal embed reste seul déterminant du tri principal et de `--embed-threshold`). Dans `run_extract_annotate_mode()` (`loterre_cli.py`), un candidat absent du vocabulaire, sous `--enrichment-threshold`, mais dans le top N% du classement structurel (`--structural-top-pct`, défaut 10%) est marqué `enrichment_suggestion_structural=True` — catégorie strictement séparée d'`enrichment_suggestion` (jamais les deux à la fois), pour un curateur qui veut voir aussi les candidats "forts structurellement mais loin du seed" sans que ça pollue la suggestion principale basée sur la similarité.

**Validation** : vérifié sur P66_en (`extract_annotate --extractor embed`) — 3 candidats sur 25 absents du vocabulaire basculent en `enrichment_suggestion_structural` (ex. *"sleep-dependent memory triage"*, embed_score=0.73, structural_rank=10/105 en PositionRank) sans jamais chevaucher `enrichment_suggestion`. Smoke tests `test_embed.sh`/`test_extract_cli.sh`/`test_extract_annotate_cli.sh`/`test_variants.sh` toujours verts.

**Mesuré le 2026-09-07** (`evaluate_domain_lang_structural_signal()`, nouveau dans `acter_eval.py`, seuils de production réels `--enrichment-threshold 0.95`/`--structural-top-pct 10` au départ, pas la coupure oracle top-N de la variante semi-supervisée existante) : F1 combiné (embed + structurel) **0.360** contre **0.222** pour embed seul à 10% (+62% relatif), porté par un rappel qui plus que double (0.127→0.313) au prix d'une précision qui chute de moitié (0.858→0.422 ; la catégorie structurelle isolée a une précision ≈0.313, nettement plus bruitée qu'embed seul). Détail complet dans `planification/analyse_benchmarks_extraction.md`, entrée "Mesure du signal structurel".

**Balayage `--structural-top-pct` (2/5/10/15/20/30%) et décision** : pas de pic net de F1 dans la plage testée (0.329 à 2% → plateau ~0.36 entre 10-20% → 0.386 à 30%, non monotone) — le vrai levier est le compromis precision/volume de bruit pour le curateur, pas un optimum de F1. Consigne explicite de l'utilisateur ("favorise la précision") + cohérent avec le principe déjà acté `CLAUDE.md` ("la précision compte plus que l'exhaustivité") : **défaut changé de 10% à 2%** (`src/loterre_cli.py` et `scripts/evaluation/acter_eval.py`, 2026-09-07) — P=0.568/F1=0.329 à 2%, contre P=0.422/F1=0.360 à l'ancien défaut 10% (F1 legèrement plus bas, mais liste structurelle nettement plus propre, cohérent avec le principe "curateur humain valide avant intégration").

---

## 9. Réflexion en cours — grammaire de candidats étendue (TermSuite) + spécificité *(suspendue le 2026-09-10, reprendre ici)*

**Point de départ** : lecture par l'utilisateur des fichiers de patrons TermSuite (`termsuite-resources/{en,fr}/*-multi-word-rule-system.regex`) — spaCy `doc.noun_chunks` (seule source de candidats jusque-là) a un angle mort structurel confirmé empiriquement : il ne produit jamais "N of/with N" (EN) ni "N de/avec N" (FR) comme span unique (`"quality of service"` → deux chunks séparés, jamais fusionnés).

**Ce qui a été implémenté (2026-09-10)**, dans `src/loterre_extract_cli.py` + fil CLI dans `src/loterre_cli.py` (duplication du parsing d'arguments, même convention que le reste des flags d'extraction) :

1. **`--prep-patterns`** (opt-in) : sous-ensemble ciblé N-prep-N (`npn`/`npnn`/`npan`/`anpn` en EN — préposition `of`/`with` ; `npn`/`npnn` en FR — préposition `de`/`avec`).
2. **`--all-candidate-patterns`** (opt-in, prioritaire sur `--prep-patterns` si les deux sont passés) : grammaire TermSuite **complète** non-"noisy" — 37 règles EN (`_EN_GRAMMAR_RULES`) + 34 règles FR (`_FR_GRAMMAR_RULES`), transcrites depuis les deux fichiers `.regex` réels (le fichier FR fourni par l'utilisateur en cours de session — mes motifs FR initiaux `de`/`avec` seulement pour `--prep-patterns` étaient une approximation ad hoc, pas la vraie grammaire : le `P` de base FR n'est en réalité restreint à aucune préposition particulière). Simplifications documentées en commentaire dans le code faute de moteur Ruta pour vérifier certains opérateurs exacts (`~D`/`~D?` → déterminant optionnel, `~Og`/`~Fg` → guillemets littéraux non négés, A2(FR) simplifié à ADJ seul).
3. **Bug de dédoublonnage identifié et corrigé avant tout bench** : avec autant de règles, beaucoup de spans chevauchent un noun_chunk sans lui être identiques (ex. "quality" et "quality of service" au même point de départ). `spacy.util.filter_spans` (le plus long gagne) aurait supprimé à tort les candidats courts imbriqués, cassant l'hypothèse de C-value classique (Frantzi et al. 1998 : la fréquence brute d'un candidat court doit inclure ses occurrences imbriquées, c'est la formule qui soustrait l'absorption). Remplacé par une déduplication stricte sur bornes `(start_char, end_char)` **identiques** uniquement.

**Mesuré sur ACTER** (détail complet et chiffré dans `planification/analyse_benchmarks_extraction.md`, entrées 2026-09-10) :
- Rappel candidat oracle : 0.5435 → **0.8294** avec `--all-candidate-patterns` (+154% de candidats).
- F1 (sweep top-N) : **gain net et large avec `ncvalue`** sur petit lot (+0.08 à +0.13 selon coupure, jusqu'à +50% relatif) ; **régression nette et systématique avec `graph`/PositionRank** à toute profondeur (jusqu'à −0.12) — PositionRank sur-score structurellement les composés dont les deux extrémités sont déjà des nœuds centraux du graphe de co-occurrence, indépendamment de leur validité terminologique réelle.
- **Coût de performance mesuré et décisif** : sur un gros corpus (>50k tokens, régime où `ncvalue` est auto-sélectionné), `extract` passe de 12.2s à **66.0s** (×5.4) avec `--all-candidate-patterns` — `build_containment_map()` (`loterre_cvalue.py`) est O(n²), et le volume de candidats ×2,46 en ACTER htfl donne (2,46)²≈6,05, cohérent avec le ×5,4 observé. Sur document unique/petit lot en revanche, le flag est gratuit (chargement spaCy dominant).
- **Décision** : les deux flags restent opt-in, non activés par défaut — confirmé par deux arguments indépendants (régression `graph`, coût O(n²) sur gros corpus `ncvalue`). Pas de garde-fou code empêchant une combinaison risquée (`--all-candidate-patterns --extractor graph`, ou sur gros corpus) — pas demandé par l'utilisateur pour l'instant.
- Question "et pour `embed` ?" — **pas mesurée** : `sentence-transformers`/`torch` absents de l'environnement de dev (pas de venv projet actif), installation explicitement refusée par l'utilisateur pour ce test. Hypothèse qualitative seulement (voir `analyse_benchmarks_extraction.md`) : `embed` scorant chaque candidat indépendamment par similarité sémantique (pas par centralité de graphe), *a priori* moins vulnérable au biais de `graph` — mais `_attach_structural_signal()` réutilise en interne `ncvalue`/`graph` selon la taille du corpus, donc le signal structurel secondaire d'`embed` hériterait indirectement du même risque sur corpus court. **À mesurer si l'environnement de dev gagne ces dépendances.**

**Piste suivante, discutée mais pas implémentée — mesure de "Specificity" (TermSuite)** : en explorant `termsuite-resources`/`termsuite.github.io/documentation/termsuite-pipelines`, découverte que **"Specificity" est le critère de tri final PAR DÉFAUT de TermSuite** (pas C-value) — `default-extractor-config.json` : `"ranking": {"property": "SPECIFICITY", "is-descending": true}`. Mécanisme : contraste de fréquence entre le corpus analysé et une référence de "langue générale" (`{en,fr}-general-language.txt`, tables `lemme::POS::fréquence`, 48 571 entrées EN sur 28,7M mots de référence / 17 287 entrées FR sur 82,6M mots — type Weirdness Ratio, technique classique, aucun modèle, CPU pur).

Sanity-check fait pendant la session (fréquences dans la table EN) — sépare nettement le bruit générique des vrais termes de domaine sur les cas déjà documentés comme problématiques (X64, `docs/README.md` §5.4/`analyse_benchmarks_extraction.md`) :

| Mot | Fréq. langue générale (/28,7M) |
|---|---:|
| hand | 5 531 |
| author | 923 |
| thing | 11 610 |
| linguistics | 11 |
| lexicon | 20 |
| philology / semiotics | 0 (absent) |

**Intérêt spécifique** : contrairement au signal structurel (réservé à `embed`, compense sa faiblesse propre), la spécificité ne nécessite **aucun vocabulaire cible** — calculable pour `ncvalue`/`graph`/`embed` indifféremment, y compris en mode `extract` "à froid" (où le bruit académique générique n'a actuellement aucun filtre — le problème X64 documenté avant que Phase 5/embed ne le résolve, mais seulement pour `extract_annotate` avec vocabulaire).

**Décision de conception discutée (pas tranchée)** : signal additionnel (`specificity_score`/`specificity_rank`, même schéma que `structural_score`) plutôt qu'un 4ᵉ `--extractor` autonome — raisonnement : la spécificité seule ne capture pas la structure/forme d'un terme (un mot rare mais mal formé scorerait aussi haut qu'un vrai terme rare), et chez TermSuite elle-même le tri par spécificité n'intervient qu'après tout un pipeline de filtrage/morphologie/regroupement en amont qu'on n'a pas ici. Cohérent avec le principe déjà acté (Option 3, §8) de garder les signaux séparés plutôt que fusionnés. **Réserve à vérifier avant de trancher définitivement** : tester quand même la spécificité seule (classement brut, script de bench jetable, pas exposée en CLI) pour confirmer empiriquement qu'elle apporte moins en solo qu'en signal additionnel, avant de graver ce choix de conception.

**Licence** : fichiers `general-language.txt` sans en-tête explicite dans le dépôt `termsuite-resources` (contrairement aux `.regex`), mais même situation que les tables de morphologie déjà vendorisées (`resources/termsuite_morphology/`, documentées Apache 2.0 dans `CLAUDE.md`) — même base déjà acceptée par le projet, pas un nouveau problème identifié.

**Suite (2026-09-11)** :

1. ✅ **Vendorisé** : `resources/termsuite_general_language/{en,fr}/general-language.txt` (copie brute, sans en-tête inline — les données contiennent de vrais tokens `#...`, un en-tête `#` serait ambigu ; provenance documentée dans `resources/termsuite_general_language/SOURCE.md` à la place, même base de licence que `termsuite_morphology/`).
2. ✅ **Implémenté** : `src/loterre_specificity.py` — `score_candidates_specificity()`, Weirdness Ratio (moyenne géométrique sur les mots de contenu du candidat, `(lemme, lettre_pos)` avec repli sur une constante de lissage si absent de la table). Champs `specificity_score`/`specificity_rank` posés dynamiquement sur `CandidateTerm` (pas de `__slots__`) — **pas encore ajoutés au schéma officiel** (`to_dict()` inchangé), prototype de mesure uniquement, rien de câblé en CLI.
   - **Bug trouvé et corrigé pendant le prototypage** : les mots-outils adjectivaux/adverbiaux (`other`, `same`, `very`...) sont absents de `general-language.txt` (table limitée aux mots de contenu), donc lus à tort comme "jamais vus en langue générale" = très spécifiques — mesuré sur "other hand" (score 74× plus haut que "one hand" sur un même texte avant correction). Corrigé en excluant `_GENERIC_ADJ_EN`/`_GENERIC_ADV_EN` (promue en constante module dans `loterre_extract_cli.py`, réutilisée ici) de l'agrégation — même liste que la grammaire de motifs, pour la même raison (pas de contenu lexical propre). Pas d'équivalent FR (même asymétrie déjà acceptée pour `--all-candidate-patterns`).
3. ✅ **Benchmarké sur ACTER** (8 combinaisons domaine/langue, `--min-freq 1`, sweep top-N identique aux bench précédents) — deux framings testés :

   **Classement autonome** (spécificité seule vs `ncvalue`/`graph`) :

   | Fraction | ncvalue | graph | specificity |
   |---:|---:|---:|---:|
   | 0.10 | 0.257 | 0.145 | 0.108 |
   | 0.50 | 0.344 | 0.389 | 0.270 |
   | 1.00 | 0.397 | 0.500 | 0.377 |
   | 2.00 | 0.505 | 0.551 | 0.525 |

   Plus faible que `ncvalue`/`graph` aux coupures serrées (précision-first) — confirme empiriquement le raisonnement du 2026-09-10 : la spécificité seule ne capture pas la forme/structure d'un terme (un mot rare mal formé scorerait aussi haut qu'un vrai terme rare). **Rejeté comme 4ᵉ `--extractor` autonome.**

   **Filtre de bruit** (retire les candidats sous la spécificité médiane du corpus, avant `ncvalue`/`graph`) :

   | Fraction | ncvalue Δ | graph Δ |
   |---:|---:|---:|
   | 0.10 | −0.030 | −0.002 |
   | 0.50 | −0.024 | −0.007 |
   | 1.00 | **+0.029** | −0.015 |
   | 1.50 | **+0.045** | −0.030 |
   | 2.00 | +0.001 | −0.040 |

   **Résultat mitigé, pas un gain net** : aide `ncvalue` aux coupures moyennes/larges (+0.02 à +0.045 à N=1.0-1.5×) mais nuit systématiquement à `graph` (jusqu'à −0.04, à toute profondeur). Une coupure fixe à la médiane (50%) est un instrument grossier, probablement mal calibré — même limite déjà rencontrée avant le sweep `--structural-top-pct` (2026-09-07) qui avait dû être balayé (2/5/10/15/20/30%) avant de trouver un défaut correct.

4. **Balayage du seuil (même session, 2026-09-11)** : 0/10/20/30/40/50/60/70% retirés, `ncvalue` uniquement. **40% est un pic net** — F1 top-N=1.00× : 0.397→0.447 (+12.6%), top-N=1.50× : 0.455→0.518 (+13.8%), quasi neutre aux coupures serrées (top-N=0.10×). Le 50% testé en premier était déjà au-delà du pic, d'où le résultat mitigé initial — pas une propriété du signal, un mauvais calibrage. Détail complet dans `planification/analyse_benchmarks_extraction.md`.
5. **Implémenté et câblé en CLI** : `filter_by_specificity()` (`src/loterre_specificity.py`), exposé via `--specificity-filter-pctl` (0 = désactivé par défaut) dans `loterre_extract_cli.py` + dupliqué dans `loterre_cli.py` (même convention que les autres flags d'extraction). Appliqué **avant** `score_extracted_candidates()`. Toujours restreint à `--extractor ncvalue` dans la documentation — aucun garde-fou code empêchant `--extractor graph`, juste déconseillé (mesuré dégradant au seuil 50%, pas re-testé aux autres seuils avec `graph`).

**État final (filtre `ncvalue`)** : signal validé et exploitable pour `ncvalue` avec `--specificity-filter-pctl 40` (ou proche). Pas activé par défaut (même prudence que les autres flags d'extraction de cette session) — décision utilisateur si un défaut différent de 0 est souhaité un jour. `specificity_score`/`specificity_rank` **ajoutés au schéma officiel** `CandidateTerm`/`to_dict()`/export CSV (2026-09-11, suite à une question utilisateur constatant qu'ils n'étaient pas visibles en sortie) — exposés (non `null`) pour les candidats survivants quand `--specificity-filter-pctl` > 0, `null` sinon (même comportement que `structural_score` avec `embed`). Documenté dans `docs/README.md` §5.3 (schéma) et `docs/underthehood.md`/`docs/curation_guide.md`.

**Suite (même session, 2026-09-11) — spécificité comme troisième signal de suggestion pour `embed`** : question utilisateur ("pas de spécificité pour embed ?") ouvrant une piste distincte du filtre `ncvalue` — utiliser la spécificité comme signal additionnel pour `--extractor embed`, sur le même modèle que le signal structurel (Option 3, §8), plutôt que comme filtre pré-scoring.

Mesuré sur ACTER (méthodologie semi-supervisée seed/holdout, comme `evaluate_domain_lang_structural_signal`, script ad hoc pas `acter_eval.py`) :

| | Precision | Rappel | F1 |
|---|---:|---:|---:|
| `embed` seul | 0.899 | 0.114 | 0.203 |
| + structurel (2%) seul | 0.641 | 0.171 | 0.270 |
| + spécificité (10%) seul | 0.500 | 0.182 | 0.267 |
| **+ structurel(2%) OU spécificité(10%)** | 0.492 | 0.231 | **0.314** |
| spécificité isolée (candidats niveau 3 seulement, ni embed ni structurel) | **0.27–0.30** | 0.02–0.06 | 0.04–0.10 |

La combinaison bat les deux signaux pris séparément (+16% relatif vs structurel seul, +18% vs spécificité seule) — les deux signaux ratent des choses différentes (structurel = force statistique/positionnelle, spécificité = rareté vs langue générale), leur union récupère plus de vrais termes. Mais la précision **isolée** du niveau 3 (dernière ligne, mesurée séparément après la première mesure combinée trop optimiste en apparence) est nettement plus faible que celle du niveau 2 (~0.29 contre ~0.64) — le gain de F1 combiné cache un signal individuellement bien plus bruité.

**Décision (utilisateur : "on en tire les conséquences, que proposes-tu ?")** : implémenté comme **troisième niveau de suggestion séparé** (`enrichment_suggestion_specificity`), pas fusionné avec le niveau 2 — cohérent avec le principe déjà acté (Option 3) de listes séparées à confiance différenciée, d'autant plus justifié ici vu l'écart de précision isolée mesuré. **Opt-in, désactivé par défaut** (`--specificity-top-pct 0.0`) — contrairement au niveau 2 qui est actif par défaut, car le profil de bruit du niveau 3 est un choix explicite du curateur (plus de rappel contre plus de tri manuel), pas un défaut sûr pour tout le monde. Si activé, **10%** est la valeur mesurée utile.

**Implémenté** :
- `score_extracted_candidates()` (`loterre_extract_cli.py`) prend désormais `lang` et appelle `score_candidates_specificity()` **toujours** pour `--extractor embed` (comme `_attach_structural_signal()`, coût négligeable, pas de modèle) — `specificity_score`/`specificity_rank` donc toujours renseignés pour `embed`, indépendamment de `--specificity-top-pct`.
- `run_extract_annotate_mode()` (`loterre_cli.py`) calcule `enrichment_suggestion_specificity` à partir de `--specificity-top-pct` (nouveau flag, défaut 0.0, sur le sous-parseur `extract_annotate` uniquement — même emplacement que `--enrichment-threshold`/`--structural-top-pct`) — mutuellement exclusif des niveaux 1 et 2.
- `enrichment_suggestion_specificity` ajouté au schéma `CandidateTerm`/`to_dict()`/export CSV.
- Testé de bout en bout (texte jouet + faux dictionnaire) : mutuelle exclusivité vérifiée, comportement par défaut (flag à 0) confirmé neutre (aucun candidat jamais marqué, mais `specificity_score` déjà visible).
- Documenté dans `CLAUDE.md`, `docs/README.md` (§5.1 options, §5.3 schéma, §5.4 mécanisme+chiffres), `docs/underthehood.md` (étape 7, trois niveaux), `docs/curation_guide.md` (consigne de travail, précision isolée explicitement signalée comme plus faible que le niveau 2).

**État global de cette réflexion (§8+§9) : close.** Trois avancées livrées cette session : grammaire de candidats étendue (opt-in, ncvalue uniquement, gros corpus à éviter), filtre de spécificité pour `ncvalue` (opt-in, 40% calibré), troisième niveau de suggestion spécificité pour `embed` (opt-in, 10% calibré). Reprise possible plus tard : mesurer si le seuil 10% du niveau 3 est optimal (pas balayé au-delà, contrairement au niveau 2) ; envisager d'inclure ce test dans `acter_eval.py` officiellement plutôt que via script ad hoc si cette piste devient récurrente.

**Comblement de deux dettes identifiées lors d'une relecture de cohérence de la documentation (même session, 2026-09-11)** :
1. **Tests automatisés manquants** : `tests/smoke/test_specificity.sh` créé et vert (4 vérifications : `--prep-patterns` produit un composé N-prep-N que `noun_chunks` seul ne produit jamais, `--all-candidate-patterns` produit strictement plus de candidats sans span dupliqué, `--specificity-filter-pctl` retire des candidats et peuple `specificity_score`, `--specificity-top-pct` peuple `enrichment_suggestion_specificity` en exclusivité mutuelle des niveaux 1/2). Câblé dans `Makefile` (`make test-specificity`, inclus dans `test-extraction`) et `tests/smoke/run_regression_all.sh`.
2. **Scripts de benchmark ad hoc non committés** : consolidés et committés dans `scripts/evaluation/` — `bench_candidate_patterns.py` (`--prep-patterns`/`--all-candidate-patterns`, remplace les 4 scripts ad hoc du 2026-09-10) et `bench_specificity.py` (3 modes : `standalone`/`filter-sweep`/`embed`, remplace les 4 scripts ad hoc du 2026-09-11). Re-smoke-testés sur un domaine ACTER unique après consolidation (résultats cohérents en direction avec les mesures 8-domaines déjà journalisées) — pas re-exécutés en entier (8 domaines × plusieurs configurations, coûteux), donc les chiffres de référence dans ce document et dans `analyse_benchmarks_extraction.md` restent ceux des scripts ad hoc originaux, pas une ré-mesure via ces nouveaux scripts consolidés.

---

## 10. Corpus réel RevueESR — validation à pleine échelle + 3ᵉ découverte O(n²) *(suspendu le 2026-09-14, reprendre ici)*

**Contexte** : après tout le travail des §8/§9 (grammaire de motifs, spécificité), demande de re-lancer `extract_annotate --extractor embed` sur un vrai corpus de production, `data/RevueESR-textFR.json` (1539 documents, **5 954 459 tokens** — bien au-delà de tout ce qui a été testé sur ACTER), vocabulaire `SEN` (`dictionary/fr_annot_SEN.jsonl`), pour rafraîchir un ancien fichier de sortie (`output_extract/SEN_fr_RevueESR_extract_annotate.json`, généré ailleurs avant cette session, encore avec l'ancien nom `enrichment_suggestion` et sans `specificity_score`).

**Déroulé** :
1. Premier essai échoué : `sentence-transformers` absent de l'environnement WSL de dev — installé en cours de session (`pip install --user --break-system-packages sentence-transformers`, l'install standard bloquée par la protection PEP 668 `externally-managed-environment` de Debian/Ubuntu).
2. Deuxième essai échoué après **23m32s** : `--profile` manquant (`extract_annotate` appelle en interne le moteur d'annotation v1.0 pour `in_vocabulary`, qui l'exige). Corrigé avec `--profile term_balanced`.
3. Run réussi (28m39s) avec `--specificity-top-pct 10` (niveau 3 activé). **Résultat à pleine échelle, cohérent avec les chiffres ACTER** : 38 838 candidats, 225 `in_vocabulary=True`/38 613 absents, niveau 1=177, niveau 2=705, niveau 3=3686, **exclusivité mutuelle vérifiée sur les 38 838 candidats (0 violation)**. Échantillon niveau 3 qualitativement plausible (*"intoxication ciguatérique"*, *"toxicité chimique"*, *"micro-organismes infectieux"*...) — cohérent avec le domaine du corpus (santé environnementale/toxicologie, en-tête "Env Risque Santé" du texte).

**Question utilisateur ensuite : "tu n'as pas pris les variantes ?"** — `--detect-variants` (Phase 4) n'avait été activé ni sur ce run ni sur l'original (vérifié : `canonical_form`/`variant_type` jamais renseignés dans l'ancien fichier). Avant de relancer un 3ᵉ run de ~30 min avec `--detect-variants`, vérification du risque de performance (réflexe acquis cette session après la découverte `build_containment_map()` O(n²)) :

**3ᵉ découverte O(n²) de la session** : `group_variants()` (`src/loterre_variants.py`) bucket les candidats par longueur puis compare **toutes les paires à l'intérieur d'un bucket** dans deux passes — `_group_single_token_diff()` (motif `morph_prefix`) et `_group_derivation()` (motif `morph_derivation`). La docstring de `_group_single_token_diff()` suppose "cher uniquement à l'intérieur d'un bucket, qui reste petit en pratique car --min-tokens/--max-tokens bornent la longueur des candidats" — hypothèse validée seulement sur de petits corpus de test (P66, 11 documents), jamais stress-testée à l'échelle production. Mesuré sur la distribution réelle des candidats RevueESR (depuis le JSON déjà généré, sans rien ré-extraire) :

| Longueur (tokens) | Candidats |
|---:|---:|
| 1 | **21 459** |
| 2 | **15 631** |
| 3 | 1 113 |
| 4 | 522 |
| 5 | 89 |
| 6 | 24 |

Un bucket de 21 459 candidats en O(n²) ≈ 230 millions de comparaisons par paire (idem ~122M pour le bucket de longueur 2) — même famille de risque que `build_containment_map()`, jamais rencontré avant parce que jamais testé sur un corpus de cette taille.

**Test isolé lancé puis arrêté sur demande utilisateur** ("d'accord abandonne", 2026-09-14) : chargeait les 38 838 `CandidateTerm` depuis le JSON déjà généré (sans repasser par spaCy/embed) et chronométrait `group_variants()` seul. **Toujours en cours d'exécution au moment de l'arrêt** (plusieurs minutes écoulées sans résultat, tâche stoppée manuellement, pas de crash) — sans être une mesure chiffrée, c'est un indice cohérent avec le risque O(n²) suspecté : le calcul n'était clairement pas instantané. **Investigation explicitement abandonnée pour l'instant, pas résolue** — `--detect-variants` reste non testé sur RevueESR, aucune décision prise sur sa praticabilité à cette échelle.

**À faire pour reprendre** :
1. Relancer le test de timing (arrêté sans résultat, voir ci-dessus) : charger les `CandidateTerm` depuis `output_extract/SEN_fr_RevueESR_extract_annotate.json` (déjà là, pas besoin de ré-extraire), appeler `group_variants(cands, 'fr')`, chronométrer — cette fois le laisser aller jusqu'au bout (ou fixer une limite de temps explicite, ex. 10-15 min, plutôt que de l'arrêter sans donnée).
2. Si le temps est prohibitif (minutes à heures) : documenter `--detect-variants` comme limité aux corpus modestes (même conclusion que `--all-candidate-patterns`), envisager une optimisation (index par lemme/préfixe au lieu de la comparaison par paire brute, sur le modèle de `_group_expansion()` qui utilise déjà un index inversé — voir son commentaire "évite une comparaison O(n²) sur l'ensemble du corpus", donc le correctif a déjà un précédent dans le même fichier).
3. Si le temps est raisonnable : relancer RevueESR avec `--detect-variants` en plus de `--specificity-top-pct 10`, comparer.
4. Journaliser la mesure dans `planification/analyse_benchmarks_extraction.md` (gabarit habituel) et mettre à jour ce document + la mémoire persistante avec la conclusion.

---

## Références

- Frantzi, K., Ananiadou, S., Mima, H. (2000). *Automatic recognition of multi-word terms: the C-value/NC-value method*. International Journal on Digital Libraries, 3(2), 115–130.
- TermSuite : https://termsuite.github.io/ / https://github.com/termsuite
- spaCy noun chunks : https://spacy.io/usage/linguistic-features#noun-chunks
- KeyBERT : https://github.com/MaartenGr/KeyBERT
- pke (Python Keyphrase Extraction, contient C-value) : https://github.com/boudinfl/pke
