# Under the hood — extraction terminologique et scoring des candidats

Déroulé pas à pas du texte brut aux candidats scorés, pour les sous-commandes
`extract`/`extract_annotate` (v2.0) :

1. **Étapes communes** aux trois méthodes de scoring — extraction des
   candidats, choix de la méthode, croisement avec le vocabulaire cible
2. **Méthode C-value** (`--extractor ncvalue`) — corpus volumineux
3. **Méthode PositionRank** (`--extractor graph`) — corpus courts
4. **Méthode embed** (`--extractor embed`) — similarité à un vocabulaire
   cible, avec son signal structurel secondaire et ses trois niveaux de
   suggestion d'enrichissement

Ce document couvre uniquement le **mécanisme technique** (le code, la
formule, le pourquoi d'un choix). Pour la consigne d'usage — quand choisir
quelle méthode, comment un curateur doit traiter les suggestions produites —
voir `docs/curation_guide.md`.

Le mode `annotate` (recherche dans un vocabulaire via pattern/lemme/surface +
Trie) est un mécanisme **complètement différent**, indépendant de
l'extraction de candidats décrite ici — voir `docs/README.md` §7 à 9 pour son
fonctionnement détaillé.

## Étapes communes à toutes les méthodes

**1. Extraction des candidats (indépendante de l'extracteur)** —
`loterre_extract_cli.py:79-123`
- spaCy tourne sur le corpus, un `doc` par ligne du JSONL
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
  `CandidateTerm` avec un score placeholder = fréquence brute. Chaque
  candidat garde aussi ses `occurrences` (offsets caractères par `doc_id`),
  réutilisées par le croisement vocabulaire (étape 3) et par le scoring
  PositionRank (position dans le document).

**2. Choix de l'extracteur** — `score_extracted_candidates()`,
`loterre_extract_cli.py:190-228`
- `--extractor auto` (défaut) bascule entre `ncvalue` et `graph` selon le
  volume : `graph` si `total_tokens < --extractor-auto-threshold` (défaut
  **50000**), sinon `ncvalue`. `auto` **ne bascule jamais** vers `embed`.
- Avec `--extractor embed`, on exige `--dict` (chemin du dictionnaire JSONL
  cible) — sinon erreur explicite : c'est le seul extracteur qui a besoin
  d'un vocabulaire cible pour fonctionner.

**3. Croisement avec l'annotateur (mode `extract_annotate` uniquement,
indépendant de l'extracteur)** — `run_extract_annotate_mode()`,
`loterre_cli.py:224-266`, `cross_reference_candidates()` dans
`loterre_extract_cli.py:231-264`
- Le moteur d'annotation v1.0 tourne en parallèle sur le même corpus, quel
  que soit l'extracteur utilisé pour scorer les candidats.
- `cross_reference_candidates()` marque chaque candidat `in_vocabulary=True/False`
  + `uri`/`pref` si trouvé, par correspondance exacte de span
  `(doc_id, start, end)` — pas un simple chevauchement, pour éviter qu'un
  candidat composé hérite à tort de l'URI d'un sous-terme qu'il contient.
- Cette étape est **la même quelle que soit la méthode de scoring**
  (`ncvalue`/`graph`/`embed`) : `in_vocabulary`/`uri`/`pref` sont toujours
  renseignés en mode `extract_annotate`. Seules les suggestions
  d'enrichissement (`enrichment_suggestion_embed`/`enrichment_suggestion_structural`/
  `enrichment_suggestion_specificity`, voir méthode embed ci-dessous) sont
  réservées à `--extractor embed`, car le score `ncvalue`/`positionrank` n'a
  pas de seuil de similarité comparable à un vocabulaire.

---

## Méthode C-value (`--extractor ncvalue`)

Algorithme de Frantzi et al. (1998), implémenté dans `src/loterre_cvalue.py`
— indépendant de spaCy et du moteur d'annotation (règle Phase 0.5). Pertinent
sur corpus volumineux (> ~50 000 tokens), où les fréquences de candidats sont
statistiquement fiables (voir `docs/README.md` §5.1 pour le choix selon le
volume).

**0. Filtre de spécificité optionnel (`--specificity-filter-pctl`)** —
`filter_by_specificity()`, `src/loterre_specificity.py`, appelé dans
`loterre_extract_cli.py:main()` **avant** le scoring C-value ci-dessous.
- Mesure de "Weirdness Ratio" (TermSuite, contraste de fréquence entre le
  corpus analysé et une référence de "langue générale",
  `resources/termsuite_general_language/{en,fr}/general-language.txt`) :
  un mot beaucoup plus fréquent dans le corpus qu'en langue générale est
  spécifique au domaine, un mot aussi fréquent dans les deux est du
  vocabulaire générique. Score par candidat = moyenne géométrique du ratio
  sur ses mots de contenu (NOUN/PROPN/ADJ/VERB/ADV), en excluant les
  mots-outils adjectivaux/adverbiaux (`_GENERIC_ADJ_EN`/`_GENERIC_ADV_EN`,
  absents de la table de référence — sans cette exclusion ils sont lus à
  tort comme "jamais vus en langue générale" = très spécifiques, mesuré sur
  "other hand" vs "one hand").
- **Paramètre manuel, pas de calibrage automatique par corpus** :
  `--specificity-filter-pctl` vaut **0 par défaut (désactivé)** — comme
  `--cvalue-threshold`/`--structural-top-pct`, l'utilisateur doit passer une
  valeur explicitement pour l'activer. Retire les N% de candidats les moins
  spécifiques **du pool entier**, avant que `build_containment_map()`
  (ci-dessous) ne tourne dessus.
- Calibré sur ACTER le 2026-09-11, `--extractor ncvalue` uniquement :
  balayage 0/10/.../70% — **40% est un pic net** (F1 top-N=n_gold_terms
  0.397→0.447, top-N=1.5× 0.455→0.518), un premier essai à 50% (déjà passé
  le pic) donnait un résultat mitigé. Voir
  `planification/analyse_benchmarks_extraction.md` pour le détail complet.
- **Jamais testé positivement avec `--extractor graph`** : un filtrage à
  50% dégradait le F1 de PositionRank à toute profondeur testée (pas
  re-testé aux autres seuils, l'effort a été concentré sur `ncvalue` où le
  signal était concluant) — ne pas combiner avec `graph`/`auto` sur corpus
  court, aucun garde-fou code ne l'empêche.
- Aucun vocabulaire cible nécessaire (contrairement au signal structurel
  d'`embed` ci-dessous) — utilisable en mode `extract` "à froid".

**1. Carte d'emboîtement** — `build_containment_map()`,
`loterre_cvalue.py:25-44`
- Pour chaque candidat, liste tous les candidats **plus longs** qui le
  contiennent comme sous-séquence contiguë de lemmes — ex. `"memory"` est
  emboîté dans `"controlled memory assessment"` si ce dernier existe comme
  candidat séparé.

**2. Score C-value** — `c_value()`, `loterre_cvalue.py:47-61`
- Formule : `log2(longueur) * (fréquence − somme(fréquences des termes plus
  longs qui le contiennent) / nombre de ces termes plus longs)`.
- Intuition : un candidat fréquent gagne un bon score, mais s'il n'apparaît
  **que** comme fragment d'un terme composé plus long et lui-même fréquent
  (ex. `"machine"` presque toujours à l'intérieur de `"machine learning"`),
  sa fréquence "propre" est quasiment entièrement absorbée par le terme
  englobant — son C-value chute d'autant. Un candidat qui n'est jamais
  emboîté garde toute sa fréquence brute (pondérée par `log2(longueur)`).
- **Toujours 0 pour un terme à un seul token** (`log2(1) = 0` par
  construction de la formule) — voir l'étape 3 pour le repli mono-token.

**3. Repli mono-token** — `single_token_score()`, `loterre_cvalue.py:64-71`
- C-value ne peut rien dire d'un candidat à un seul mot (formule nulle par
  construction) ; repli sur la fréquence normalisée par la fréquence max du
  corpus (`rule="freq_single_token"` au lieu de `"cvalue"` dans la sortie).
- **Échelle non garantie comparable** aux scores C-value multi-tokens — un
  score de 0.5 en `freq_single_token` n'est pas comparable à un score de 0.5
  en `cvalue` ; seulement comparable entre candidats mono-tokens entre eux.

**4. Tri** — `score_candidates()`, `loterre_cvalue.py:74-90`
- Un seul passage : construit la carte d'emboîtement, calcule le score
  (C-value ou repli) pour chaque candidat, trie par score décroissant.
- `--cvalue-threshold` (optionnel, défaut 0 = pas de filtre) retire les
  candidats sous le seuil après ce tri, uniquement en mode `extract` simple.

---

## Méthode PositionRank (`--extractor graph`)

Algorithme de Florescu & Caragea (2017), implémenté dans
`src/loterre_positionrank.py` — un PageRank biaisé par la position des mots
dans le document, en pur Python (pas de dépendance graphe externe type
networkx). Pertinent sur corpus courts (< ~10 000 tokens, voire un document
unique) où les statistiques de fréquence de C-value ne sont pas fiables.

**1. Graphe de co-occurrence** — `build_cooccurrence_graph()`,
`loterre_positionrank.py:22-49`
- Seuls les mots de contenu (NOUN/PROPN/ADJ) deviennent des nœuds du graphe.
- Deux mots de contenu sont reliés (arête pondérée, cumulée sur tout le
  corpus) s'ils apparaissent à moins de `window` mots de contenu l'un de
  l'autre (défaut **4**).
- `position_weight[lemme]` = somme de `1/(position+1)` sur toutes les
  occurrences du lemme — un mot qui apparaît tôt dans un document (position
  0, 1, 2…) pèse plus qu'un mot qui n'apparaît que loin dans le texte.

**2. PageRank biaisé par la position** — `position_rank()`,
`loterre_positionrank.py:52-89`
- Vecteur de personnalisation = `position_weight` normalisé (au lieu d'une
  distribution uniforme comme le PageRank classique) : le score de chaque
  mot est tiré vers le haut s'il apparaît tôt et souvent dans le corpus, pas
  seulement s'il est central dans le graphe de co-occurrence.
- Itération de puissance (`alpha=0.85`, jusqu'à 50 itérations ou convergence
  `tol=1e-6`) : à chaque tour, le score d'un mot dépend des scores de ses
  voisins de co-occurrence, pondérés par la force de l'arête qui les relie.

**3. Score d'un candidat** — `score_candidates_positionrank()`,
`loterre_positionrank.py:92-100`
- Le score d'un candidat multi-tokens = **somme** des scores PositionRank de
  chacun de ses lemmes constitutifs (pas une probabilité jointe de la
  séquence) — `rule="positionrank"`.
- **Limite à garder en tête** : deux mots individuellement forts (fréquents,
  précoces) donnent un candidat combiné fort même si la phrase elle-même
  (leur co-occurrence en tant que groupe) est rare — le score ne valide pas
  directement que le groupement des mots forme un terme figé, seulement que
  ses composants sont individuellement importants dans le texte.
- Tri par score décroissant, même convention que `loterre_cvalue.score_candidates`.

---

## Méthode embed (`--extractor embed`) — scoring par similarité au vocabulaire cible

Phase 5 (v2.0), implémenté dans `src/loterre_embed.py`. Contrairement à
`ncvalue`/`graph`, ce scoring **nécessite** un vocabulaire cible (`--dict`) :
il classe les candidats par proximité sémantique à ce vocabulaire, pas par
fréquence/centralité dans le corpus, et calcule en complément un second
signal structurel (étape 3 ci-dessous) pour rattraper les candidats loin du
vocabulaire.

**1. Chargement du vocabulaire cible** — `load_vocabulary_terms()` dans
`loterre_embed.py:54-73`
- Lit le dictionnaire JSONL du vocabulaire (format `label`/`pattern`/`id`/`pref`).
- Dédupliqué par `id` (un concept a souvent plusieurs lignes = variantes de
  surface) → une liste de libellés préférés (`pref`) uniques.

**2. Chargement du modèle** — `get_embed_model()`, `loterre_embed.py:36-51`
- `paraphrase-multilingual-MiniLM-L12-v2` via `sentence-transformers`,
  chargé une seule fois (`lru_cache`), en mode 100% local
  (`HF_HUB_OFFLINE=1`).

**3. Encodage du vocabulaire cible** — `embed_vocabulary_terms()`,
`loterre_embed.py:83-88`
- Chaque terme `pref` du vocabulaire → un vecteur (encodage batché), puis
  normalisation L2 ligne par ligne (`_normalize_rows`).

**4. Scoring des candidats** — `score_candidates_embed()`,
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

**5. Signal structurel secondaire** — `_attach_structural_signal()`,
`loterre_extract_cli.py:146-187`
- Calculé automatiquement dès que `extractor == "embed"`, sur les mêmes
  candidats déjà scorés à l'étape 4.
- Recalcule un score **C-value ou PositionRank** (mêmes méthodes que
  ci-dessus, même bascule "auto" selon le volume de corpus que le choix
  normal d'extracteur, étape 2) — un signal indépendant du vocabulaire
  cible, qui juge un candidat sur sa propre forme/fréquence dans le corpus
  plutôt que sur sa proximité à un terme connu.
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

**6. Filtre optionnel** — `--embed-threshold` (défaut 0.0 = pas de filtre) :
retire les candidats sous le seuil, appliqué après le scoring, dans
`loterre_extract_cli.py` (mode `extract` simple).

**7. Suggestions — trois niveaux, jamais fusionnés** — `loterre_cli.py`,
`run_extract_annotate_mode()`
- Seulement si `extractor == "embed"` (le score embed n'a de sens comparable
  à un seuil de similarité que pour cet extracteur), et seulement pour un
  candidat **absent** du vocabulaire (`in_vocabulary is False`, déjà
  renseigné à l'étape commune 3).
- **Niveau 1** : `enrichment_suggestion_embed = score >= --enrichment-threshold`
  (défaut **0.95**, recalibré empiriquement pour le plus-proche-voisin —
  l'ancien défaut 0.5 datait du centroïde et signalait ~77% des candidats
  X64 comme suggestions, beaucoup trop bruité).
- **Niveau 2** : `enrichment_suggestion_structural = True` si le candidat
  n'est **pas** déjà en niveau 1, **et** que `structural_rank` est dans le
  top `--structural-top-pct` (défaut **2%**, favorise la précision) du
  classement structurel de l'étape 5 — un candidat loin du seed mais
  statistiquement fort.
- **Niveau 3** (`--specificity-top-pct`, **défaut 0.0 = désactivé**,
  2026-09-11) : `enrichment_suggestion_specificity = True` si le candidat
  n'est **ni** niveau 1 **ni** niveau 2, et que `specificity_rank` (Weirdness
  Ratio vs langue générale, `loterre_specificity.score_candidates_specificity`
  — toujours calculé pour `embed`, coût négligeable, aucun modèle) est dans
  le top `--specificity-top-pct`. Contrairement au niveau 2, **pas actif par
  défaut** : précision isolée mesurée ~0.27-0.30 sur ACTER (2026-09-11),
  nettement plus bruitée que le niveau 2 (~0.64) — un choix explicite du
  curateur (accepter plus de bruit pour plus de rappel), pas un défaut
  raisonnable. Si activé, **10%** est la valeur mesurée utile (l'union
  niveau 2 + niveau 3 à 10% porte le F1 combiné de 0.270 à 0.314 sur ACTER,
  voir `planification/analyse_benchmarks_extraction.md`).
- Les trois catégories sont **strictement séparées** (jamais deux `True` en
  même temps) : pas de score composite, pour ne pas réintroduire le bruit
  que le passage centroïde → plus proche voisin avait justement filtré, et
  pour que le curateur garde une confiance différenciée entre les listes —
  chacune avec un profil de précision propre et documenté.

### Le dénominateur du top `--structural-top-pct` inclut les candidats déjà connus

`structural_rank` (étape 5) est calculé sur **tous** les candidats extraits,
avant même que `in_vocabulary` soit connu (le croisement avec le vocabulaire
a lieu à l'étape commune 3, avant le scoring embed dans le déroulé
`extract_annotate`, mais le calcul du rang lui-même à l'étape 5 ne filtre pas
sur ce statut). Et `structural_top_n` (`loterre_cli.py`,
`run_extract_annotate_mode`) est un pourcentage de `n_total = len(candidates)`
— ce total inclut aussi les candidats qui s'avéreront `in_vocabulary=True`,
pas seulement les absents éligibles à une suggestion.

Ce n'est pas un oubli : c'est délibéré et ça rend le seuil **plus strict**,
pas plus permissif. Les termes déjà dans le vocabulaire sont typiquement les
plus fréquents/centraux du corpus (un vocabulaire curé capture en priorité le
cœur terminologique du domaine) — ils obtiennent donc naturellement un bon
score C-value/PositionRank et occupent une partie des meilleurs rangs. En les
laissant dans le classement, un candidat absent doit être structurellement
**aussi fort que les termes déjà canoniques du vocabulaire** pour entrer dans
le top N — pas seulement se distinguer du bruit des autres candidats absents.
L'alternative (calculer le pourcentage uniquement parmi les candidats
absents) donnerait une taille de liste plus prévisible, mais accepterait des
candidats seulement forts *par rapport au reste du bruit*, sans les comparer
aux vrais termes du domaine — moins aligné avec l'esprit "favorise la
précision" du défaut `--structural-top-pct 2%`.

`scripts/evaluation/acter_eval.py` (`evaluate_domain_lang_structural_signal`)
reproduit exactement cette même sémantique (`n_total = len(candidates)`,
candidats seed inclus) — les chiffres Precision/Rappel/F1 mesurés ci-dessous
intègrent donc déjà cet effet ; ce n'est pas un biais caché non calibré.

### Ce que ça donne concrètement (spécifique à la méthode embed)

Un candidat qui est déjà dans le vocabulaire (`in_vocabulary=True`) n'a pas
besoin d'`embed` pour être identifié — c'est le rôle de l'étape commune 3.
`embed` sert spécifiquement à **trier les absents**, en trois temps : ceux
très proches (≥0.95) d'un terme déjà connu remontent en
`enrichment_suggestion_embed` (haute confiance), ceux plus loin mais
statistiquement forts remontent en `enrichment_suggestion_structural` (à
vérifier), et — si `--specificity-top-pct` est explicitement activé — ceux
plus loin encore mais rares par rapport à la langue générale remontent en
`enrichment_suggestion_specificity` (exploratoire, plus bruité) — les trois
à valider par un curateur humain, cohérent avec l'objectif produit "mise à
jour de ressource" documenté dans `CLAUDE.md`. Voir `docs/curation_guide.md`
pour la consigne de travail détaillée du curateur et le choix de méthode
selon le contexte.

**Chiffres mesurés sur ACTER (2026-09-07, seuils de production actuels)** :

| | Precision | Rappel | F1 |
|---|---:|---:|---:|
| `enrichment_suggestion_embed` seul | 0.858 | 0.127 | 0.222 |
| `enrichment_suggestion_embed` + `enrichment_suggestion_structural` | 0.568 | 0.232 | 0.329 |

**Niveau 3 — chiffres mesurés séparément sur ACTER (2026-09-11, script ad hoc, pas `acter_eval.py`, méthodologie comparable mais pas identique — voir `planification/analyse_benchmarks_extraction.md` pour le détail)** :

| | Precision | Rappel | F1 |
|---|---:|---:|---:|
| `enrichment_suggestion_embed` seul | 0.899 | 0.114 | 0.203 |
| + `enrichment_suggestion_structural` (2%) | 0.641 | 0.171 | 0.270 |
| + `enrichment_suggestion_structural` (2%) + `enrichment_suggestion_specificity` (10%) | 0.492 | 0.231 | **0.314** |
| `enrichment_suggestion_specificity` isolé (candidats **uniquement** niveau 3, ni 1 ni 2) | **0.27–0.30** | 0.02–0.06 | 0.04–0.10 |

Le niveau 3 capte un angle mort différent du niveau 2 (rareté par rapport à
la langue générale, pas force statistique/positionnelle dans le corpus) —
leur union récupère plus de vrais termes que chacun seul (rappel
0.171→0.231), mais la précision propre du niveau 3 (dernière ligne) est
nettement plus faible que celle du niveau 2 — **c'est pour ça qu'il reste
désactivé par défaut**, contrairement au niveau 2.

Le niveau 2 relève le rappel de +83% relatif au prix d'une précision qui
tombe à ~0.57 — un compromis délibéré (voir `docs/curation_guide.md`), pas un
défaut à corriger. Détail complet, y compris le balayage de
`--structural-top-pct` (2 à 30%), dans
`planification/analyse_benchmarks_extraction.md`.

**Limite résiduelle non résolue, commune à toutes les méthodes** : le rappel
reste plafonné par l'étape commune 1 (extraction de candidats, noun chunks +
filtres POS) — un terme dont la forme de surface n'est jamais capturée comme
candidat (acronyme isolé, forme très rare) n'atteint aucun score, quelle que
soit la méthode choisie en aval.
