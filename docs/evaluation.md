# Évaluation — résultats de référence et protocoles

Résultats mesurés, protocoles d'évaluation et pistes écartées. Le manuel d'utilisation (`docs/README.md`) n'en garde que les conclusions utiles au choix des options ; le mécanisme des méthodes est décrit dans `docs/underthehood.md`, le journal complet des mesures dans `planification/analyse_benchmarks_extraction.md`.

1. [Extraction — benchmark ACTER](#1-extraction--benchmark-acter)
2. [Listes de suggestion d'`embed` — précision et rappel mesurés](#2-listes-de-suggestion-dembed--précision-et-rappel-mesurés)
3. [Piste abandonnée — juger un vocabulaire cible sans corpus](#3-piste-abandonnée--juger-un-vocabulaire-cible-sans-corpus)
4. [Annotation — corpus gold](#4-annotation--corpus-gold)
5. [Annotation — comparaison avec l'API de production](#5-annotation--comparaison-avec-lapi-de-production)

---

## 1. Extraction — benchmark ACTER

```bash
make corpus-acter      # clone https://github.com/AylaRT/ACTER (CC BY-NC-SA 4.0) dans corpus_acter/
make benchmark-acter   # ncvalue vs PositionRank, P/R/F1 token-level vs le gold ACTER
```

Compare `ncvalue`/`graph` (sans vocabulaire, comme D-Terminer) sur 4 domaines × 2 langues. Résultat de référence (2026-10-05, inchangé le 2026-10-09) : F1 PositionRank=0.499, C-value=0.398. La fourchette D-Terminer (0.32–0.50, mBERT+RNN+GPU) est citée à titre indicatif : son protocole exact n'a pas été reproduit ici. `--extractor embed` exclu de cette comparaison (nécessite un vocabulaire cible, qu'ACTER n'a pas) — voir `scripts/evaluation/acter_eval.py` pour la variante expérimentale semi-supervisée.

Cette variante (moitié du gold ACTER comme vocabulaire de référence, l'autre moitié à retrouver, coupure oracle top-N) donne F1=0.364 pour `embed` (P=0.734, R=0.242, revérifié le 2026-10-09) — F1 **moins bon** que C-value (0.398) et PositionRank (0.499) évalués à froid sur le même gold, malgré la moitié des réponses fournies comme référence, mais avec une précision nettement plus haute (0.73 contre 0.47–0.56). À l'inverse du gain massif observé sur X64 (README §5.1), un vocabulaire de référence restreint ne donne pas à `embed` un signal suffisant : préférer `ncvalue`/`graph` quand le vocabulaire cible est petit ou peu représentatif du domaine.

`make benchmark-acter` lance aussi (par défaut, `--skip-structural-signal` pour désactiver) une troisième variante avec les **vrais seuils de production** (`--enrichment-threshold`/`--structural-top-pct`, pas la coupure oracle top-N ci-dessus) : `enrichment_suggestion_embed` seul vs `enrichment_suggestion_embed` + `enrichment_suggestion_structural` (§2). Voir `planification/analyse_benchmarks_extraction.md` pour le détail et le balayage de `--structural-top-pct`.

### 1.1 Comparaison avec TermSuite (2026-10-09)

TermSuite 3.0.10 (configuration par défaut, classement par spécificité) a été passé sur les mêmes textes ACTER et noté avec exactement le même protocole (`scripts/evaluation/termsuite_acter_eval.py`, qui réutilise les fonctions d'`acter_eval.py` ; les occurrences TermSuite sont prises à leurs positions exportées dans son JSON).

| P / R / F1 (token-level) | Notre pipeline | TermSuite |
|---|---:|---:|
| Sans vocabulaire, top-N | PositionRank 0.556 / 0.452 / 0.499 — C-value 0.471 / 0.345 / 0.398 | 0.521 / 0.627 / **0.569** |
| Avec vocabulaire, même nombre de suggestions que la liste 1 | liste 1 (embed) **0.854** / 0.129 / 0.224 | 0.525 / 0.303 / 0.384 |
| Avec vocabulaire, même nombre que les listes 1+2 | listes 1+2 **0.571** / 0.231 / 0.329 | 0.476 / 0.340 / 0.397 |

Lecture : en token-level, TermSuite gagne en F1 par le **rappel** et embed garde la meilleure **précision**. Mais compté par suggestion (une suggestion compte une fois), à nombre égal, embed fait mieux sur les deux tableaux : liste 1, 53 % de suggestions justes contre 39 %, soit **521 termes justes distincts contre 385** sur 980 ; listes 1+2, 648 contre 479 sur 1 499 (tableau « Ce que voit le curateur » plus bas). L'avantage de TermSuite en rappel n'existe qu'en mesure pondérée par les occurrences. `extract_annotate --extractor embed` reste le pipeline recommandé pour la mise à jour de ressource. Ces F1 token-level ne sont pas comparables à ceux de TermEval 2020 (liste de termes uniques).

**Origine de l'avance de TermSuite, et correction** : TermSuite repère toutes les occurrences de chaque terme dans le texte ; nos candidats ne comptaient que les endroits où spaCy produit exactement ce groupe nominal. Avec `--respot-occurrences` (même benchmark, 2026-10-09) :

| P / R / F1 (token-level) | Sans l'option | `--respot-occurrences` | TermSuite |
|---|---:|---:|---:|
| C-value, à froid | 0.471 / 0.345 / 0.398 | 0.497 / 0.445 / **0.470** | — |
| PositionRank, à froid | 0.556 / 0.452 / 0.499 | 0.554 / 0.532 / **0.543** | 0.521 / 0.627 / 0.569 |
| embed semi-supervisé, top-N | 0.734 / 0.242 / 0.364 | 0.754 / 0.436 / **0.552** | 0.416 / 0.483 / 0.447 |
| liste 1 (embed) | 0.854 / 0.129 / 0.224 | **0.879** / 0.218 / **0.349** | — |
| listes 1+2 | 0.571 / 0.231 / 0.329 | **0.582** / 0.343 / **0.432** | — |

Embed dépasse alors TermSuite partout où la comparaison existe ; à froid, TermSuite ne garde que 0.026 de F1 d'avance sur PositionRank. Pas d'intégration de TermSuite envisagée.

Ce tableau est celui de la première version, qui repérait dans tout le texte : sur RevueESR, elle a pris 1 h 36 et rempli la liste 2 de suites de mots outils (« Of the », « pas d »). La version actuelle ne repère qu'à l'intérieur des groupes nominaux : C-value 0.443, PositionRank 0.521, embed top-N 0.519 (toujours au-dessus de TermSuite), liste 1 0.883 / 0.195 / 0.319, listes 1+2 0.600 / 0.307 / 0.406, sans surcoût de temps sur RevueESR.

**Ce que voit le curateur : la précision par candidat** (une suggestion compte une fois, juste si c'est un terme de référence à retrouver), à nombre de suggestions égal :

| P par candidat (suggestions justes / suggestions) | Liste 1 | Listes 1+2 |
|---|---:|---:|
| embed, sans l'option | **0.532** (521 / 980) | **0.432** (648 / 1 499) |
| embed, `--respot-occurrences` | 0.509 (468 / 919) | 0.430 (595 / 1 385) |
| TermSuite, même nombre de suggestions | 0.393 (385 / 980) | 0.320 (479 / 1 499) |

Embed bat TermSuite sur ce critère aussi ; `--respot-occurrences` améliore la mesure token-level mais pas le nombre de suggestions justes distinctes — il reste une option. Détail : `planification/analyse_benchmarks_extraction.md`, entrées 16 à 18. Mesure reproductible : `python3 scripts/evaluation/acter_eval.py --min-freq 1 --respot-occurrences --out-dir benchmark_results/respot/acter_respot`.

```bash
# TermSuite (installé dans ~/app/termsuite-run : jar 3.0.10 + TreeTagger), un dossier de .txt par domaine/langue
java -Xmx6g -cp termsuite-core-3.0.10.jar fr.univnantes.termsuite.tools.TerminologyExtractorCLI \
  -t treetagger -c corpora/acter_wind_fr -l fr --json acter_wind_fr.json
# notation, sans puis avec vocabulaire
python3 scripts/evaluation/termsuite_acter_eval.py --termsuite-dir <dossier des JSON> \
  --compare <acter_eval à froid>/acter_results.json --out benchmark_results/termsuite/termsuite_acter_results
python3 scripts/evaluation/termsuite_acter_eval.py --termsuite-dir <dossier des JSON> \
  --seeded-compare <acter_eval --skip-cold> --out benchmark_results/termsuite/termsuite_vs_embed
```

---

## 2. Listes de suggestion d'`embed` — précision et rappel mesurés

Mesuré sur ACTER (seuils de production, reproduit le 2026-09-30, précision token-level) :

| | Precision | Rappel | F1 |
|---|---:|---:|---:|
| niveau 1 seul (`enrichment_suggestion_embed`) | 0.852 | 0.129 | 0.224 |
| niveau 1 + niveau 2 (`enrichment_suggestion_structural`) | 0.560 | 0.231 | 0.327 |

Le niveau 2 relève le rappel de +79% relatif au prix d'une liste propre nettement moins précise (part de suggestions justes, par candidat : 0.23 pour le niveau 2 seul contre 0.53 pour le niveau 1 ; en token-level, 0.39 contre 0.85). Le seuil `--structural-top-pct` a été balayé de 2% à 30% sans pic net de F1 dans cette plage — le choix de 2% privilégie la précision plutôt que de maximiser le F1 brut.

**Niveau 3 (2026-09-11)** : les trois niveaux combinés (structurel 2% + spécificité 10%) portent le F1 à **0.368** (contre 0.327 pour les niveaux 1+2), mais le niveau 3 seul n'a que **0.14 de suggestions justes par candidat** (0.27 en token-level), contre 0.23 (0.39) pour le niveau 2 seul — nettement plus bruité, d'où la désactivation par défaut.

**Choix de la tâche plutôt que du vocabulaire** : le profil précision/rappel d'`embed` seul est constant sur les 8 combinaisons domaine/langue testées — il **valide bien** un candidat qui ressemble à un terme déjà présent dans le vocabulaire cible (précision correcte), mais **rate la plupart des termes vraiment absents/nouveaux** (rappel bas). D'où les listes 2 et 3, indépendantes du vocabulaire, pour l'enrichissement par des termes éloignés de la ressource.

---

## 3. Piste abandonnée — juger un vocabulaire cible sans corpus

Piste explorée et **abandonnée** : mesurer une densité interne du vocabulaire seul (scission seed/held-out, similarité au plus proche voisin), sans corpus de texte réel. Calibration testée sur 4 cas connus (X64 + 3 domaines ACTER, voir `planification/analyse_benchmarks_extraction.md`) : le vocabulaire ACTER `wind` est le **plus dense** de tous (médiane 0.874, au-dessus de X64 à 0.828) et donne pourtant le **pire** F1 réel (0.286, variante semi-supervisée) — ni la densité ni même la taille du vocabulaire (`corp`, 463 termes, F1=0.407 > `htfl`, 1180 termes, F1=0.345) ne discriminent les cas qui marchent des cas qui échouent. Cause probable : ces métriques ignorent le bruit des candidats non-termes extraits d'un texte réel, qui est le facteur dominant du rappel en production (précision correcte 0.55–0.85 partout, mais rappel bas 0.17–0.34 quel que soit le domaine — voir `benchmark_results/acter/acter_results_embed_seeded.json`). Aucun diagnostic sans corpus de texte réel n'est donc fiable ; seule la méthodologie d'`acter_eval.py` (seed/held-out sur un **corpus de texte réel** annoté) est validée pour évaluer `embed` avant de le choisir en production.

---

## 4. Annotation — corpus gold

### 4.1 Qualité des ARKs — corrections appliquées (corpus anglais)

Les gold ont été générés avec des versions antérieures des vocabulaires et contenaient des ARKs obsolètes (format numérique `P66-84482143`). Les corrections suivantes ont été appliquées :

**Corrections automatiques (correspondance par libellé préféré)** :
- **P66** : 289 ARKs numériques → alphanumériques courants
- **27X** : 294 ARKs numériques → alphanumériques courants
- 7 autres corpus (9SD, 8HQ, B9M, BVM, QX8, 3JP, JVR) : déjà corrects

**Corrections manuelles (termes absents du dictionnaire courant)** :

| Terme | Ancien ARK | ARK courant |
|---|---|---|
| `scientific discourse` (P66) | P66-24670690 | `P66-ZLDWBWS5-Z` |
| `speed cell` (P66) | P66-84416865 | `P66-FSHB2M05-B` |
| `scene construction theory` (P66) | P66-43657611 | `P66-GXCZ963J-Z` |
| `sleep-dependent memory triage` (P66) | P66-89130182 | `P66-SW8FNBND-B` |
| `scientific principle` (P66) | P66-24184462 | `P66-N7XGNQGG-J` |

**Termes supprimés** (absents des vocabulaires actuels) :
- `beetle` (27X) — 3 occurrences retirées
- `ceramic assemblage` (27X) — 3 occurrences retirées

### 4.2 Logique de comparaison gold/prédictions

Le renderer et le benchmark utilisent une comparaison **par libellé préféré** (`pref`), indépendante de la position exacte. Cette approche est nécessaire car les offsets de position du gold pour les documents 1+ sont systématiquement décalés par rapport au texte réel (conséquence de la génération avec une version différente du texte).

**Algorithme** (`loterre_html_renderer.py`) :
1. `ann_key(m)` retourne `pref.lower()` — clé de comparaison indépendante de la position et du format d'ARK
2. `ann_span(m, text)` valide `text[start:end] == found` avant d'utiliser la position ; si la position est incorrecte, recherche la surface form dans le texte
3. `classify()` groupe les matches par `pref` et apparie la i-ème occurrence attendue avec la i-ème occurrence prédite (trié par position) — gère correctement les occurrences multiples du même concept
4. `counts()` utilise `Counter` pour un comptage par occurrence (pas par concept unique)

**Conséquence** : un terme prédit au bon endroit mais avec un ARK plus récent (alphanumérique) est correctement reconnu comme correspondant au terme attendu avec l'ancien ARK.

---

## 5. Annotation — comparaison avec l'API de production

**Alignement des tokens** : les `idx.start/end` renvoyés par l'API ISTEX sont des indices de **tokens** (non des offsets caractères). Le tokeniseur de l'API isole la ponctuation et traite les nombres décimaux comme un seul token (`1.1` → 1 token, non 3). Le convertisseur local (`api_doc_to_matches`) utilise la même règle `r"\d+\.\d+|\w+|[^\w\s]"` pour garantir l'alignement des indices.

**Écart résiduel sur BVM_en / B9M_fr** (baseline de non-régression, README §14.5) : cause identifiée — désaccord d'étiquetage POS entre le dictionnaire (généré avec `en_core_web_trf`/`fr_dep_news_trf`) et l'exécution (`en_core_web_sm`/`fr_core_news_sm`), confirmé indépendant des 3 correctifs de la baseline (reproduit à l'identique avec l'ancien moteur via `git stash`). Cet écart (~18 % de désaccords lemme/POS sur P66_en) est structurel et accepté : faire coïncider les deux modèles a été essayé et a dégradé le F1.
