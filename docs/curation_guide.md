# Guide de curation — mise à jour de ressource (`extract_annotate --extractor embed`)

Consigne opérationnelle : quelle méthode utiliser selon le contexte, et
comment un curateur humain doit traiter les suggestions produites. Pour le
mécanisme technique détaillé (comment les scores et les deux champs de
suggestion sont calculés), voir `docs/underthehood.md`.

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

Le seul paramètre ajustable en pratique est **`--structural-top-pct`**
(défaut **2%**, précision privilégiée — voir la mesure ci-dessous). À
remonter (5/10/15/20/30%, valeurs déjà mesurées dans
`planification/analyse_benchmarks_extraction.md`) seulement si la liste "à
vérifier" (niveau 2 ci-dessous) s'avère trop courte après plusieurs cycles
réels de curation — pas une décision à prendre a priori.

---

## Consigne de travail pour le curateur

Chaque candidat absent du vocabulaire (`in_vocabulary=False`) peut porter
l'un de deux signaux de suggestion, **jamais les deux à la fois** :

| Champ | Mécanisme | Precision mesurée (ACTER) | Rappel apporté |
|---|---|---:|---:|
| `enrichment_suggestion` | similarité au terme le plus proche du vocabulaire, seuil 0.95 | 0.858 | base |
| `enrichment_suggestion_structural` | C-value/PositionRank, top 2% des candidats absents du vocabulaire | ~0.57 isolé | +83% relatif |

1. **Traiter `enrichment_suggestion=True` en premier** (liste 1, haute
   confiance) — revue rapide, validation quasi en lot acceptable, environ
   1 candidat sur 7 à rejeter.
2. **Traiter `enrichment_suggestion_structural=True` ensuite, séparément**
   (liste 2, confiance plus faible) — jamais de validation en lot ici,
   chaque candidat doit être lu avec son contexte (`occurrences`) avant
   décision. S'attendre à plus de bruit que sur la liste 1 : c'est le
   compromis attendu, pas un signe d'erreur du système.
3. **Un candidat ni dans l'une ni dans l'autre liste = pas de suggestion**
   par défaut — hors périmètre du workflow de curation courant, sauf
   recherche exploratoire ponctuelle.
4. **Ne jamais comparer `structural_score` brut entre deux candidats comme
   un niveau de confiance** — l'échelle C-value/PositionRank n'est pas
   bornée et dépend du corpus. Seul le statut binaire
   `enrichment_suggestion_structural` (déjà seuillé par rang relatif) doit
   guider la décision, pas le chiffre lui-même.
5. **`in_vocabulary=True` = rien à faire** — le terme est déjà connu, hors
   périmètre de la curation.
6. **Retour attendu après usage réel** : si la liste 2 est jugée trop
   bruitée ou trop courte en pratique, c'est un signal pour ajuster
   `--structural-top-pct` (paramètre de run) — pas pour modifier le code.

---

## Pourquoi deux listes séparées plutôt qu'un score unique

Une fusion en un seul score (moyenne pondérée, Reciprocal Rank Fusion) a été
envisagée puis écartée (`planification/planif_extraction_terminologique.md`
§8, Option 3) : elle aurait risqué de réintroduire le bruit de discours
académique générique qu'`embed` (plus proche voisin) a justement été conçu
pour filtrer, et aurait cassé la lisibilité simple d'`enrichment_suggestion`
pour un curateur non technique. Garder deux catégories permet de leur
appliquer un niveau d'exigence différent plutôt que de les diluer l'une dans
l'autre.

## Limite résiduelle

Le rappel reste plafonné par l'étape d'extraction (noun chunks + filtres
POS, voir `docs/underthehood.md` étape 1) — un terme dont la forme de
surface n'est jamais capturée comme candidat (acronyme isolé, forme très
rare) n'atteint aucune des deux listes, quel que soit le réglage de
`--structural-top-pct`. Le F1 mesuré ici (corpus ACTER, protocole
token-level) est un proxy, pas une garantie sur les vraies ressources
Loterre — la validation de référence reste l'usage réel par un curateur sur
un vocabulaire cible réel.
