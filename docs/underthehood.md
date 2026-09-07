# Under the hood — `--extractor embed`

Déroulé pas à pas du scoring par embeddings (Phase 5, v2.0), du texte brut à
la suggestion d'enrichissement. `--extractor embed` intervient dans le mode
`extract_annotate` : il ne remplace pas l'extraction de candidats, il
remplace seulement leur **scoring** — classer les candidats par proximité
sémantique à un vocabulaire Loterre cible plutôt que par fréquence (C-value)
ou par centralité dans le texte (PositionRank).

## Étape par étape

**1. Extraction des candidats (indépendante de l'extracteur)** —
`loterre_extract_cli.py:79-123`
- spaCy tourne sur le corpus (`nlp.pipe`), un `doc` par ligne du JSONL
  d'entrée.
- Chaque `noun_chunk` est nettoyé en bordure (`clean_chunk_span` : retire
  DET/PRON/ADP/ponctuation/élisions FR mal taguées).
- Filtré par `is_valid_candidate` (longueur, POS de contenu NOUN/PROPN/ADJ,
  pas 100% stopwords, pas de ponctuation).
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

**7. Filtre optionnel** — `--embed-threshold` (défaut 0.0 = pas de filtre) :
retire les candidats sous le seuil, appliqué après le scoring, dans
`loterre_extract_cli.py` (mode `extract` simple).

**8. Croisement avec l'annotateur (mode `extract_annotate` uniquement)** —
`run_extract_annotate_mode()`, `loterre_cli.py:209-238`
- Le moteur d'annotation v1.0 tourne en parallèle sur le même corpus.
- `cross_reference_candidates()` marque chaque candidat `in_vocabulary=True/False`
  + `uri`/`pref` si trouvé, par correspondance exacte de span
  `(doc_id, start, end)` — pas un simple chevauchement, pour éviter qu'un
  candidat composé hérite à tort de l'URI d'un sous-terme qu'il contient.

**9. Suggestion d'enrichissement** — `loterre_cli.py:223-230`
- Seulement si `extractor == "embed"` (le score n'a de sens comparable à un
  seuil de similarité que pour cet extracteur).
- Pour chaque candidat **absent** du vocabulaire (`in_vocabulary is False`) :
  `enrichment_suggestion = score >= --enrichment-threshold` (défaut **0.95**,
  recalibré empiriquement pour le plus-proche-voisin — l'ancien défaut 0.5
  datait du centroïde et signalait ~77% des candidats X64 comme suggestions,
  beaucoup trop bruité).

## Ce que ça donne concrètement

Un candidat qui est déjà dans le vocabulaire (`in_vocabulary=True`) n'a pas
besoin d'`embed` pour être identifié — c'est le rôle de l'étape 8. `embed`
sert spécifiquement à **trier les absents** : ceux très proches (≥0.95) d'un
terme déjà connu du vocabulaire sont remontés comme candidats plausibles à
l'ajout (`enrichment_suggestion=True`), à valider par un curateur humain —
cohérent avec l'objectif produit "mise à jour de ressource" documenté dans
`CLAUDE.md`.

**Limite connue** (sujet de la réflexion suspendue du 2026-09-04, voir
`planification/planif_extraction_terminologique.md` §8) : ce mécanisme a un
rappel bas (0.17–0.34 sur ACTER) — un terme pertinent mais
lexicalement/sémantiquement éloigné de tout terme déjà présent dans le
vocabulaire (donc justement le genre de terme qu'on voudrait détecter pour
enrichir la ressource) obtient un score de similarité faible et n'est jamais
remonté.
