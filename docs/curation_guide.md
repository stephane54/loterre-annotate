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
curateur ne doit s'appuyer **que sur les trois champs booléens déjà seuillés** :

| Niveau | Champ | Ce qu'il signifie | Précision mesurée (ACTER) | Traitement recommandé |
|---|---|---|---:|---|
| **1** | `enrichment_suggestion_embed` | Ressemble sémantiquement à un terme déjà connu du vocabulaire | **0.858** | Revue rapide, validation quasi en lot acceptable (~1 candidat sur 7 à rejeter) |
| **2** | `enrichment_suggestion_structural` | Loin du vocabulaire mais statistiquement fort dans le corpus | **~0.57-0.64** | Lecture individuelle avec contexte (`occurrences`) obligatoire, pas de lot — plus de bruit attendu, ce n'est pas une anomalie |
| **3** | `enrichment_suggestion_specificity` | Loin du vocabulaire et du classement structurel, mais rare comparé à la langue générale | **~0.27-0.30** | Liste "exploratoire", à consulter seulement si activée explicitement (`--specificity-top-pct` > 0) — ~1 candidat sur 3-4 pertinent, tri manuel plus lourd assumé |

**Pourquoi séparées et jamais fusionnées** : un score composite (moyenne
pondérée, RRF) aurait dilué cet écart de fiabilité — le curateur doit pouvoir
calibrer sa confiance différemment par liste, pas recevoir un classement
unique qui mélange une précision de 0.86 avec une de 0.29 (détail §"Pourquoi
des listes séparées" plus bas).

**Règles pratiques à ne pas enfreindre** :
1. Traiter les listes **dans l'ordre** 1 → 2 → 3, jamais en vrac.
2. Un candidat dans **aucune** des trois listes = pas de suggestion, hors périmètre du flux courant.
3. `in_vocabulary=True` = rien à faire, le terme est déjà connu.
4. Le rappel reste plafonné par l'extraction elle-même (noun chunks + filtres POS) — un terme dont la forme de surface n'est jamais capturée comme candidat n'apparaîtra dans **aucune** liste, quel que soit le réglage des seuils.

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
  haute précision mesurée (0.858 sur ACTER)
- **`structural_rank` dans le top `--structural-top-pct`** (défaut **2%**) →
  `enrichment_suggestion_structural=True`, candidat loin du vocabulaire mais
  statistiquement fort dans le corpus, précision plus faible (~0.57)
- **`specificity_rank` dans le top `--specificity-top-pct`** (défaut **0.0 =
  désactivé**) → `enrichment_suggestion_specificity=True`, candidat loin du
  vocabulaire et loin du classement structurel, mais rare par rapport à la
  langue générale — précision isolée nettement plus faible (~0.27-0.30, voir
  règle 2 de la consigne de travail ci-dessous), **à activer explicitement**
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
ou non (voir `CLAUDE.md` §Objectif produit principal) :

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

| Champ | Mécanisme | Precision mesurée (ACTER) | Rappel apporté |
|---|---|---:|---:|
| `enrichment_suggestion_embed` | similarité au terme le plus proche du vocabulaire, seuil 0.95 | 0.858 | base |
| `enrichment_suggestion_structural` | C-value/PositionRank, top 2% des candidats absents du vocabulaire | ~0.57 isolé | +83% relatif |
| `enrichment_suggestion_specificity` | Weirdness Ratio vs langue générale, top `--specificity-top-pct` (défaut désactivé) | **~0.27-0.30 isolé** | supplémentaire, mais net (structurel+spécificité : F1 0.270→0.314) |

1. **Traiter `enrichment_suggestion_embed=True` en premier** (liste 1, haute
   confiance) — revue rapide, validation quasi en lot acceptable, environ
   1 candidat sur 7 à rejeter.
2. **Traiter `enrichment_suggestion_structural=True` ensuite, séparément**
   (liste 2, confiance plus faible) — jamais de validation en lot ici,
   chaque candidat doit être lu avec son contexte (`occurrences`) avant
   décision. S'attendre à plus de bruit que sur la liste 1 : c'est le
   compromis attendu, pas un signe d'erreur du système.
3. **Si `--specificity-top-pct` a été activé, traiter `enrichment_suggestion_specificity=True`
   en dernier, comme une liste "exploratoire"** — précision isolée mesurée
   ~0.27-0.30 (environ 1 candidat sur 3-4 pertinent), sensiblement plus
   bruitée que la liste 2. À n'activer/consulter que si le curateur veut
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
précision isolée (~0.27-0.30) est nettement plus faible que celle du niveau
2 (~0.57-0.64) ; les fusionner aurait caché cet écart de fiabilité au
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
