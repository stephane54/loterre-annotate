# Journal des versions — loterre-annotate

---

## v1.0.0 — Moteur d'annotation terminologique (release majeure)

**Date :** 2026-06-13  
**Statut :** stable

### Fonctionnalités

**Annotation par dictionnaire (mode unique)**

- Détection des termes d'un vocabulaire Loterre dans un texte libre
- Stratégie de matching en 5 passes : patrons POS+lemme, surface exacte, séquence lemme, surface structurelle, lemme structurel
- Scoring de confiance par passe (1.0 → 0.70) avec seuils configurables
- Matching par Trie (recherche longest-match)
- Génération automatique de variantes (parenthèses, apostrophes, casse)

**Langues supportées**

- Français (`fr_core_news_sm`)
- Anglais (`en_core_web_sm`)

**Profils préconfigurés**

- `entity_strict` (seuil 0.80) — entités nommées, haute précision
- `term_balanced` (seuil 0.75) — terminologie mixte
- `term_recall` (seuil 0.70) — rappel maximum, termes compositionnels

**Filtres qualité**

- Élimination des stopwords
- Gardes syntaxiques (copule, motifs discursifs faibles)
- Pénalités contextuelles pour termes mono-token ambigus
- Fenêtre de contexte ±2 tokens

**Vocabulaires**

- 30+ vocabulaires Loterre indexés via `configs/registry.yaml`
- Résolution par identifiant court (ex. `P66`, `9SD`) ou URI complète
- Dictionnaires au format JSONL (label, pref, id, pattern, altLabels)

**CLI**

- `loterre-annotate` — point d'entrée principal avec résolution du registre
- `loterre-engine` — moteur bas niveau
- `loterre-benchmark` — comparaison locale vs API ISTEX de production
- `loterre-render` — visualisation HTML interactive avec surlignage des termes

**Modes de sortie**

- JSONL (défaut)
- HTML interactif avec comparaison gold standard

---

## v1.1.0 — Maintenance outillage release (patch)

**Date :** 2026-06-13  
**Statut :** stable

### Changements

- `make build` / `make deploy` : passage des arguments (`BUILD_ARGS`, `DOCKER_ARGS`) et exemples d'usage ajoutés au texte d'aide affiché — aucun changement fonctionnel côté annotation/extraction

---

## v1.2.0 — Extraction terminologique intégrée *(VERSION mis à jour localement, non taguée/publiée)*

**Statut réel :** toutes les phases prévues (0 à 6, y compris la détection de variantes Phase 4) sont **terminées** dans le code (`src/loterre_extract_cli.py`, `loterre_cvalue.py`, `loterre_positionrank.py`, `loterre_embed.py`, `loterre_variants.py`) et documentées dans [planif_extraction_terminologique.md](planif_extraction_terminologique.md). Le fichier `VERSION` a été passé à `2.0.0-beta` (2026-09-04) puis revu à `1.2.0` (2026-09-07, choix de convention de versionnement — minor bump plutôt que major) pour refléter cet état sur `master` — mais **aucun `git tag`/release officielle n'a encore été exécutée** (`production/release.sh --tag`, qui inclut build + ~30 min de tests EZS + Docker + publication) : pas encore publiée sur le remote.

### Fonctionnalités livrées

- Extraction de candidats termes par noun chunks spaCy + scoring C-value (Frantzi et al. 1998)
- Bascule automatique C-value/PositionRank selon le volume de corpus (`--extractor auto`, seuil configurable)
- Trois sous-commandes CLI positionnelles : `annotate` / `extract` / `extract_annotate`
- Détection de variantes morphologiques, graphiques et syntaxiques, inspirée de TermSuite (CNRS/TTC) — `--detect-variants`
- Croisement extraction/vocabulaire Loterre natif (`in_vocabulary` / `enrichment_suggestion_embed`)
- Scoring par embeddings au plus proche voisin d'un vocabulaire cible (`--extractor embed`, `paraphrase-multilingual-MiniLM-L12-v2`) — **pas** `--extractor bert`
- Benchmark intégré contre le gold ACTER (`make benchmark-acter`) : F1 PositionRank=0.496, C-value=0.391, au sommet de la fourchette D-Terminer (0.32–0.50, GPU) obtenue en CPU pur
- **Ajouts post-complétion des phases, opt-in, jamais activés par défaut (2026-09-10/11)** : génération de candidats étendue par grammaire de motifs TermSuite (`--prep-patterns`/`--all-candidate-patterns`) et filtre de spécificité par contraste de langue générale (`--specificity-filter-pctl`, `src/loterre_specificity.py`) — voir `planification/planif_extraction_terminologique.md` §9 et `planification/analyse_benchmarks_extraction.md` pour le détail et les mesures

---

> **Note** : les versions v1.3.0 à v1.11.0 ont été publiées (tags git, `production/release.sh`) sans entrée dans ce journal ; leur contenu est dans l'historique git (`git log v1.2.0..v1.11.0`). `VERSION` = 1.11.0.

## Travaux en cours, non publiés (après v1.11.0) — 2026-09-28 → 2026-10-09

**Statut :** dans l'arbre de travail de `master`, **non commités**. Détail des mesures : `planification/analyse_benchmarks_extraction.md`, entrées du 2026-09-29 au 2026-10-09 (points 1 à 18).

### Rapport d'analyse (`extract_annotate --report rapport.html`)

- Nouveau module `src/loterre_report.py` (alias `--topic-report`, `--report-topics N`) : page HTML autonome + JSON.
- Contenu : chiffres clés (part du vocabulaire retrouvée dans le corpus, documents annotés, suggestions par liste), **mode d'emploi** (consignes de relecture et sens des indicateurs), graphiques annotation/extraction, suggestions les plus fréquentes par liste, et **couverture du vocabulaire par thème (expérimental)**.
- Couverture par thème : segments de 600 caractères, NMF sur les candidats, couverture = part des segments du thème contenant un **terme propre** du vocabulaire (surreprésenté ≥ 2×), mesurée par les annotations de l'annotateur. Les termes transversaux ne comptent que là où ils sont surreprésentés ; un **thème générique** (poids ≥ 2,5 × la moyenne, discours général) est affiché hors classement.
- `scripts/evaluation/build_report.py` : produit le rapport depuis des sorties existantes, ou regénère la page depuis le JSON d'un rapport (`--from-report`).
- Nombre de thèmes automatique (segments / 30, borné 5–30) **vérifié par mesure** (2026-10-08, `scripts/evaluation/sweep_topics.py`, k = 10 à 50 sur RevueESR) : 30 a la meilleure stabilité et une cohérence au plateau (20–30) ; au-delà, le thème générique se fragmente et échappe à sa règle de détection. Le constat principal (santé au travail la moins couverte, 1 à 1,7 %) ne dépend pas du nombre de thèmes. Plafond de 30 conservé ; la formule pour les petits corpus reste non validée.

### Champs d'aide au curateur (JSON et CSV des candidats)

- `n_docs` (documents contenant le candidat), `nearest_vocab_term` (embed : terme du vocabulaire le plus proche), `context` (extrait autour de la première occurrence) ; avec `--report` : `topic_id`, `topic_label`, `topic_coverage`, `topic_generic` (rangement par thème, jamais un score).
- `extract` reçoit aussi `n_docs` et `context`.

### Extraction

- `is_valid_candidate()` exige au moins deux lettres : élimine ponctuation, symboles et lettres isolées (« - », « – », « © », « n », « C »), garde les sigles courts (« PM », « IC »). ACTER : effet neutre (F1 ±0,002).
- **Nouvelle option `--respot-occurrences`** (`extract`, `extract_annotate`, `acter_eval.py`) : chaque candidat reçoit toutes les occurrences de son texte dans le corpus (insensible à la casse, y compris à l'intérieur de groupes nominaux plus longs), et ses variantes de casse sont fusionnées. Jusqu'ici, un candidat ne comptait que les endroits où spaCy produisait exactement ce groupe nominal. Repérage en une passe par document (trie sur les tokens). ACTER : F1 graph 0,499 → 0,543, ncvalue 0,398 → 0,470, liste 1 (embed) 0,224 → 0,349 avec une précision de 0,88, listes 1+2 0,329 → 0,432 — gain sur les 8 combinaisons domaine × langue. **Sur RevueESR, pas utilisable en l'état** : 1 h 36 au lieu de 28 min, et liste 2 envahie de suites de mots outils (« Of the », « In the », « pas d ») dont la fréquence explose une fois repérées dans le texte libre. **Corrigé le même jour (v2)** : repérage limité à l'intérieur des groupes nominaux, et seulement pour les candidats déjà au-dessus de `--min-freq`. ACTER : graph 0,521, liste 1 0,319 (précision 0,88), listes 1+2 0,406 (précision 0,60) ; RevueESR : 39 min au lieu de 28, plus de « Of the » dans la liste 2. Puis précision par candidat mesurée (entrée 18) : l'option n'augmente pas le nombre de suggestions justes distinctes (liste 1 : 468 contre 521, précision par candidat 0,51 contre 0,53) — le gain est token-level, pas pour le curateur. **Reste une option, pas de passage par défaut.**
- **Filtre de mots outils FR + EN** (`is_valid_candidate`, par défaut) : rejette les candidats faits uniquement de mots outils français ou anglais, d'élisions (« d », « qu ») ou de « -ci » ; les sigles en majuscules (« NO », « OR ») sont gardés. Sur RevueESR, retire « Of the », « In the », « pas d », « D autres », « -ci » et les mots outils anglais des résumés ; ACTER neutre (≤ 0,001).

### Données

- `scripts/corpus/clean_revueesr.py` → `data/RevueESR-textFR.clean.json` : réparation des défauts d'extraction PDF (76 334 césures, 23 259 accents, 9 437 ligatures fi/fl, 380 accents initiaux — uniquement si la forme corrigée existe ailleurs dans le corpus) et retrait du paratexte de la revue (en-têtes, « Pour citer », courriels, « Tirés à part », signatures et références des brèves, remerciements). Résultat : +14 % d'annotations SEN, liste 2 débarrassée des en-têtes de revue.

### Évaluation et méthode

- Signaux de répartition intra-corpus (NMF, recette BERTopic, IDF résiduel, DP) **rejetés** comme signal de pertinence par candidat : ils ne font pas mieux que la fréquence brute (`scripts/evaluation/bench_topical.py`). Règle de méthode adoptée : tout nouveau signal est comparé au témoin fréquence (et au retrait des hapax) et mesuré aussi en précision par candidat.
- Correction des précisions publiées : liste 2 seule = 0,39 par token / 0,23 par candidat (l'ancien ~0,57-0,64 était l'union listes 1+2) ; tableau du 2026-09-11 non reproductible, chiffres de référence reproduits le 2026-09-30.
- **Affichage des précisions (2026-10-15)** : tout support destiné au curateur (guide de curation, rapport HTML, présentations) donne la précision **par candidat** (« part de suggestions justes » : 0,53 / 0,23 / 0,14 pour les listes 1 / 2 / 3) ; la précision par token, pondérée par les occurrences (0,85 / 0,39 / 0,27), reste dans les benchmarks, toujours libellée. Elle avait été présentée à tort comme « 85 % des suggestions sont justes » dans une diapositive. Constat associé : à nombre de suggestions égal, embed trouve plus de termes justes distincts que TermSuite (521 contre 385) — l'avantage de TermSuite en rappel n'existe qu'en token-level.
- Consigne de relecture : trier chaque liste par fréquence décroissante (liste 1 : quart le plus fréquent P 0,81 par candidat, quart le moins fréquent 0,41), en écartant d'abord le bruit évident sur un corpus issu de PDF.
- **Comparaison TermSuite sur ACTER (2026-10-09)**, faite pour la première fois, même protocole token-level (`scripts/evaluation/termsuite_acter_eval.py`, TermSuite 3.0.10 en configuration par défaut, installé dans `~/app/termsuite-run/`) :
  - sans vocabulaire : TermSuite F1 **0,569** contre 0,499 (PositionRank) et 0,398 (C-value) — gain par le rappel (0,63 contre 0,45), précision un peu inférieure (0,52 contre 0,56) ;
  - avec vocabulaire, à nombre de suggestions égal : la liste 1 (embed) garde la meilleure **précision** (0,85 contre 0,53), TermSuite le meilleur F1 (0,38 contre 0,22). Pour le cas d'usage curateur, où la précision prime, embed reste le pipeline recommandé.
  - Hypothèse vérifiée le même jour (`scripts/evaluation/bench_respot.py`) : l'avance de TermSuite venait surtout de son repérage de toutes les occurrences. Corrigé chez nous par `--respot-occurrences` (voir Extraction) ; avec l'option, embed dépasse TermSuite et l'écart à froid tombe à 0,026 de F1. Pas d'intégration de TermSuite nécessaire.

### Divers

- `requirements.txt` : `numpy<2` (thinc 8.2.x, imposé par spaCy 3.7, est compilé contre numpy 1.x) et `scikit-learn>=1.3` (rapport). Le webservice (`github-web-services`) épingle aussi `numpy<2` dans son Dockerfile en attendant une release.
- Aide CLI réparée : `extract_annotate --help` et `loterre_extract_cli.py --help` plantaient depuis v1.9.0 (`%` non doublé dans un texte d'aide).
- `acter_eval.py --skip-cold` ne plante plus à l'écriture du Markdown quand le dossier de sortie n'a pas de résultats à froid (`acter_results.json`) : le Markdown est alors simplement omis.
- `docs/slide_termsuite_acter.pptx` : diapositive de synthèse embed contre TermSuite, au style de `docs/Extraction_terminologique_v2.pptx`.

### Résultats de référence — RevueESR / SEN (corpus nettoyé, code actuel, 2026-10-09)

- 1 539 documents, 5,53 M tokens, 36 755 candidats, 243 déjà dans SEN (36 512 nouveaux) ; suggestions listes 1 / 2 / 3 = 191 / 660 / 3 509 ; run complet en 24 min 42, 5,8 Go au pic. Avant le filtre de mots outils (`clean3`) : 37 054 candidats, listes 191 / 666 / 3 540.
- 250 des 429 concepts SEN (58 %) présents dans le corpus ; 89 % des documents contiennent au moins un terme SEN.
- Couverture par thème : les mieux couvertes restent évaluation des risques (25 %), mortalité/chaleur (22 %), pesticides (21 %), pollution de l'air (19 %). La santé au travail reste parmi les zones les moins couvertes (1,9 %), mais n'est plus la dernière : depuis le filtre de mots outils, le thème de discours général se scinde en deux petits thèmes (« compte, prise, facteurs », « mise, France, place ») qui échappent à la règle du thème générique et occupent le bas du classement — même effet qu'au-delà de 30 thèmes (entrée 13). Avant le filtre (`clean3`) : santé au travail dernière à 1 %, évaluation des risques 33 %.
- Sorties : `output_extract/RevueESR_clean6_base_*` (code actuel) et `RevueESR_clean6_respot_*` (même run avec `--respot-occurrences`) ; `RevueESR_clean3_*` conservé (référence d'avant le filtre, et `annotate_SEN.json` — annotations SEN seules, toujours valables pour `build_report.py`).
