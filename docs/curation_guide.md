# Guide de curation — mise à jour de ressource (`extract_annotate --extractor embed`)

Consigne opérationnelle : quelle méthode utiliser selon le contexte, et
comment un curateur humain doit traiter les suggestions produites. Pour le
mécanisme technique détaillé (comment les scores et les trois champs de
suggestion sont calculés), voir `docs/underthehood.md`.

---

## En bref — recommandations pour le curateur

**Principe de base : ne jamais lire les scores bruts.** `score`, `structural_score`
et `specificity_score` sont des scores internes de mécanismes différents
(similarité cosinus, C-value/PositionRank, Weirdness Ratio) — non bornés pour
deux d'entre eux, non comparables entre eux, non comparables entre corpus. Le
curateur ne doit s'appuyer **que sur les trois champs booléens déjà seuillés**
pour décider quoi relire — et sur `frequency` (un simple comptage
d'occurrences, pas un score) pour décider **dans quel ordre** (règle 5
ci-dessous) :

| Niveau | Champ | Ce qu'il signifie | Suggestions justes (ACTER) | Traitement recommandé |
|---|---|---|---:|---|
| **1** | `enrichment_suggestion_embed` | Ressemble sémantiquement à un terme déjà connu du vocabulaire | **0.53** (~1 sur 2) | Revue rapide ; validation en lot seulement sur le haut de liste trié par fréquence (règle 5) |
| **2** | `enrichment_suggestion_structural` | Loin du vocabulaire mais statistiquement fort dans le corpus | **0.23** (~1 sur 4) | Lecture individuelle avec contexte (`occurrences`) obligatoire, pas de lot — plus de bruit attendu, ce n'est pas une anomalie |
| **3** | `enrichment_suggestion_specificity` | Loin du vocabulaire et du classement structurel, mais rare comparé à la langue générale | **0.14** (~1 sur 7) | Liste "exploratoire", à consulter seulement si activée explicitement (`--specificity-top-pct` > 0) — tri manuel lourd assumé |

**Quel chiffre lire** (mesures du 2026-09-30, chaque liste prise seule, aux
seuils par défaut — 10% pour le niveau 3) : la colonne ci-dessus est la
**précision par candidat** — chaque suggestion compte une fois, juste si
c'est un terme de référence. C'est ce que voit le curateur en parcourant une
liste, c'est le chiffre à retenir. Il est plutôt pessimiste : il exige une
correspondance exacte (un pluriel ou une variante compte comme faux).

Les benchmarks techniques donnent aussi une précision **par token**
(protocole ACTER : 0.85 / 0.39 / 0.27), qui fait peser chaque suggestion
selon son nombre d'occurrences dans le texte. Elle avantage les termes
fréquents, et elle peut monter sans qu'aucune suggestion ne s'améliore. Elle
sert à comparer des extracteurs entre eux, pas à prévoir la part de
suggestions justes : ne pas la présenter au curateur comme « x % des
suggestions sont justes ».

**Pourquoi séparées et jamais fusionnées** : un score composite (moyenne
pondérée, RRF) aurait dilué cet écart de fiabilité — le curateur doit pouvoir
calibrer sa confiance différemment par liste, pas recevoir un classement
unique qui mélange une liste juste à 1 sur 2 avec une juste à 1 sur 7 (détail §"Pourquoi
des listes séparées" plus bas).

**Règles pratiques à ne pas enfreindre** :
1. Traiter les listes **dans l'ordre** 1 → 2 → 3, jamais en vrac.
2. Un candidat dans **aucune** des trois listes = pas de suggestion, hors périmètre du flux courant.
3. `in_vocabulary=True` = rien à faire, le terme est déjà connu.
4. Le rappel reste plafonné par l'extraction elle-même (noun chunks + filtres POS) — un terme dont la forme de surface n'est jamais capturée comme candidat n'apparaîtra dans **aucune** liste, quel que soit le réglage des seuils.
5. **Dans chaque liste, relire par `frequency` décroissante** : le haut de liste est nettement plus fiable que le bas (liste 1 : ~8 candidats sur 10 pertinents dans le quart le plus fréquent, ~4 sur 10 dans le quart le moins fréquent). Le bas de liste demande plus de vérification, il ne doit pas être rejeté d'office — voir règle 8 de la consigne.
6. **Sur un corpus de plusieurs dizaines d'articles, générer aussi le rapport d'analyse** (`--report rapport.html`) : chiffres clés, graphiques sur l'annotation et l'extraction, et couverture du vocabulaire par thème (expérimental) — voir §"Rapport d'analyse" plus bas.

**Les deux seuils ajustables, et quand y toucher** :
- **`--structural-top-pct`** (défaut 2%) : à remonter (5/10/15/20/30%, valeurs déjà mesurées) **seulement si** la liste 2 s'avère trop courte après plusieurs cycles réels de curation — jamais une décision a priori.
- **`--specificity-top-pct`** (défaut 0.0, désactivé) : à activer **uniquement** si le curateur veut explicitement pousser le rappel au-delà de ce que les listes 1+2 couvrent, en acceptant le coût de tri supplémentaire — 10% est la valeur mesurée utile si activé.

Le retour d'usage réel doit ajuster ces **paramètres de run**, jamais le code — c'est la boucle de rétroaction prévue.

**Limite à garder en tête** : le F1 mesuré (corpus ACTER, protocole
token-level) est un **proxy**, pas une garantie sur les vraies ressources
Loterre. La validation de référence reste l'usage réel par un curateur sur un
vocabulaire cible réel — les chiffres ci-dessus orientent la confiance à
accorder à chaque liste, ils ne remplacent pas le jugement du curateur.

Le détail de chaque point (mécanique des scores, choix de méthode, consigne
complète) est développé section par section ci-dessous.

---

## Interpréter les scores

`score` (le score embed, colonne CSV/champ JSON) est une **similarité cosinus
au terme du vocabulaire cible le plus proche** (plus proche voisin, pas une
moyenne) — **ce n'est ni une probabilité, ni un indice de qualité
linguistique du candidat**. Un score élevé signifie seulement "ce candidat
ressemble sémantiquement à un terme déjà connu du vocabulaire", pas "c'est un
bon terme" au sens absolu. Repères pratiques :

- **`score >= --enrichment-threshold`** (défaut **0.95**) → `enrichment_suggestion_embed=True`,
  haute précision mesurée (0.53 par candidat sur ACTER, soit environ une
  suggestion sur deux ; 0.85 pondéré par les occurrences)
- **`structural_rank` dans le top `--structural-top-pct`** (défaut **2%**) →
  `enrichment_suggestion_structural=True`, candidat loin du vocabulaire mais
  statistiquement fort dans le corpus, précision plus faible (0.23 par
  candidat ; 0.39 pondéré par les occurrences)
- **`specificity_rank` dans le top `--specificity-top-pct`** (défaut **0.0 =
  désactivé**) → `enrichment_suggestion_specificity=True`, candidat loin du
  vocabulaire et loin du classement structurel, mais rare par rapport à la
  langue générale — précision nettement plus faible (0.14 par candidat à
  10% ; 0.27 pondéré par les occurrences — voir règle 3 de la consigne de
  travail ci-dessous),
  **à activer explicitement**
- **`structural_score`/`specificity_score` bruts (C-value/PositionRank/Weirdness Ratio) : voir règle 4 ci-dessous**
  — échelle non bornée, dépend du corpus, jamais comparable directement à un
  niveau de confiance

Pour la mécanique de calcul complète (encodage, matrice de similarité,
calcul des signaux structurel et spécificité), voir `docs/underthehood.md`,
étapes 6, 7 et 10. En pratique, un curateur ne devrait lire ni `score` ni
`structural_score`/`specificity_score` directement — seuls les trois champs
booléens déjà seuillés (`enrichment_suggestion_embed`/`_structural`/`_specificity`)
doivent guider la décision, cf. consigne ci-dessous.

---

## Choix de la méthode

Un seul chemin recommandé selon que le vocabulaire Loterre cible existe déjà
ou non :

| Situation | Commande | Pourquoi |
|---|---|---|
| Vocabulaire cible existe déjà (cas quasi systématique) | `extract_annotate --extractor embed --dict <vocab>` | Seul extracteur avec un mécanisme de suggestion calibré vis-à-vis d'un vocabulaire — `ncvalue`/`graph` n'ont pas de seuil de confiance pour "ce terme mérite d'être ajouté" |
| Aucun vocabulaire cible (rare — "découvrir un domaine à froid") | `extract --extractor auto` (sans `--dict`) | `embed` est techniquement impossible sans dictionnaire cible (erreur explicite au lancement) |

Points qui ne nécessitent **aucune décision manuelle** :
- Le choix entre C-value et PositionRank pour le signal structurel (étape 7
  de `underthehood.md`) est automatique — bascule "auto" selon le volume de
  corpus, même règle que le choix normal d'extracteur.
- `ncvalue`/`graph` restent la bonne réponse pour l'autre cas d'usage
  (`extract` sans vocabulaire) — ce ne sont pas des concurrents d'embed pour
  la mise à jour de ressource, ils répondent à une question différente et
  n'ont pas de notion de suggestion d'enrichissement.
- **Et TermSuite ?** Comparé sur ACTER le 2026-10-09 avec le même
  protocole, à nombre de suggestions égal : 53 % des suggestions de la
  liste 1 d'embed sont justes, contre 39 % pour TermSuite — soit 521
  suggestions justes contre 385 sur 980. Embed trouve donc à la fois plus
  juste et plus de termes. L'avantage de TermSuite en rappel n'existe qu'en
  mesure pondérée par les occurrences : il vient de son comptage de toutes
  les occurrences de chaque terme, pas de termes supplémentaires. Pour un
  curateur, embed reste le bon choix (détail : `docs/evaluation.md` §1.1).
- **`--respot-occurrences`** (défaut désactivé) : compte toutes les
  occurrences de chaque candidat à l'intérieur des groupes nominaux, et
  fusionne ses variantes de casse. Fréquences plus justes pour le tri de
  relecture et fin des doublons « Terme » / « terme », mais pas plus de
  suggestions justes : sur ACTER, la précision par candidat de la liste 1
  passe de 0.53 à 0.51. Pas nécessaire pour la curation.
- Depuis le 2026-10-09, les candidats faits uniquement de mots outils
  français ou anglais (« of the », « pas d », « -ci ») sont écartés
  d'office ; les sigles en majuscules (« NO », « OR ») restent.

Les paramètres ajustables en pratique pour le chemin `embed` sont
**`--structural-top-pct`** (défaut **2%**, précision privilégiée — voir la
mesure ci-dessous). À remonter (5/10/15/20/30%, valeurs déjà mesurées dans
`planification/analyse_benchmarks_extraction.md`) seulement si la liste "à
vérifier" (niveau 2 ci-dessous) s'avère trop courte après plusieurs cycles
réels de curation — pas une décision à prendre a priori.

**`--specificity-top-pct`** (défaut **0.0 = désactivé**, contrairement à
`--structural-top-pct`) ajoute un troisième niveau de suggestion, plus
bruité que le niveau 2 (voir consigne de travail ci-dessous) — **à activer
uniquement si le curateur souhaite explicitement maximiser le rappel au prix
de plus de bruit à trier manuellement**, pas un réglage par défaut
raisonnable. Si activé, **10%** est la valeur mesurée utile sur ACTER.

Pour le chemin "aucun vocabulaire cible" (`extract --extractor ncvalue`,
gros corpus) : **`--specificity-filter-pctl`** (défaut **0**, désactivé) —
paramètre manuel, jamais recalculé automatiquement par corpus. Retire les
N% de candidats les moins spécifiques (contraste de fréquence vs langue
générale, voir `docs/underthehood.md`) avant le scoring C-value. **40**
est le point calibré sur ACTER (2026-09-11) — gain net (+12 à +14% de F1
relatif selon la coupure), à activer explicitement avec `--extractor
ncvalue` uniquement (dégrade `graph`/PositionRank, jamais à combiner avec
`--extractor auto` sur un document unique/corpus court).

---

## Consigne de travail pour le curateur

Chaque candidat absent du vocabulaire (`in_vocabulary=False`) peut porter
l'un de trois signaux de suggestion, **jamais deux à la fois** :

| Champ | Mécanisme | Suggestions justes (par candidat ; pondéré par les occurrences) | Rappel apporté (pondéré) |
|---|---|---:|---:|
| `enrichment_suggestion_embed` | similarité au terme le plus proche du vocabulaire, seuil 0.95 | **0.53** (0.85) | base (R 0.129) |
| `enrichment_suggestion_structural` | C-value/PositionRank, top 2% des candidats absents du vocabulaire | **0.23** (0.39) | +79% relatif (R 0.231, F1 0.224→0.327) |
| `enrichment_suggestion_specificity` | Weirdness Ratio vs langue générale, top `--specificity-top-pct` (défaut désactivé) | **0.14** (0.27) à 10% | +39% relatif (R 0.321, F1 0.327→0.368) |

Chiffres reproduits le 2026-09-30, chaque liste prise seule (voir "Quel
chiffre lire" en tête de ce guide, et
`planification/analyse_benchmarks_extraction.md`, entrée 2026-09-29 — une
version antérieure de ce guide donnait ~0.57-0.64 pour la liste 2, qui était
en réalité la précision de l'union listes 1+2, pas de la liste 2 seule).

1. **Traiter `enrichment_suggestion_embed=True` en premier** (liste 1, haute
   confiance) — revue rapide ; la validation en lot n'est raisonnable que
   sur le haut de liste trié par fréquence (règle 8) : environ 1 candidat
   sur 5 à rejeter dans le quart le plus fréquent, plus de 1 sur 2 dans le
   quart le moins fréquent.
2. **Traiter `enrichment_suggestion_structural=True` ensuite, séparément**
   (liste 2, confiance plus faible) — jamais de validation en lot ici,
   chaque candidat doit être lu avec son contexte (`occurrences`) avant
   décision. S'attendre à plus de bruit que sur la liste 1 : c'est le
   compromis attendu, pas un signe d'erreur du système.
3. **Si `--specificity-top-pct` a été activé, traiter `enrichment_suggestion_specificity=True`
   en dernier, comme une liste "exploratoire"** — environ 1 suggestion sur
   7 juste (0.14 par candidat à 10% ; 0.27 pondéré par les occurrences),
   sensiblement plus bruitée que la liste 2. À n'activer/consulter que si le curateur veut
   explicitement pousser le rappel au-delà de ce que les listes 1+2
   couvrent et accepte le tri manuel supplémentaire que ça implique — pas
   un flux de travail par défaut.
4. **Un candidat dans aucune des trois listes = pas de suggestion** par
   défaut — hors périmètre du workflow de curation courant, sauf recherche
   exploratoire ponctuelle.
5. **Ne jamais comparer `structural_score`/`specificity_score` bruts entre
   deux candidats comme un niveau de confiance** — les échelles C-value/
   PositionRank/Weirdness Ratio ne sont pas bornées et dépendent du corpus.
   Seuls les statuts binaires (déjà seuillés par rang relatif) doivent
   guider la décision, pas les chiffres eux-mêmes.
6. **`in_vocabulary=True` = rien à faire** — le terme est déjà connu, hors
   périmètre de la curation.
7. **Retour attendu après usage réel** : si la liste 2 (ou 3, si activée)
   est jugée trop bruitée ou trop courte en pratique, c'est un signal pour
   ajuster `--structural-top-pct`/`--specificity-top-pct` (paramètres de
   run) — pas pour modifier le code.
8. **À l'intérieur de chaque liste, trier par `frequency` décroissante et
   relire dans cet ordre.** Mesuré sur ACTER (2026-09-30, précision par
   candidat — chaque candidat compte une fois) :

   | Liste | Quart le plus fréquent | Quart le moins fréquent |
   |---|---:|---:|
   | 1 — `enrichment_suggestion_embed` | 0.81 | 0.41 |
   | 2 — `enrichment_suggestion_structural` | 0.40 | 0.09 |
   | 3 — `enrichment_suggestion_specificity` (10%) | 0.27 | 0.07 |

   Concrètement : la validation rapide de la liste 1 (règle 1) vaut
   surtout pour son haut de liste ; son bas de liste mérite la même
   lecture avec contexte que la liste 2. Pour les listes 2 et 3, le quart
   le moins fréquent est très majoritairement du bruit — c'est là qu'un
   curateur pressé peut s'arrêter. Un candidat peu fréquent n'est pas
   rejeté pour autant : un vrai terme rare reste possible, il demande
   seulement plus de vérification.

   `frequency` est le seul chiffre brut que le curateur peut lire
   directement (exception à la règle 5) : c'est un nombre d'occurrences
   dans le corpus analysé, comparable entre candidats d'un même run. Un
   indicateur plus élaboré (concentration thématique NMF/BERTopic, IDF
   résiduel) a été testé et fait moins bien que ce simple comptage — voir
   `planification/analyse_benchmarks_extraction.md`, entrée 2026-09-29.

   L'ordre de relecture recommandé vaut aussi en précision pondérée par les
   occurrences (liste 1 : quart le plus fréquent 0.91, quart le moins
   fréquent 0.63) — voir "Quel chiffre lire" en tête de ce guide.

   **Attention sur un corpus bruité** : ces chiffres viennent d'ACTER, dont le
   texte est propre. Sur un corpus issu de PDF (RevueESR, 2026-10-02), le
   haut des listes triées par fréquence est envahi par le bruit le plus
   répété : en-tête de revue ("Environ Risque Sante", 2 848 occurrences, en
   tête de la liste 2), "Mots clés", ponctuation et fragments de mots coupés
   par l'extraction PDF ("-", "n", "tion", "ees", en tête de la liste 3). Sur
   ce type de corpus, écarter d'abord ces candidats (ils se repèrent d'un
   coup d'œil, et la colonne `context` le confirme), puis appliquer le tri
   par fréquence au reste.

9. **Utiliser les colonnes d'aide du CSV** pour juger un candidat sans
   rouvrir le corpus :
   - `context` : extrait du texte autour de sa première occurrence, terme
     entre crochets ;
   - `n_docs` : nombre de documents qui le contiennent — un terme présent
     dans un seul article (vocabulaire propre à un auteur) ne se juge pas
     comme un terme présent dans 200 ;
   - `nearest_vocab_term` (`--extractor embed`) : le terme du vocabulaire
     auquel il ressemble le plus — c'est lui qui a donné `score`, et c'est
     un indice pour le placer dans la hiérarchie de la ressource (terme plus
     spécifique, synonyme, voisin) ;
   - `topic_id` / `topic_label` / `topic_coverage` (avec `--report`) : le
     thème du corpus auquel il appartient et la couverture de ce thème par
     le vocabulaire — pour filtrer et relire par thème dans un tableur. Ce
     sont des informations de **rangement**, pas un score de qualité.

---

## Rapport d'analyse (`--report`)

```bash
python3 src/loterre_cli.py extract_annotate --dict-id SEN_fr --profile term_balanced \
  --extractor embed --text corpus.jsonl --out candidats.json --out-csv candidats.csv \
  --report rapport.html
```

(`--topic-report` reste accepté comme ancien nom de l'option.) Page HTML
autonome. Sous les chiffres clés, un **mode d'emploi** rappelle en version
courte les consignes de relecture de ce guide et le sens de chaque indicateur
(trois listes et leur fiabilité mesurée, `nearest_vocab_term`, `frequency`,
`n_docs`, couverture d'un thème, scores bruts à ne pas lire). Le reste du
rapport tient en trois parties :

1. **Chiffres clés** : documents, candidats extraits, **part du vocabulaire
   retrouvée dans le corpus** (concepts présents au moins une fois / concepts
   du dictionnaire), part des documents contenant au moins un terme du
   vocabulaire, nombre de suggestions par liste. Deux lectures utiles avant
   même de relire une suggestion : un vocabulaire dont une grande part
   n'apparaît jamais dans le corpus est peut-être mal adapté à ce corpus (ou
   le corpus mal choisi) ; une forte part de documents sans aucune
   annotation signale des textes hors domaine ou mal extraits.
2. **Ce que le vocabulaire couvre déjà / ce qui pourrait manquer** : termes du
   vocabulaire les plus annotés (on y repère les termes transversaux),
   documents selon leur nombre d'annotations, chemin des candidats extraits
   aux suggestions, candidats par longueur, et les 10 suggestions les plus
   fréquentes de chaque liste (avec `n_docs` et, pour la liste 1, le terme
   du vocabulaire le plus proche). Ce sont des comptages directs.
3. **Couverture par thème (expérimental)**, détaillée ci-dessous.

### Couverture par thème — expérimental

Les trois listes jugent les candidats **un par un**. Cette partie répond à une
autre question : **dans quelles zones du corpus la ressource manque-t-elle de
termes ?** Elle découpe le corpus en thèmes (calculés automatiquement à partir
des candidats) et indique pour chacun :

- sa **couverture** : la part des passages du thème qui contiennent au moins
  un **terme propre** du vocabulaire — un terme surreprésenté dans ce thème.
  Les termes présents partout ("risque sanitaire", "changement climatique"
  pour SEN) ne comptent que là où ils sont surreprésentés, sinon ils
  donneraient une couverture trompeuse à des thèmes qui n'ont aucun terme
  propre ;
- les **suggestions** des listes 1, 2 et 3 qui en viennent.

**Comment s'en servir** :

1. **Lire le graphique de haut en bas** : les thèmes sont triés du moins
   couvert au plus couvert. Pour chacun des thèmes du haut, lire son
   étiquette (les 6 à 10 candidats les plus représentatifs) et trancher :
   - **thème de bruit** — en-têtes de revue ("Vol.", "n°", mois),
     remerciements et financements, adresses, affiliations, texte mal
     extrait des PDF ("donn ees", "signi catif") : l'écarter, et ignorer ses
     suggestions (sur RevueESR, ces thèmes portent près d'un quart des
     suggestions de la liste 3) ;
   - **discours général** — étiquette sans mot du domaine (« compte, prise,
     facteurs, modèle », « mise, place, gestion ») : un fourre-tout de
     langue courante, que le rapport ne met à part que s'il est d'un seul
     tenant ; l'écarter comme le bruit ;
   - **sous-domaine réel peu couvert** (sur RevueESR/SEN : santé au travail,
     périnatal, gestion des déchets) : c'est une zone où chercher en priorité
     des termes à ajouter — **si** elle entre dans le périmètre de la
     ressource, ce que seul le curateur peut décider.
2. **Relire les suggestions thème par thème** (bloc "Détail par thème" du
   rapport, ou filtre sur `topic_id` dans le CSV) : juger ensemble
   "solvants", "toluène", "VLEP", "travail posté" est plus rapide et plus
   cohérent que de les croiser dispersés dans une liste à plat. À
   l'intérieur de chaque thème, les suggestions sont déjà triées par
   fréquence décroissante (règle 8).
3. **Un thème bien couvert** (haut pourcentage) n'est pas pour autant
   complet : il reste à relire ses suggestions, simplement avec moins
   d'urgence.
4. **Un "thème générique"** est affiché à part, hors classement : un thème
   qui pèse beaucoup plus que la moyenne (au moins 2,5 fois) et regroupe le
   discours général des articles ("compte, exemple, mise, place, prise,
   gestion" sur RevueESR, 13% du corpus). Sa couverture est basse par
   construction : ce n'est pas une zone où chercher des termes manquants.
   Ses suggestions restent à relire normalement. Dans le CSV, ses candidats
   portent `topic_generic=True`.

**Ce que le rapport n'est pas** :

- **Pas un taux de couverture absolu** : "14%" signifie "14% des passages de
  ce thème contiennent un terme propre du vocabulaire", pas "la ressource
  couvre 14% de ce sous-domaine" — on ne connaît pas la terminologie
  complète que chaque thème devrait contenir. Comparer les thèmes entre eux,
  pas lire un pourcentage isolé.
- **Pas un découpage de référence** : le nombre de thèmes est un choix
  (automatique par défaut, `--report-topics N` pour le fixer) ; un
  même sous-domaine peut être éclaté en deux thèmes ou fondu dans un plus
  large. Sur RevueESR, les thèmes les moins et les mieux couverts restent
  les mêmes de 10 à 50 thèmes (mesuré le 2026-10-08) : c'est le classement
  qu'il faut lire, pas le découpage exact. Les étiquettes contiennent souvent des mots génériques ("niveau",
  "étude") à côté des mots qui caractérisent vraiment le thème.
- **Pas un signal de pertinence** : un candidat n'est ni meilleur ni pire
  parce qu'il est dans un thème peu couvert — ce genre de signal a été
  mesuré et ne fait pas mieux que la fréquence
  (`planification/analyse_benchmarks_extraction.md`, entrée 2026-09-29).
- **Pas disponible sur un texte court** : sous ~30 000 caractères, le
  rapport n'est pas généré (trop peu de matière pour former des thèmes).

**Statut expérimental** : validé qualitativement sur un seul corpus
(RevueESR, vocabulaire SEN). Les retours d'usage réel — le rapport a-t-il
effectivement aidé à trouver des termes manquants ? — décideront de son
avenir. Mécanisme détaillé : `docs/underthehood.md`, section "Rapport
d'analyse".

---

## Pourquoi des listes séparées plutôt qu'un score unique

Une fusion en un seul score (moyenne pondérée, Reciprocal Rank Fusion) a été
envisagée puis écartée (`planification/planif_extraction_terminologique.md`
§8, Option 3) : elle aurait risqué de réintroduire le bruit de discours
académique générique qu'`embed` (plus proche voisin) a justement été conçu
pour filtrer, et aurait cassé la lisibilité simple d'`enrichment_suggestion_embed`
pour un curateur non technique. Garder des catégories séparées permet de leur
appliquer un niveau d'exigence différent plutôt que de les diluer l'une dans
l'autre — même raisonnement appliqué au niveau 3 (spécificité, §9) : sa
précision (0.14 par candidat, 0.27 pondéré par les occurrences) est nettement
plus faible que celle du niveau 2 (0.23 / 0.39) ; les fusionner aurait caché cet écart de fiabilité au
curateur plutôt que de le lui laisser trancher (d'où le choix de le garder
désactivé par défaut, contrairement au niveau 2).

## Limite résiduelle

Le rappel reste plafonné par l'étape d'extraction (noun chunks + filtres
POS, voir `docs/underthehood.md` étape 1) — un terme dont la forme de
surface n'est jamais capturée comme candidat (acronyme isolé, forme très
rare) n'atteint aucune des trois listes, quel que soit le réglage de
`--structural-top-pct`/`--specificity-top-pct`. Le F1 mesuré ici (corpus ACTER, protocole
token-level) est un proxy, pas une garantie sur les vraies ressources
Loterre — la validation de référence reste l'usage réel par un curateur sur
un vocabulaire cible réel.
