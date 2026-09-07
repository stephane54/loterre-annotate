# Under the hood — `--extractor embed`

Déroulé pas à pas du scoring par embeddings (Phase 5, v2.0) et du signal
structurel secondaire qui l'accompagne (Option 3, §8), du texte brut aux deux
niveaux de suggestion d'enrichissement. `--extractor embed` intervient dans
le mode `extract_annotate` : il ne remplace pas l'extraction de candidats, il
remplace seulement leur **scoring** — classer les candidats par proximité
sémantique à un vocabulaire Loterre cible plutôt que par fréquence (C-value)
ou par centralité dans le texte (PositionRank), et calcule ce second signal
en complément (étape 7 ci-dessous).

Pour la consigne d'usage (quand choisir quelle méthode, comment un curateur
doit traiter les suggestions), voir `docs/curation_guide.md` — ce document-ci
couvre uniquement le mécanisme technique.

## Étape par étape

**1. Extraction des candidats (indépendante de l'extracteur)** —
`loterre_extract_cli.py:79-123`
- spaCy tourne sur le corpus (`nlp.pipe`), un `doc` par ligne du JSONL
  d'entrée.
- Chaque `noun_chunk` est nettoyé en bordure (`clean_chunk_span` : retire
  DET/PRON/ADP/ponctuation/élisions FR mal taguées).
- Filtré par `is_valid_candidate` (longueur, POS de contenu NOUN/PROPN/ADJ,
  pas 100% stopwords). La ponctuation interne est tolérée **seulement** si
  c'est un connecteur de type tiret/slash (`_CONNECTOR_PUNCT`) — spaCy
  tokenise souvent un composé scientifique (`renin-angiotensin-aldosterone`,
  `ISO/IEC 27001`) en éclatant le tiret/slash en token PUNCT/SYM séparé ; sans
  cette tolérance, tout le span était rejeté avant même le scoring (mesuré
  sur le gold ACTER EN : 93% des termes gold à tiret/slash jamais candidats
  — voir `planification/analyse_benchmarks_extraction.md`, entrée
  2026-09-07).
- Dédupliqué et compté en fréquence, `min_freq` appliqué → liste de
  `CandidateTerm` avec un score placeholder = fréquence brute.

**2. Choix de l'extracteur** — `loterre_extract_cli.py:126-162`
- Avec `--extractor embed`, on exige `--dict` (chemin du dictionnaire JSONL
  cible) — sinon erreur explicite. `embed` n'est **jamais** choisi
  automatiquement par `auto` (auto ne bascule qu'entre ncvalue/graph).

**3. Chargement du vocabulaire cible** — `load_vocabulary_terms()` dans
`loterre_embed.py:54-73`
- Lit le dictionnaire JSONL du vocabulaire (format `label`/`pattern`/`id`/`pref`).
- Dédupliqué par `id` (un concept a souvent plusieurs lignes = variantes de
  surface) → une liste de libellés préférés (`pref`) uniques.

**4. Chargement du modèle** — `get_embed_model()`, `loterre_embed.py:36-51`
- `paraphrase-multilingual-MiniLM-L12-v2` via `sentence-transformers`,
  chargé une seule fois (`lru_cache`), en mode 100% local
  (`HF_HUB_OFFLINE=1`).

**5. Encodage du vocabulaire cible** — `embed_vocabulary_terms()`,
`loterre_embed.py:83-88`
- Chaque terme `pref` du vocabulaire → un vecteur (encodage batché), puis
  normalisation L2 ligne par ligne (`_normalize_rows`).

**6. Scoring des candidats** — `score_candidates_embed()`,
`loterre_embed.py:91-116`
- Chaque candidat (le texte de son span, pas son lemme) est encodé et
  normalisé de la même façon.
- Similarité cosinus = produit matriciel
  `candidats_normalisés @ vocab_normalisé.T` → matrice
  (n_candidats × n_termes_vocab).
- **Score retenu = le max par ligne, pas la moyenne** : distance au terme le
  **plus proche** du vocabulaire (plus proche voisin), pas à un centroïde
  global. Choix documenté et validé empiriquement : un centroïde brouille
  des vocabulaires hétérogènes (ex. X64 mélange des noms de langues à un mot
  et des notions linguistiques abstraites multi-mots) et favorise
  mécaniquement les candidats courts.
- Clip `[-1, 1]` (artefact float32 : un candidat identique à un terme du
  vocabulaire peut donner `1.0000002`).
- Tri décroissant par score, départagé par nombre de tokens décroissant à
  score égal (évite que les unitermes, souvent à score 1.0 exact, masquent
  systématiquement les multitermes équivalents par un tri stable).

**7. Signal structurel secondaire** — `_attach_structural_signal()`,
`loterre_extract_cli.py`
- Calculé automatiquement dès que `extractor == "embed"`, sur les mêmes
  candidats déjà scorés à l'étape 6.
- Recalcule un score **C-value ou PositionRank** (même bascule "auto" selon
  le volume de corpus que le choix normal d'extracteur) — un signal
  indépendant du vocabulaire cible, qui juge un candidat sur sa propre
  forme/fréquence dans le corpus plutôt que sur sa proximité à un terme
  connu.
- Stocké dans des champs **séparés** (`structural_score`/`structural_rule`/
  `structural_rank`, rang 1 = le plus fort) — ne touche jamais `score`/`rule`,
  qui restent le signal embed utilisé pour le tri principal et
  `--embed-threshold`.
- Raison d'être : un candidat loin de tout terme du vocabulaire a un score
  embed bas par construction, même s'il est linguistiquement/statistiquement
  un vrai terme de domaine — c'est justement le genre de candidat qu'on
  voudrait proposer en enrichissement. Voir
  `planification/planif_extraction_terminologique.md` §8 (Option 3) pour la
  réflexion complète et `planification/analyse_benchmarks_extraction.md`
  pour les chiffres.

**8. Filtre optionnel** — `--embed-threshold` (défaut 0.0 = pas de filtre) :
retire les candidats sous le seuil, appliqué après le scoring, dans
`loterre_extract_cli.py` (mode `extract` simple).

**9. Croisement avec l'annotateur (mode `extract_annotate` uniquement)** —
`run_extract_annotate_mode()`, `loterre_cli.py:209-238`
- Le moteur d'annotation v1.0 tourne en parallèle sur le même corpus.
- `cross_reference_candidates()` marque chaque candidat `in_vocabulary=True/False`
  + `uri`/`pref` si trouvé, par correspondance exacte de span
  `(doc_id, start, end)` — pas un simple chevauchement, pour éviter qu'un
  candidat composé hérite à tort de l'URI d'un sous-terme qu'il contient.

**10. Suggestions — deux niveaux, jamais fusionnés** — `loterre_cli.py`
- Seulement si `extractor == "embed"` (le score embed n'a de sens comparable
  à un seuil de similarité que pour cet extracteur), et seulement pour un
  candidat **absent** du vocabulaire (`in_vocabulary is False`).
- **Niveau 1** : `enrichment_suggestion = score >= --enrichment-threshold`
  (défaut **0.95**, recalibré empiriquement pour le plus-proche-voisin —
  l'ancien défaut 0.5 datait du centroïde et signalait ~77% des candidats
  X64 comme suggestions, beaucoup trop bruité).
- **Niveau 2** : `enrichment_suggestion_structural = True` si le candidat
  n'est **pas** déjà en niveau 1, **et** que `structural_rank` est dans le
  top `--structural-top-pct` (défaut **2%**, favorise la précision) du
  classement structurel de l'étape 7 — un candidat loin du seed mais
  statistiquement fort. Catégorie **strictement séparée** de
  `enrichment_suggestion` (jamais les deux `True` en même temps) : pas de
  score composite, pour ne pas réintroduire le bruit que le passage
  centroïde → plus proche voisin avait justement filtré, et pour que le
  curateur garde une confiance différenciée entre les deux listes.

## Ce que ça donne concrètement

Un candidat qui est déjà dans le vocabulaire (`in_vocabulary=True`) n'a pas
besoin d'`embed` pour être identifié — c'est le rôle de l'étape 9. `embed`
sert spécifiquement à **trier les absents**, en deux temps : ceux très
proches (≥0.95) d'un terme déjà connu remontent en `enrichment_suggestion`
(haute confiance), ceux plus loin mais statistiquement forts remontent en
`enrichment_suggestion_structural` (à vérifier) — les deux à valider par un
curateur humain, cohérent avec l'objectif produit "mise à jour de ressource"
documenté dans `CLAUDE.md`. Voir `docs/curation_guide.md` pour la consigne de
travail détaillée du curateur et le choix de méthode selon le contexte.

**Chiffres mesurés sur ACTER (2026-09-07, seuils de production actuels)** :

| | Precision | Rappel | F1 |
|---|---:|---:|---:|
| `enrichment_suggestion` seul | 0.858 | 0.127 | 0.222 |
| `enrichment_suggestion` + `enrichment_suggestion_structural` | 0.568 | 0.232 | 0.329 |

Le niveau 2 relève le rappel de +83% relatif au prix d'une précision qui
tombe à ~0.57 — un compromis délibéré (voir `docs/curation_guide.md`), pas un
défaut à corriger. Détail complet, y compris le balayage de
`--structural-top-pct` (2 à 30%), dans
`planification/analyse_benchmarks_extraction.md`.

**Limite résiduelle non résolue** : le rappel reste plafonné par l'étape 1
(extraction de candidats, noun chunks + filtres POS) — un terme dont la
forme de surface n'est jamais capturée comme candidat (acronyme isolé, forme
très rare) n'atteint aucun des deux niveaux de suggestion, quel que soit le
scoring en aval.
