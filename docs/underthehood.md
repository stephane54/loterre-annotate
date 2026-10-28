# Under the hood — extraction terminologique, scoring des candidats et annotation

Déroulé pas à pas du texte brut aux candidats scorés, pour les sous-commandes
`extract`/`extract_annotate` (v2.0) :

1. **Étapes communes** aux trois méthodes de scoring — extraction des
   candidats, choix de la méthode, croisement avec le vocabulaire cible
2. **Méthode C-value** (`--extractor ncvalue`) — corpus volumineux
3. **Méthode PositionRank** (`--extractor graph`) — corpus courts
4. **Méthode embed** (`--extractor embed`) — similarité à un vocabulaire
   cible, avec son signal structurel secondaire et ses trois niveaux de
   suggestion d'enrichissement
5. **Rapport d'analyse** (`extract_annotate --report`) — chiffres clés,
   annotation et extraction, et couverture du vocabulaire par thème
   (expérimental)
6. **Annotation** (`annotate`) — représentation du dictionnaire en mémoire,
   mise en cache des index, chemins de matching, filtrage qualité,
   auto-profiling

Ce document couvre uniquement le **mécanisme technique** (le code, la
formule, le pourquoi d'un choix). Pour la consigne d'usage — quand choisir
quelle méthode, comment un curateur doit traiter les suggestions produites —
voir `docs/curation_guide.md`.

Le mode `annotate` (recherche dans un vocabulaire via pattern/lemme/surface +
Trie) est un mécanisme **complètement différent**, indépendant de
l'extraction de candidats — il est décrit dans la dernière partie de ce
document. Les résultats mesurés et les protocoles d'évaluation sont dans
`docs/evaluation.md`.

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
  2026-09-07). Enfin, le candidat doit contenir **au moins deux lettres**
  (2026-10-05) : sur du texte extrait de PDF, spaCy étiquette NOUN/PROPN des
  symboles et lettres isolées ("-", "–", "©", "n", "C") qui passaient tous
  les autres filtres et envahissaient les listes de suggestion ; les sigles
  courts ("PM", "IC") et "vitamine D" restent acceptés. Effet neutre sur
  ACTER (F1 ±0,002).
- Pas uniquement des mots outils, en français **ou** en anglais (2026-10-09,
  `_only_function_words`) : le filtre `is_stop` de spaCy ne connaît que la
  langue du modèle, et les résumés anglais d'un corpus français donnaient
  des candidats « of the », « and », « this ». Liste spaCy FR + EN, plus
  les élisions (« d », « l », « qu ») et « -ci »/« -là » ; un mot en
  majuscules d'au moins deux lettres compte comme sigle (« NO », « OR »),
  sauf « OF », « THE », « AND »… des titres en capitales. ACTER neutre.
- Dédupliqué et compté en fréquence, `min_freq` appliqué → liste de
  `CandidateTerm` avec un score placeholder = fréquence brute. Chaque
  candidat garde aussi ses `occurrences` (offsets caractères par `doc_id`),
  réutilisées par le croisement vocabulaire (étape 3) et par le scoring
  PositionRank (position dans le document).
- **Quelles occurrences ?** Par défaut, seulement les endroits où spaCy a
  produit exactement ce groupe nominal (`_register_span`, `term =
  span.text`) : « heart failure » n'est pas compté dans « chronic heart
  failure patients », et « Heart failure » est un autre candidat que
  « heart failure ». Avec **`--respot-occurrences`** (`_respot_occurrences`,
  appliqué avant `min_freq`) :
  1. les variantes de casse d'un candidat sont fusionnées (forme retenue :
     la plus fréquente comme groupe nominal, la minuscule à égalité) ;
  2. toutes les occurrences de son texte sont repérées dans le corpus,
     insensible à la casse, aux bornes de tokens (`\w+|[^\w\s]`), en une
     passe par document grâce à un trie sur les tokens en minuscules —
     termes emboîtés et chevauchants tous comptés ;
  3. la fréquence devient le nombre d'occurrences repérées.

  C'est aussi ce que la formule C-value suppose (un terme court compte ses
  apparitions dans les termes plus longs, que la formule soustrait
  ensuite). Mesuré sur ACTER le 2026-10-09 : gain sur toutes les méthodes,
  précision comprise — c'était l'essentiel de l'avance de TermSuite (voir
  `docs/evaluation.md` §1.1). Option explicite, défaut désactivé.

  Deux garde-fous, ajoutés après un premier essai sur RevueESR où le
  repérage couvrait tout le texte (1 h 36 au lieu de 28 min, liste 2
  envahie de « of the », « pas d ») :
  - le repérage ne se fait qu'**à l'intérieur des groupes nominaux** de
    chaque document (bornes collectées pendant le passage spaCy) ;
  - seuls les candidats qui atteignent déjà `min_freq` comme groupes
    nominaux y participent.

  Avec eux : pas de surcoût sur RevueESR, liste 2 propre en tête. Le gain
  est token-level (plus d'occurrences comptées pour les mêmes termes) : en
  précision par candidat, la liste 1 passe de 0.532 à 0.509 sur ACTER —
  d'où le maintien en option.

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
  défaut** : précision isolée mesurée 0.27 par token / 0.14 par candidat
  sur ACTER, nettement plus bruitée que le niveau 2 (0.39 / 0.23) — un
  choix explicite du curateur (accepter plus de bruit pour plus de rappel),
  pas un défaut raisonnable. Si activé, **10%** est la valeur mesurée utile
  (l'union niveaux 1 + 2 + 3 à 10% porte le F1 combiné de 0.327 à 0.368 sur
  ACTER, voir `planification/analyse_benchmarks_extraction.md`).
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
jour de ressource" du projet. Voir `docs/curation_guide.md`
pour la consigne de travail détaillée du curateur et le choix de méthode
selon le contexte.

**Chiffres mesurés sur ACTER (reproduits le 2026-09-30, seuils de production actuels, seed/holdout 50%)** — listes cumulées (précision token-level, protocole ACTER) :

| | Precision | Rappel | F1 |
|---|---:|---:|---:|
| `enrichment_suggestion_embed` seul | 0.852 | 0.129 | 0.224 |
| + `enrichment_suggestion_structural` (2%) | 0.560 | 0.231 | 0.327 |
| + `enrichment_suggestion_specificity` (10%) | 0.430 | 0.321 | 0.368 |

Chaque liste **prise seule** (candidats de cette liste uniquement — ce que le
curateur relit réellement) :

| Liste | Précision par token | Précision par candidat |
|---|---:|---:|
| `enrichment_suggestion_embed` | 0.852 | 0.528 |
| `enrichment_suggestion_structural` (2%) | 0.391 | 0.231 |
| `enrichment_suggestion_specificity` (10%) | 0.270 | 0.143 |

La précision par token pondère chaque candidat par ses occurrences (et
accepte un recouvrement partiel avec un terme de référence) ; la précision
par candidat compte chaque candidat une fois et exige une correspondance
exacte — voir `docs/curation_guide.md`. Les versions antérieures de ce
document donnaient ~0.57-0.64 pour la précision du niveau 2 : c'était celle
de l'**union** niveaux 1 + 2, pas du niveau 2 seul ; et le tableau du
2026-09-11 (0.899 / 0.641 / 0.314) n'est pas reproductible — voir
`planification/analyse_benchmarks_extraction.md`, entrée 2026-09-29.

Le niveau 2 relève le rappel de +79% relatif (0.129 → 0.231) au prix d'une
liste propre nettement moins précise — un compromis délibéré, pas un défaut
à corriger. Le niveau 3 capte un angle mort différent (rareté par rapport à
la langue générale, pas force statistique/positionnelle dans le corpus) et
relève encore le rappel (0.231 → 0.321), mais sa précision propre est la
plus faible des trois — **c'est pour ça qu'il reste désactivé par défaut**,
contrairement au niveau 2. Dans chaque liste, le tri par `frequency`
décroissante sépare nettement les candidats fiables des douteux (consigne de
relecture dans `docs/curation_guide.md`). Détail complet, y compris le
balayage de `--structural-top-pct` (2 à 30%), dans
`planification/analyse_benchmarks_extraction.md`.

**Limite résiduelle non résolue, commune à toutes les méthodes** : le rappel
reste plafonné par l'étape commune 1 (extraction de candidats, noun chunks +
filtres POS) — un terme dont la forme de surface n'est jamais capturée comme
candidat (acronyme isolé, forme très rare) n'atteint aucun score, quelle que
soit la méthode choisie en aval.

## Rapport d'analyse (`extract_annotate --report`)

Module `src/loterre_report.py` (2026-09-30, élargi le 2026-10-02 ;
`--topic-report` reste accepté comme ancien nom de l'option). Calculé à la
fin d'`extract_annotate`, sur les candidats et les annotations déjà produits,
sans second passage spaCy ni second passage de l'annotateur, **avant**
l'écriture des sorties JSON/CSV (il y ajoute les champs de thème, voir plus
bas). Trois parties :

1. **Synthèse chiffrée** et 2. **annotation / extraction** — comptages
   directs, `compute_summary()` : nombre de documents et de tokens,
   candidats, candidats `in_vocabulary`, annotations, concepts du
   vocabulaire retrouvés (URI distinctes dans les annotations) rapportés au
   nombre de concepts du dictionnaire (identifiants `id` distincts du JSONL),
   documents avec au moins une annotation, histogramme des annotations par
   document, 15 concepts les plus annotés, candidats par longueur (tokens du
   `pattern`), effectifs et 10 suggestions les plus fréquentes de chaque liste.
3. **Couverture par thème — expérimental**, ci-dessous. Ce n'est **pas** une
   méthode de scoring : elle répond à une autre question que les listes de
   suggestion — non pas "ce candidat est-il un bon terme ?" mais "**dans
   quelles zones du corpus le vocabulaire cible manque-t-il de termes ?**".

Champs par candidat liés au rapport et à l'export (JSON et CSV) :
`n_docs` (documents distincts parmi les occurrences, toujours présent),
`nearest_vocab_term` (`--extractor embed` : libellé du vocabulaire qui a
donné `score`, l'argmax de la ligne de similarités dans
`score_candidates_embed()`), `context` (extrait de ±70 caractères autour de
la première occurrence, relu dans le fichier source, `attach_contexts()` de
`loterre_csv_export.py`), et avec `--report` `topic_id` / `topic_label` /
`topic_coverage` (thème principal du candidat, voir étape 2, et couverture
de ce thème). Les champs de thème sont des informations de **rangement**,
pas un score : NMF comme signal de pertinence par candidat a été mesuré et
ne fait pas mieux que la fréquence (`planification/analyse_benchmarks_extraction.md`,
entrée 2026-09-29).

### Étape 1 — Segments

Chaque document est découpé en tranches de 600 caractères (`SEGMENT_CHARS`),
déduites des positions des occurrences de candidats (le texte brut n'est pas
relu). Un segment est l'unité de base : c'est lui qui reçoit un thème et
qu'on déclare "couvert" ou non. 600 caractères ≈ 100 tokens, environ un
paragraphe. Sous 50 segments (`MIN_SEGMENTS`, ~30 000 caractères), la partie
thèmes est omise (le reste du rapport est produit) : trop peu de matière pour
que des thèmes émergent.

### Étape 2 — Thèmes (NMF)

Matrice creuse segments × candidats (nombre d'occurrences de chaque candidat
dans chaque segment, candidats de fréquence ≥ 2, pondération tf-idf),
factorisée par NMF (*Non-negative Matrix Factorization*, scikit-learn) en
W (segments × thèmes) et H (thèmes × candidats), toutes deux positives :

- **thème dominant d'un segment** = la plus forte valeur de sa ligne W ;
- **thème principal d'un candidat** = la plus forte valeur de sa colonne H —
  c'est ce qui range chaque suggestion sous un thème dans le rapport, et
  qui donne `topic_id` / `topic_label` (5 premiers mots de l'étiquette) au
  candidat ;
- **étiquette d'un thème** = ses 10 candidats de plus fort poids dans H.

Nombre de thèmes : `--report-topics`, ou automatique (segments / 30,
borné entre 5 et 30). Graine fixe (résultat reproductible). Les thèmes ne
sont construits qu'à partir des candidats extraits : le vocabulaire cible
n'intervient pas dans leur formation.

Le plafond de 30 a été vérifié a posteriori sur RevueESR (2026-10-08,
`scripts/evaluation/sweep_topics.py`, k = 10 à 50) :

- 30 a la meilleure stabilité (thèmes retrouvés à 0,94 sur des
  sous-échantillons de 80 % des segments) et une cohérence d'étiquettes au
  niveau du plateau 20–30 ;
- au-delà de 30, la cohérence baisse et le thème générique se fragmente en
  petits thèmes qui passent sous le seuil de détection (étape 4) et
  occupent le bas du classement ;
- le constat de couverture ne dépend pas de k : la santé au travail reste
  entre 1 et 1,7 % pour tous les k testés.

La formule segments / 30, qui fixe k sur les corpus de moins de ~900
segments, n'a pas été vérifiée.

### Étape 3 — Couverture par les termes propres du vocabulaire

La couverture est mesurée à partir des **annotations du vocabulaire** (sortie
du moteur d'annotation, déjà calculée par `extract_annotate` pour
`in_vocabulary`), rattachées à leur segment — et non à partir du champ
`in_vocabulary` des candidats. Ce dernier sous-estime la couverture : un
terme reconnu par l'annotateur mais extrait avec un autre empan (inclus dans
un groupe nominal plus long, par exemple) n'est pas marqué. Sur RevueESR/SEN,
cette ancienne mesure désignait à tort le bruit et les maladies vectorielles
comme non couverts, alors que SEN y a "trafic routier" et "virus West Nile".

Seuls comptent les **termes propres** au thème : un terme du vocabulaire est
propre au thème *t* si

```
(annotations du terme dans les segments de t / annotations du terme) /
(segments de t / segments du corpus)  >=  2        (SPECIFIC_LIFT)
```

avec au moins 3 annotations dans le thème (`SPECIFIC_MIN_COUNT`). Sans ce
filtre, quelques termes transversaux présents partout ("risque sanitaire",
"changement climatique" sur RevueESR/SEN) donnaient une couverture moyenne à
des thèmes qui n'avaient aucun terme propre — la santé au travail passait de
14% des segments (tous termes) à 2% (termes propres). Un terme transversal
compte toujours là où il est surreprésenté ("risque sanitaire" pour le thème
évaluation des risques).

**Couverture d'un thème** = part de ses segments (ceux où il domine) qui
contiennent au moins une annotation d'un de ses termes propres. C'est une
mesure **relative** : elle compare les thèmes entre eux, mais n'est pas un
taux de couverture absolu (on ne connaît pas la terminologie complète que
chaque thème devrait contenir).

**Thème générique** (2026-10-07) : NMF range le discours général des
articles ("compte, exemple, mise, place, prise, gestion") dans un grand thème
fourre-tout, dont la couverture est basse par construction et qui
apparaîtrait à tort en tête des zones "mal couvertes". Un thème est marqué
`generic` (et ses candidats `topic_generic=True`) si son poids
(`segment_share`) atteint au moins `GENERIC_SHARE_FACTOR` = 2,5 fois le
poids moyen d'un thème (1 / nombre de thèmes) ; il est alors affiché à part,
hors classement. Calibré sur RevueESR/SEN (30 thèmes) : 13,2% contre 3,3% de
moyenne, thème suivant à 5,1%. Le critère de poids seul suffit : la
spécificité des mots de l'étiquette (rang de Weirdness Ratio) ne distingue
pas ce thème (0,79 contre 0,80 pour la santé au travail, vraie zone peu
couverte).

Limite : la règle ne voit qu'un fourre-tout **d'un seul tenant**. S'il se
scinde en plusieurs petits thèmes, chacun reste sous le seuil et se classe
parmi les « moins couverts ». C'est le cas au-delà de 30 thèmes, et sur
RevueESR depuis le filtre de mots outils (2026-10-09) : deux thèmes de
discours général (« compte, prise, facteurs » ; « mise, France, place »)
passent devant la santé au travail en bas du classement. À lire en
conséquence : un thème du bas dont l'étiquette n'a pas de mot du domaine
est probablement du discours général, pas un sous-domaine mal couvert.

### Sorties

- `RAPPORT.html` : page autonome (aucune ressource externe, utilisable hors
  ligne) — chiffres clés, graphiques de l'annotation et de l'extraction,
  tableaux des suggestions les plus fréquentes, barres de couverture par
  thème (triées du moins au plus couvert, nombre de suggestions par thème),
  explications et détail par thème repliés.
- `RAPPORT.json` : les mêmes données (`summary`, `topics`), pour réutilisation.

`scripts/evaluation/build_report.py` produit le même rapport (et, avec
`--out-csv`, le CSV enrichi) à partir de sorties déjà calculées (JSON
d'`extract_annotate` + JSON du moteur d'annotation), sans relancer le
pipeline.

### Coût et validation

RevueESR (1 549 documents, 53 245 segments, 36 546 candidats) : ~13 s et
~1 Go de RAM. Validation **qualitative uniquement**, sur un seul corpus
(RevueESR/SEN) : zones peu couvertes plausibles (santé au travail, périnatal,
gestion des déchets), thèmes de bruit clairement isolés (en-têtes de revue,
remerciements, adresses, texte mal extrait des PDF). Aucune mesure chiffrée
possible sur ACTER (pas de vocabulaire cible). Pourquoi NMF sert ici mais
pas comme signal par candidat (il ne fait pas mieux que la fréquence) :
`planification/analyse_benchmarks_extraction.md`, entrée 2026-09-29.

## Annotation (`annotate`) — représentation du dictionnaire et matching

Mécanisme du moteur d'annotation (`src/loterre_engine_v9_cli.py`), utilisé
par `annotate` et par la partie croisement d'`extract_annotate`. Les options
réglables (profils, clés `quality.*`) sont décrites dans `docs/README.md`
§7 à §11.

### Représentation interne du dictionnaire

À l'exécution, le dictionnaire JSONL n'est pas interrogé tel quel :
`build_indexes()` le transforme en structures de recherche en mémoire.

- **Tries de séquences** (`SeqTrie`) : chaque forme (libellé, `altLabels`,
  variantes structurelles) est découpée en tokens normalisés et insérée dans
  un trie dont chaque nœud final porte le concept (`label`, `pref`, `uri`).
  Trois tries coexistent — formes de surface, séquences de lemmes des
  libellés, séquences de lemmes issues des motifs. La recherche du plus long
  terme commençant à une position du texte (`iter_longest`) coûte au plus la
  longueur de ce terme, quelle que soit la taille du vocabulaire.
- **Index des motifs POS+lemme par premier lemme** (`pattern_first_idx`) :
  pour chaque position du texte, seules les entrées dont le premier spec
  correspond sont testées ; les entrées sans lemme sur leur premier token
  (`pattern_wildcards`) restent testées partout. Les lemmes des motifs sont
  normalisés une fois pour toutes à la construction (`_norm_lemma`).
- **Sigles mono-token en majuscules**, gardés à part pour la règle
  `surface_upper_exact`.

### Mise en cache des index

Construire ces index demande de lemmatiser tous les libellés avec spaCy :
quelques secondes pour un petit vocabulaire, plusieurs minutes pour les plus
gros (MeSH, ~150 000 entrées). Pour ne pas payer ce coût à chaque appel,
`build_indexes_cached()` les **sérialise sur disque (pickle)** dans
`.loterre_index_cache/` (ou le répertoire désigné par
`LOTERRE_INDEX_CACHE_DIR` / `--index-cache-dir`). La clé de chaque fichier
est un SHA-256 calculé sur :

- le **contenu** du dictionnaire (pas son chemin ni sa date, pour qu'un cache
  produit sur une machine reste valide sur une autre après `dvc pull`) ;
- la langue, le profil de matching et ses paramètres ;
- le nom et la version du modèle spaCy, la version de spaCy ;
- un numéro de format (`INDEX_CACHE_FORMAT_VERSION`, incrémenté quand la
  structure des index change).

Toute modification de l'un de ces éléments produit une nouvelle clé : un
cache périmé n'est jamais réutilisé. L'écriture passe par un fichier
temporaire propre à chaque processus puis un renommage atomique, ce qui
permet à plusieurs workers de remplir le cache en parallèle sans jamais lire
un fichier partiel ; un fichier corrompu ou un répertoire non inscriptible
déclenche simplement une reconstruction, jamais un échec. Le cache est
pré-rempli pour tous les vocabulaires du registre par
`src/warm_index_cache.py` et livré avec les dictionnaires
(`dictionary/.loterre_index_cache/`, ~1,2 Go, suivi par DVC) ; l'image
Docker du webservice le désigne via `LOTERRE_INDEX_CACHE_DIR`.

Caches complémentaires, plus légers :

- **Modes `fast`/`hybrid`** : l'index regex du chemin rapide
  (`src/loterre_fast_path.py`) est mis en cache dans `.loterre_cache/`
  (`--cache-dir`), avec une clé fondée sur le chemin, la date de modification
  et la taille du dictionnaire, plus le mode de casse ; les versions périmées
  d'un même dictionnaire sont supprimées à chaque reconstruction.
- **En mémoire, par processus** (`functools.lru_cache`) : normalisation de
  texte (`normalize_text`, 16 384 entrées), chargement des modèles spaCy
  (`get_nlp`), du modèle d'embeddings (`get_embed_model`) et des tables
  morphologiques (`load_derivation_rules`) — chacun n'est chargé qu'une fois
  par processus.
- **Embeddings du vocabulaire** (`--extractor embed`) : non persistés. Les
  libellés préférés sont encodés à chaque exécution, par lots de 64, en une
  matrice de vecteurs normalisés (un vecteur par concept), ce qui ramène la
  similarité cosinus à un produit matriciel.

### Chemins de matching

**Le pattern compare toujours sur le lemme, indépendamment du flag
`use_lemma`.** Chaque spec du pattern (généré par `build_dictionaries.py`,
un par token du terme source) porte un `lemma` ; `token_matches_spec()`
compare le lemme normalisé du token du texte à celui de la spec — c'est le
comportement intrinsèque du chemin `pattern`, pas une passe optionnelle.
Concrètement : un terme au singulier dans le dictionnaire matche déjà les
formes fléchies du texte (pluriel, accord) via `pattern` seul, même en
profil `entity_strict` (`use_lemma: false`).

Le flag `use_lemma` ne contrôle qu'une passe *distincte* :
`lemma_pattern_seq`/`lemma_structural`, qui compare la séquence de lemmes du
**label entier** (pas le pattern POS+lemme token par token) à la séquence de
lemmes du texte — un filet de secours pour les entrées sans pattern
exploitable, désactivable indépendamment. Le chemin
`surface_structural`/`surface_upper_exact` (`use_surface`), lui, ne
lemmatise jamais : comparaison sur la forme littérale normalisée.

**Déduplication** : sélection gloutonne des meilleurs spans
non-chevauchants, triés par score décroissant → priorité de règle →
longueur → position.

### Filtrage qualité — valeurs internes

`discourse_pattern_guard` filtre les mots fonctionnels courants même pour
les matches `rule="pattern"`, via des sets propres à chaque langue,
sélectionnés depuis `lang` et surchargeables par
`quality.syntactic_generic_words` :

- **EN** : `{"and", "or", "it", "well", "can", "may", "like"}`
- **FR** : `{"et", "ou", "ni", "mais", "il", "elle", "on", "bien", "ainsi", "comme"}`

Garde syntaxique (`syntactic_context_guard: true`) :

1. **Attribut copulatif** : `"is the <mot_générique> that…"` → élimine
   `"process"`, etc.
2. **Mot-titre en position 0** : mot générique en majuscule au début du
   document.

Pénalité adaptative des single-tokens :

| Cas | Pénalité |
|---|---|
| Tout en majuscules ≥ 2 chars (`ERP`, `SAM`) | min(base, 0.05) — acronyme |
| CamelCase avec majuscule interne (`SenseCam`) | min(base, 0.05) — entité spécifique |
| Tout en minuscules ≤ 3 chars (`cue`, `or`) | max(base, 0.20) — risque élevé |
| Autres | base (valeur du profil) |

Scoring contextuel, dans une fenêtre de ±2 tokens :

- voisins lexicaux majoritaires → +0.05 (bonus) ;
- voisins fonctionnels majoritaires → -0.20 (pénalité) ;
- token en NOUN/PROPN/ADJ → +0.05 (bonus POS).

### Auto-profiling — heuristique

`--auto-profile` choisit le profil d'après les statistiques du
dictionnaire :

| Condition | Profil suggéré |
|---|---|
| `ratio_pattern ≥ 0.45` ET `ratio_mono ≥ 0.4` ET beaucoup d'uppercase | `entity_strict` |
| `ratio_puncty ≥ 0.15` OU `avg_label_len ≥ 2.2` | `term_recall` |
| Sinon | `term_balanced` |

### Optimisations de performance

| Optimisation | Gain mesuré |
|---|---|
| Pré-compilation de `_PUNCT_RE` | −8s sur P66_en |
| Pré-calcul de `spec._norm_lemma` | −5s |
| LRU cache sur `normalize_text` (99.9% hit rate) | −60% des appels |
| Index patterns par premier token normalisé | ×2 à ×73 selon le vocabulaire |

**Cumul** : P66_en 33s → 7s (×4.7), 9SD_en 117s → 1.6s (×73), 27X_en 16s → 1.2s (×13).
