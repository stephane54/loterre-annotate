# Benchmarks : extraction de termes/phrases-clés sans modèle de langue

**Date :** 2026-06-13  
**Objet :** Comparaison chiffrée des méthodes d'extraction terminologique pour orienter le choix technologique de la v2.0

---

## Données clés — F1@N sur corpus scientifiques

Chiffres issus d'*Attention-Seeker* (Mao et al., 2024, arXiv:2409.10907), comparaison systématique sur 4 corpus de référence :

| Méthode | Inspec F1@10 | SemEval17 F1@10 | SemEval10 F1@10 | Krapivin F1@10 |
|---------|:-----------:|:---------------:|:---------------:|:--------------:|
| TF-IDF | 13.88 | 16.26 | 3.48 | — |
| YAKE | 19.62 | 18.14 | 14.40 | 9.35 |
| TextRank | 25.08 | 25.83 | 5.38 | 9.43 |
| SingleRank | 34.46 | 27.73 | 9.02 | 10.53 |
| TopicRank | 28.46 | 22.62 | 12.90 | 9.01 |
| PositionRank | 32.87 | 26.30 | 13.34 | — |
| EmbedRank (Doc2Vec) | 37.94 | 29.59 | 5.08 | 6.60 |
| EmbedRank (Sent2Vec) | 37.09 | — | 8.91 | 10.47 |
| PromptRank (LLM) | 37.88 | 37.76 | 20.66 | 16.71 |
| Attention-Seeker | 40.14 | 34.53 | 23.07 | 18.25 |

*Inspec = 2 250 abstracts CS (standard benchmark). SemEval2010/17 = papers scientifiques. Krapivin = full papers CS.*

**Observations directes :**
- YAKE est **le moins performant** des méthodes graphiques/statistiques sur ces corpus, malgré sa vitesse
- SingleRank et PositionRank dominent les méthodes sans modèle de langue
- MultipartiteRank absent de ce tableau — sur d'autres benchmarks : F1@5 ≈ 26.5 sur Inspec, dans la même fourchette que TopicRank
- EmbedRank (embeddings légers, pas de LLM) franchit un cap significatif

---

## Pourquoi C-value/NC-value n'apparaissent pas dans ces tableaux

Point crucial : **C-value et NC-value ne sont pas des extracteurs de phrases-clés — ce sont des extracteurs de termes de domaine.** La différence est fondamentale :

| Dimension | Keyphrase extraction | Terminology extraction |
|-----------|---------------------|----------------------|
| Objectif | Phrases importantes d'un document | Termes techniques d'un domaine |
| Granularité | Par document | Par corpus |
| Benchmarks | Inspec, SemEval | GENIA, UMLS, MeSH |
| Fréquence minimale | 1 occurrence | Typiquement ≥ 2-5 |
| Termes emboîtés | Pas gérés | Gérés explicitement (C-value) |

Sur corpus terminologiques spécialisés, les chiffres publiés pour C-value/NC-value (Frantzi 2000, confirmé par études biomédicales ultérieures) :

| Méthode | Précision | Rappel | F1 |
|---------|-----------|--------|-----|
| C-value seul | 65–70 % | 55–60 % | 60–64 % |
| NC-value (C-value + contexte) | 72–78 % | 58–63 % | 64–70 % |
| NC-value + filtres POS | 76–82 % | 55–62 % | 64–70 % |

*Source : Frantzi et al. 2000 (MEDLINE), répliqué dans plusieurs études biomédicales FR/EN 2010–2020.*

Ces chiffres **ne sont pas comparables directement** aux F1@10 du tableau précédent — protocoles d'évaluation différents.

---

## Ce que dit la littérature récente pour la terminologie scientifique

Un papier de 2025 (*Extracting domain-specific terms using contextual word embeddings*, arXiv:2502.17278) sur corpus scientifiques multi-domaines (biomécanique, chimie, linguistique, vétérinaire — 250k mots, 9 657 termes annotés manuellement) montre que les méthodes purement statistiques **ne fonctionnent pas** sans composante linguistique :

| Approche | F1 moyen (4 domaines) |
|----------|:--------------------:|
| Statistique seul | ~0.000 |
| Patron linguistique seul | ~0.002 |
| Contexte seul | ~0.35 |
| Contexte + statistique | ~0.49 |
| **Contexte + patron + statistique** | **~0.56** |
| SVM linéaire (features combinées) | **0.564** |

**Conclusion du papier** : les méthodes purement statistiques (dont C-value brut) ont un F1 proche de zéro sans filtres linguistiques. C'est la **combinaison** POS + fréquence + contexte qui produit des résultats corrects — exactement ce que NC-value formalise.

---

## Dépendance au volume d'entrée — point critique

NC-value repose sur deux fréquences : celle du candidat terme lui-même, et la fréquence de ce candidat en tant que sous-chaîne de termes plus longs. Pour que la pénalisation des termes emboîtés soit significative, les deux doivent être observés suffisamment de fois. NC-value ajoute un score de contexte nominal (co-occurrences autour des candidats), ce qui nécessite encore plus d'occurrences.

| Volume d'entrée | C-value / NC-value | SingleRank / PositionRank | YAKE |
|----------------|:-----------------:|:-------------------------:|:----:|
| 1 document (~500 mots) | inutilisable | correct | bon |
| Quelques docs (~10 000 mots) | médiocre | bon | bon |
| Corpus moyen (~100 000 mots) | bon | bon | moyen |
| Grand corpus (~500 000 mots+) | excellent | correct | moyen |

La recommandation des auteurs de C-value et de TermSuite est un **minimum de 50 000 à 100 000 mots** pour des résultats fiables.

En volume concret pour des textes scientifiques (abstracts ~250 mots, articles ~6 000 mots) :

| Mots | Pages (~400 mots/page) | Équivalent articles complets | Équivalent abstracts |
|------|:---------------------:|:---------------------------:|:--------------------:|
| 10 000 | ~25 pages | ~1–2 articles | ~40 abstracts |
| 50 000 | ~125 pages | ~6–10 articles | ~200 abstracts |
| 100 000 | ~250 pages | ~15–20 articles | ~400 abstracts |

NC-value devient fiable à partir de **6 à 10 articles scientifiques complets**. En dessous de ce seuil, PositionRank est plus pertinent.

**Conséquence pour loterre-v9** : l'algorithme optimal dépend du mode d'utilisation.

- **Texte unique ou petit lot** (< ~10 000 tokens) → SingleRank ou PositionRank sont mieux adaptés
- **Corpus entier** (mode batch, 50+ documents) → NC-value reprend l'avantage

La stratégie retenue : **sélection automatique selon le volume**, ou choix explicite via `--extractor`.

---

## Synthèse pour la décision v2.0

### Sur la keyphrase extraction générique (textes courts, extraction ad hoc)
- YAKE est rapide mais médiocre (F1@10 ≈ 19 vs 34 pour SingleRank sur Inspec)
- SingleRank/PositionRank sont les meilleurs sans modèle de langue
- MultipartiteRank est dans la même fourchette que TopicRank

### Sur la terminologie scientifique de domaine (cas loterre-v9)
- C-value seul ne suffit pas — NC-value est l'upgrade minimal nécessaire
- NC-value (C-value + contexte nominal) atteint F1 ≈ 65–70 % sur corpus médicaux annotés
- Les méthodes sans composante linguistique (YAKE, TF-IDF seul) échouent sur textes techniques
- En 2025, les approches qui surpassent NC-value sans LLM sont toutes des **combinaisons POS + statistique + contexte**
- NC-value nécessite ~50 000–100 000 mots minimum pour être fiable

### Recommandation

**Deux extracteurs complémentaires selon le volume d'entrée :**

| Contexte | Extracteur recommandé | Option CLI |
|----------|----------------------|-----------|
| Texte unique / petit lot (< 10 000 tokens) | SingleRank ou PositionRank | `--extractor graph` |
| Corpus batch (> 50 000 tokens) | NC-value + filtres POS spaCy | `--extractor ncvalue` (défaut) |

Sélection automatique possible : si le corpus d'entrée dépasse le seuil configurable, NC-value est activé ; sinon, PositionRank est utilisé.

---

## Franchir un gap de qualité — contrainte FR+EN

### Ce que la contrainte FR+EN élimine

Les modèles monolingues les plus performants sont exclus :

| Modèle | Langue | Statut |
|--------|--------|--------|
| SciBERT | EN uniquement | Éliminé |
| CamemBERT | FR uniquement | Éliminé |
| RoBERTa-large | EN uniquement | Éliminé |
| Dr-BERT | FR uniquement | Éliminé |

### Niveau 1 — Embeddings multilingues (sans fine-tuning, effort faible)

Remplacement de PositionRank par un extracteur à base d'embeddings : les candidats termes sont classés par similarité cosinus avec l'embedding du document entier (principe KeyBERT/EmbedRank).

| Modèle | FR | EN | Taille | Notes |
|--------|:--:|:--:|--------|-------|
| `paraphrase-multilingual-mpnet-base-v2` | ✓ | ✓ | 278 Mo | Meilleur ratio qualité/vitesse, CPU OK |
| `intfloat/multilingual-e5-large` | ✓ | ✓ | 560 Mo | Meilleure qualité, GPU conseillé |
| `paraphrase-multilingual-MiniLM-L12-v2` | ✓ | ✓ | 118 Mo | Rapide, qualité moindre |

Gain estimé sur benchmarks : **+10 à +15 % de F1** par rapport à PositionRank seul.  
Option CLI envisagée : `--extractor embed`

### Niveau 2 — Fine-tuning supervisé (effort moyen, saut majeur)

Fine-tuner un modèle multilingue comme classifieur de tokens (BIO tagging). Requiert GPU — voir section "Contrainte matérielle" ci-dessous.

**Important — clarification sur la "weak supervision Loterre"** : ce n'est pas un prérequis au pipeline d'extraction. Le pipeline de base (NC-value + PositionRank) est entièrement non supervisé — aucune terminologie fournie en amont. La weak supervision est une piste de R&D optionnelle dont l'objectif est différent : apprendre les patterns linguistiques des termes Loterre existants pour mieux cibler des termes du même type non encore dans le vocabulaire. Elle devient pertinente dans deux cas :

- **Enrichissement du vocabulaire** : suggérer des termes candidats à ajouter à Loterre
- **Filtrage du bruit** : NC-value et PositionRank produisent des candidats bruités (noun chunks non terminologiques) ; un classifieur fine-tuné peut scorer chaque candidat et éliminer le bruit avant présentation des résultats

Ces deux objectifs sont indépendants du mode `extract+annotate` standard, mais peuvent améliorer significativement la qualité perçue des résultats.

| Modèle | FR+EN | F1 NER multilingue | GPU requis |
|--------|:-----:|:-----------------:|:----------:|
| `xlm-roberta-large` | ✓ | ~83–86 % | Oui |
| `microsoft/mdeberta-v3-base` | ✓ | ~84–87 % | Oui |

**mDeBERTa-v3-base** est le choix recommandé en 2025 : il surpasse XLM-R-large sur la plupart des benchmarks NER multilingues tout en étant plus petit.

Gain estimé : **+20 à +25 % de F1** par rapport à NC-value.

### Tableau de décision global (FR+EN)

| Option | FR+EN | Gain qualité | Effort | Prérequis |
|--------|:-----:|:-----------:|:------:|-----------|
| NC-value + PositionRank (spaCy) | ✓ | base | faible | rien |
| + embeddings `mpnet-base-v2` | ✓ | +10–15 % F1 | faible | `sentence-transformers` pip |
| Fine-tuning mDeBERTa-v3 (weak supervision) | ✓ | +20–25 % F1 | moyen | corpus brut + GPU |
| Fine-tuning XLM-R-large (weak supervision) | ✓ | +20–25 % F1 | moyen+ | corpus brut + GPU |

---

## Contrainte matérielle : pas de GPU

Le fine-tuning (niveau 2) est hors de portée sans GPU ou accès cloud (Colab, AWS, etc.). Le niveau 1 (embeddings) reste accessible en CPU avec le bon modèle.

### Sentence-transformers en CPU — vitesses réelles

| Modèle | Taille | Temps/doc CPU | Qualité | Statut |
|--------|:------:|:-------------:|:-------:|--------|
| `paraphrase-multilingual-MiniLM-L12-v2` | 118 Mo | ~100–300 ms | correcte | **Recommandé** |
| `paraphrase-multilingual-mpnet-base-v2` | 278 Mo | ~500 ms–2 s | bonne | viable |
| `intfloat/multilingual-e5-large` | 560 Mo | ~3–8 s | très bonne | trop lent en CPU |

`MiniLM-L12-v2` est le bon compromis pour un outil CLI en CPU : rapide, FR+EN, qualité nettement supérieure à PositionRank seul.

### Approche zero-shot pour filtrage et enrichissement (sans GPU)

Les deux objectifs (filtrage du bruit + enrichissement du vocabulaire) sont accessibles sans fine-tuning en utilisant les termes Loterre existants comme référence d'embeddings :

```
Termes Loterre (labels JSONL existants)
    → embeddings MiniLM       → centroïde du vocabulaire cible
                                          ↑ similarité cosinus
Candidats NC-value / PositionRank
    → embeddings MiniLM       → score de pertinence terminologique
                                          ↓
              ┌────────────────────────────────────────┐
              │ score élevé + présent dans Loterre     │ → annotation confirmée
              │ score élevé + absent de Loterre        │ → candidat enrichissement
              │ score faible                           │ → bruit, filtré
              └────────────────────────────────────────┘
```

**Gain estimé** : +5–8 % F1 supplémentaire sur le filtrage du bruit par rapport à NC-value seul.  
**Prérequis** : uniquement `sentence-transformers` + `MiniLM-L12-v2`, déjà prévus.  
**Avantage spécifique loterre-v9** : les vocabulaires Loterre (labels JSONL) sont directement utilisables comme référence — aucune donnée supplémentaire requise.

### Plafond réaliste sans GPU

```
NC-value + PositionRank                         → F1 ~64–70 % (terminologie)
+ MiniLM scoring (filtrage bruit + enrichiss.)  → F1 ~70–76 % (terminologie)
+ MiniLM re-ranking candidats (KeyBERT)         → F1 ~72–78 % (terminologie)
Fine-tuning mDeBERTa-v3                         → hors de portée sans GPU (~85–87 %)
```

### Recommandation concrète pour la v2.0

1. **Socle** : NC-value + PositionRank selon volume — Python pur, zéro dépendance lourde
2. **Option qualité + filtrage** : `MiniLM-L12-v2` via `sentence-transformers` — scoring des candidats par similarité aux termes Loterre existants, filtre le bruit et identifie les candidats d'enrichissement
3. **Option re-ranking** : `--extractor embed` — classement KeyBERT-style pour extraction sur textes courts
4. **Fine-tuning** : différé, nécessite GPU — gain supplémentaire de ~10–15 % F1 si accès disponible un jour

---

## Journal des benchmarks effectués sur loterre-v9

Contrairement aux sections précédentes (chiffres publiés, littérature), cette section journalise les **benchmarks réellement exécutés** sur ce dépôt — un bloc par tâche, dans l'ordre chronologique. À compléter à chaque nouveau benchmark.

---

### Analyse qualité C-value sur le vocabulaire X64 — 2026-06-22

**Contexte** : l'utilisateur a demandé une analyse des résultats d'extraction existants (`output_extract/X64_{fr,en}_annotate_extract.jsonl`, vocabulaire X64 = linguistique) — les candidats remontés en tête de classement semblaient peu pertinents en FR comme en EN.

**Ce qui a été fait** : calcul du taux de candidats reconnus dans le vocabulaire (`in_vocabulary`) sur l'ensemble des candidats vs dans le top 20/top 50 par score C-value (`rule=cvalue`), sur le corpus `data/X64_{fr,en}.jsonl` (FR 1320 docs/222k tokens, EN 773 docs/113k tokens).

**Résultats** : taux global correct (FR 18.0 %, EN 22.6 % — l'extraction noun-chunk fonctionne) mais très dégradé en tête de classement (FR 4/50, EN 14/50 dans le top 50). Top candidats dominés par des locutions méta-discursives académiques ("d'autre part", "l'auteur", "one hand", "Journal des Sçavans") sans rapport avec le domaine. Diagnostic : C-value récompense la fréquence brute, pas la spécificité au domaine — voir mémoire `project_x64_extraction_quality`.

---

### Comparaison PositionRank vs C-value sur X64 — 2026-06-22

**Contexte** : suite à l'analyse précédente, test du levier `--extractor graph` (PositionRank) comme alternative à C-value, sans aucun développement.

**Ce qui a été fait** : extraction sur X64_en et X64_fr avec `--extractor graph` au lieu du défaut `ncvalue`, comparaison du top 20 par score.

**Résultats** : net progrès en EN (top20 in_vocab 7/20 → 9/20, top20 thématiquement cohérent autour de "language") ; **aucune amélioration en FR** (0/20) — révèle au passage un second problème : des candidats malformés ("travers l'étude", "questions relatives à l'" tronqué avant le nom), signe d'un bug de découpage indépendant du choix d'algorithme.

---

### Diagnostic et correction du bug d'élision FR + re-test X64 — 2026-06-22

**Contexte** : les candidats malformés détectés ci-dessus en FR avec PositionRank.

**Ce qui a été fait** : diagnostic direct via spaCy (`en_core_sci_sm`/`fr_core_news_sm`) montrant que `fr_core_news_sm` mistague l'élision FR (`l'`, `d'`, apostrophe typographique `'`) en `NOUN` au lieu de `DET`, cassant le découpage des noun chunks. Correction de `clean_chunk_span()` (`loterre_extract_cli.py`, détection par motif textuel + `dep_=="fixed"`, indépendante du POS). Re-extraction sur X64_fr complet (C-value) avant/après.

**Résultats** : top20 in_vocab FR 0/20 → 4/20, apparition de vrais termes ("langue maternelle", "linguistique cognitive"), taux global 18.0 % → 19.2 %. Aucune régression EN (P66_en/P66_fr identiques). Le bruit académique générique restant (hors élisions) n'est pas résolu par ce fix — confirmé comme un problème structurel de C-value, pas un bug.

---

### Premier test Phase 5 (`--extractor embed`) sur P66_en — 2026-06-23

**Contexte** : validation initiale du nouvel extracteur par similarité aux embeddings Loterre (`paraphrase-multilingual-MiniLM-L12-v2`), juste après son implémentation, sur un corpus propre (P66, mémoire/cognition) avant test sur le cas difficile X64.

**Ce qui a été fait** : `extract_annotate --extractor embed --dict-id P66_en`, inspection des 15 meilleurs candidats par score (similarité cosinus au centroïde).

**Résultats** : tous les candidats du top 15 sont pertinents au domaine (*cognition*, *sensory memory*, *episodic memory test*, *controlled memory assessment*, *simulated amnesia*...), scores de 0.79 à 0.15 sur l'ensemble des 84 candidats — confirme que le mécanisme fonctionne correctement avant le test sur cas plus difficile.

---

### Validation Phase 5 embed sur X64 + calibration `--min-freq` — 2026-06-23

**Contexte** : test décisif — `embed` règle-t-il le problème de bruit académique qui a motivé la Phase 5 ?

**Ce qui a été fait** : extraction `--extractor embed` sur X64_en/X64_fr à `--min-freq` par défaut (2), puis 5/10/15/20, comparaison du top 20 par score à chaque palier.

**Résultats** : à `--min-freq` par défaut, des candidats courts/peu fréquents (souvent mono-token, parfois noms propres — *"era"*, *"de"*, *"co"*, *"pas"*) obtiennent des scores artificiellement élevés (limite connue des embeddings de phrase sur texte court). En relevant `--min-freq` : EN top20 in_vocab 7/20 (cvalue) → 9/20 (graph) → **13/20** (embed, `--min-freq` 10) ; FR 0/20 → 0/20 → **9-10/20** (embed, `--min-freq` 5-10). Recommandation retenue : `--min-freq 5` à `10` avec `--extractor embed` sur gros corpus (vs 2 par défaut, calibré pour ncvalue/graph).

---

### Benchmark ACTER (Phase 6) — comparaison à froid ncvalue vs PositionRank — 2026-06-23

**Contexte** : mesure rigoureuse, externe et comparable à une baseline publiée (D-Terminer, F1 0.32–0.50 sur ACTER), après les analyses informelles sur X64.

**Ce qui a été fait** : nouveau script `scripts/evaluation/acter_eval.py` — réalignement des tokens gold ACTER (tokenisation LeTs Preprocess) sur des offsets caractères du texte brut, comparaison token-level. Coupure top-N (N = nb de termes gold uniques du domaine) pour comparer le **classement** des deux extracteurs, pas l'ensemble brut de candidats (identique entre `ncvalue`/`graph`, partageant la même extraction noun-chunk amont — sans cette coupure, scores strictement identiques, piège détecté avant le run final). `--min-freq 1` (vs défaut 2, trop strict pour ces corpus de domaine restreint). 4 domaines (corruption, équitation, insuffisance cardiaque, énergie éolienne) × 2 langues (EN, FR) × 2 extracteurs = 8 combinaisons.

**Résultats** :

| Domaine | EN F1 ncvalue | EN F1 graph | FR F1 ncvalue | FR F1 graph |
|---|---:|---:|---:|---:|
| corp | 0.34 | 0.33 | 0.35 | 0.34 |
| equi | 0.36 | 0.58 | 0.28 | 0.54 |
| htfl | 0.53 | 0.55 | 0.41 | 0.51 |
| wind | 0.44 | 0.52 | 0.28 | 0.50 |
| **TOTAL** | **0.391** | **0.496** | | |

PositionRank devance C-value sur les 8 combinaisons. F1 global 0.496 (PositionRank, sans GPU/fine-tuning) au sommet de la fourchette D-Terminer (0.32–0.50, mBERT+RNN, GPU). Détail : `benchmark_results/acter/acter_results.{json,md}` (non commités, gitignorés).

---

### Variante expérimentale embed semi-supervisé sur ACTER — 2026-06-23

**Contexte** : question utilisateur après le benchmark ci-dessus ("tu ne peux pas inclure embed ?") — `embed` ne peut pas être comparé à froid (besoin d'un vocabulaire cible, qu'ACTER n'a pas). Variante semi-supervisée proposée et acceptée pour évaluer informativement la capacité d'enrichissement.

**Ce qui a été fait** : pour chaque domaine, moitié des termes gold = vocabulaire de référence ("seed", centroïde de comparaison), l'autre moitié ("held-out") = objectif à retrouver. Tokens appartenant à un terme seed entièrement exclus du calcul P/R/F1 (ni TP/FN ni FP/TN) pour ne mesurer que la capacité à généraliser au-delà du vocabulaire donné. Clairement étiqueté "EXPÉRIMENTAL", section séparée du tableau principal (pas une comparaison à froid légitime).

**Résultats** : F1 global = **0.306** — *moins bon* que C-value (0.391) et PositionRank (0.496) évalués à froid, même avec la moitié des réponses données comme vocabulaire de référence. Hypothèse retenue : un centroïde unique (moyenne) est trop grossier pour capturer la diversité interne d'un domaine restreint (contrairement à X64 où le vocabulaire Loterre complet, des milliers de termes, donne un signal de filtrage de bruit académique nettement plus riche).

---

### Passage centroïde → plus proche voisin pour `embed`, revalidation X64 + ACTER — 2026-06-23

**Contexte** : question utilisateur après les résultats ci-dessus ("je trouve qu'il y a bcp de termes simples dans la version embed, pourquoi ?"). Investigation : composition du vocabulaire X64 (58.2% EN / 61.5% FR de concepts à un seul mot — noms de langues/ethnies, X64 est un vocabulaire de type Ethnologue) — un centroïde unique (moyenne) brouille cette diversité sémantique et favorise mécaniquement les candidats courts, qui dominent la composition du vocabulaire. Proposition retenue : remplacer la similarité au centroïde par la similarité au terme le **plus proche** (max) du vocabulaire cible.

**Ce qui a été fait** :
1. Réécriture de `src/loterre_embed.py` : `compute_centroid()` supprimé, remplacé par `embed_vocabulary_terms()` (matrice normalisée, un vecteur par terme du vocabulaire) ; `score_candidates_embed()` calcule désormais `max` de la similarité cosinus sur toute la matrice (au lieu de la similarité à une moyenne unique), avec `.clip(-1.0, 1.0)` pour absorber un dépassement float32 (`1.0000002` observé sur un candidat identique à un terme du vocabulaire).
2. Revalidation X64 EN+FR : top 20 par score passe de 13/20 (EN) et 9-10/20 (FR) avec le centroïde à **20/20 dans les deux langues** avec le plus proche voisin — et ceci dès `--min-freq` par défaut (2), sans le réglage 5-10 auparavant nécessaire.
3. Recalibration de `--enrichment-threshold` (suggestions d'ajout au vocabulaire) : à l'ancien défaut (0.5, hérité du centroïde où les scores étaient plus bas en moyenne), 77% des candidats X64 (1856/2406) étaient signalés comme suggestions, bruit inclus (*era*, *de*, *co*, *pas*, un nom propre — scores 0.93-0.96 avec le plus proche voisin). Testé 0.5/0.8/0.9/0.95/0.98/0.99 : **défaut relevé à 0.95** (liste raisonnable), 0.98-0.99 donnant une liste courte quasi sans bruit pour qui veut être plus strict.
4. Revalidation de la variante expérimentale embed semi-supervisée sur ACTER (`--skip-cold` ajouté à `acter_eval.py` pour ne relancer que cette section sans répéter ncvalue/graph, inchangés).
5. Ajustement de `tests/smoke/test_embed.sh` : seuil de test relevé de 0.5 à 0.8 (les scores plus proche voisin sont systématiquement plus hauts que l'ancien centroïde, un seuil bas ne filtrait plus rien).

**Résultats ACTER (embed semi-supervisé, 8 combinaisons, micro-moyenne)** :

| | centroïde (ancien) | plus proche voisin (nouveau) |
|---|---:|---:|
| Precision | 0.461 | **0.728** |
| Recall | 0.229 | **0.243** |
| F1 | 0.306 | **0.364** |

Amélioration nette sur précision ET rappel (pas seulement un compromis). Reste sous C-value (0.391) et PositionRank (0.496) évalués à froid, mais l'écart se réduit sensiblement — confirme que le plus proche voisin généralise mieux que le centroïde même sur un vocabulaire de référence artificiellement restreint, pas seulement sur un grand vocabulaire Loterre établi comme X64. Détail par domaine dans `benchmark_results/acter/acter_results_embed_seeded.json`/`acter_results.md` (non commités, gitignorés).

---

### Phase 4 — Détection de variantes (TermSuite) + validation sur 3 vocabulaires — 2026-06-23

**Contexte** : reprise de la Phase 4 (mise en attente depuis la session du passage centroïde → plus proche voisin). Demande explicite : mécanisme à motivation linguistique, en réutilisant les règles par langue de TermSuite (CNRS/TTC), puis tester sur un corpus autre que X64 pour vérifier que le calibrage généralise.

**Ce qui a été fait** : lecture directe de `termsuite-resources` (Apache 2.0) — `{fr,en}-variants.yaml` (~450 règles/langue) pour la taxonomie réelle, puis vendoring de `{fr,en}/morphology/{suffix-derivation-bank,suppletives-bank}.txt` (FR : 303 + 319 lignes ; EN : 17 + 0, pas de classes supplétives anglaises curées). Nouveau `src/loterre_variants.py` : 6 mécanismes généralisés (`morph_inflection`, `graphical`, `morph_prefix`, `syn_expansion`, `syn_permutation`, `morph_derivation`) au lieu de répliquer les ~450 règles par langue. Sortie additive (`canonical_form`/`variant_type` sur `CandidateTerm`), option CLI explicite `--detect-variants` (défaut désactivé). Test smoke `tests/smoke/test_variants.sh` (1 cas construit par catégorie + non-régression sans le flag).

**Quatre bugs trouvés et corrigés en validant sur données réelles** (X64, P66, puis un corpus réel de paléoclimatologie fourni par l'utilisateur, `/home/schneist/data/paleo/paleo17500/txt`, jumelé au vocabulaire QX8) :
1. Faux regroupement par transitivité (union-find sur une relation non-équivalente) — ex. *"semantic memory"* groupé à tort sous *"controlled memory assessment"* via une chaîne d'intermédiaires partageant juste *"memory"*. Corrigé par affectation directe sans transitivité.
2. Gérondifs anglais mal étiquetés VERB par spaCy (*"spacing effect"*, *"sandwich effect"*) disparaissant à tort du squelette de contenu. Corrigé en ajoutant VERB aux POS de contenu.
3. Dérivation N↔N (déverbal, ex. *"modeling"*/*"model"*) et classes supplétives (ex. *"psychologie"*/*"esprit"*, *"calcul"*/*"mesure"*) trop permissives. Corrigé : `morph_derivation` restreint aux paires A↔N, classes supplétives retirées (rôle différent chez TermSuite : décomposition de composés, pas synonymie de mots entiers).
4. Préfixe court coïncident (*"age"*/*"images"*) et acronyme confondu avec un homographe (*"GRACE"*/*"grâce"*). Corrigés par une longueur de radical minimale et une exception tout-capitales.

**Résultats** (après corrections, candidats groupés / total, échantillon inspecté manuellement par catégorie à chaque fois) :

| Corpus | Vocabulaire | % multi-mots | Candidats | Groupés |
|---|---|---:|---:|---:|
| X64 EN | X64 | 38% | 1232 | 367 (29.8%) |
| X64 FR | X64 | 42% | 2427 | 792 (32.6%) |
| P66 EN | P66 | 89% | 203 | 36 (17.7%) |
| P66 FR | P66 | — | 84 | 17 (20.2%) |
| Paléoclimatologie (794 docs réels) | QX8 | 49% | 2322 | 875 (37.7%) |

Performance : 794 documents réels traités en 44s avec `--detect-variants` — pas de ralentissement notable. Limite résiduelle acceptée (documentée, pas résolue) : `morph_prefix` garde un faux positif occasionnel sur des mots latins à préfixe historique mais non séparable synchroniquement (ex. *"information"*/*"formation"*) — nécessiterait un vrai lexique de dérivation, hors contrainte "pas de ressource lourde".

---

### Filtre de candidats et termes à tiret/slash internes (TermSuite vs whitelist ciblée) — 2026-09-07

**Contexte** : suite à la réflexion en cours sur le rappel bas d'`embed` (§8 de `planif_extraction_terminologique.md`), question utilisateur : les termes scientifiques non purement composés de mots (codes, formules, composés à tiret — ex. *"renin-angiotensin-aldosterone"*, *"ISO/IEC 27001"*) sont-ils seulement captés à l'étape 1 (extraction de candidats, avant tout scoring) ? Diagnostic : `is_valid_candidate()` rejetait **tout le span** dès qu'un token interne était `is_punct` — or spaCy tokenise très souvent le tiret/slash d'un composé scientifique comme un token PUNCT/SYM séparé (`renin-angiotensin-aldosterone` → 5 tokens, 2 tirets isolés), contrairement à un tokenizer type TreeTagger (utilisé par TermSuite) qui garde le composé en un seul token. Mesuré sur le gold ACTER EN (4 domaines) : 6.5–13.2% des termes gold contiennent un tiret/slash, et 93% d'un échantillon aléatoire (htfl) voient effectivement leur séparateur tokenisé à part par `en_core_web_sm` → candidat jamais généré, quel que soit l'extracteur choisi ensuite (ncvalue/graph/embed).

**Investigation TermSuite** (clone local Apache 2.0, `/home/schneist/app/termsuite-core`) avant de choisir un correctif : `TermSuiteConstants.COMPOUND_CHAR`/`HYPHEN = '-'` et `{en,fr}/*-allowed-chars.txt` (`abc...xyz0-9-`) montrent que le tiret fait partie de l'alphabet d'un mot chez eux, jamais un motif de rejet — cohérent avec leur tokenizer externe (TreeTagger, via `TildeTokenizer.java`) qui ne coupe jamais un composé à tiret en tokens séparés. Leur filtre de qualité réel, `CharacterFootprintTermFilter.java`, n'est pas binaire : il tolère un seul "mot sale" (caractère hors alphabet) par occurrence, et rejette seulement si plus d'un mot est sale OU si le taux global de caractères "mauvais" dépasse 41%.

**Deux approches testées et comparées** (rappel "oracle" = candidat exact présent dans l'ensemble extrait, avant scoring — isole précisément l'effet du filtre, sans le coût d'un run complet ncvalue/graph/embed) sur les 4 domaines ACTER EN, `--min-freq 1` :
1. **Whitelist de connecteurs** (`-`/variantes unicode/`/`, occurrences illimitées dans le span) — traduction directe du principe TermSuite ("le tiret fait partie du mot") à notre modèle où le tiret est un token séparé.
2. **Graduée façon `CharacterFootprintTermFilter`** (≤1 token "sale" par span, sinon rejet si le taux de caractères "sales" ≥ 41%) — traduction plus littérale du mécanisme TermSuite, sans liste blanche de caractères.

| | n_candidats | rappel global | rappel sous-ensemble tiret/slash |
|---|---:|---:|---:|
| baseline (avant fix) | 19 631 | 0.553 | 0.021 |
| **1 — whitelist connecteurs** | 21 317 | **0.606** | **0.412** |
| 2 — graduée (TermSuite) | 21 827 | 0.603 | 0.385 |

**Résultat** : l'approche 1 domine sur les trois axes (rappel global, rappel ciblé, et moins de candidats ajoutés donc moins de bruit). L'approche 2, pourtant plus fidèle au mécanisme TermSuite, est moins bonne ici : sa règle "≤1 token sale" a du sens chez TermSuite parce que leur tokenizer ne fragmente jamais un composé à tiret (0 token sale par construction) — transposée à notre modèle, elle rejette encore les composés à 2 tirets ou plus (*"renin-angiotensin-aldosterone"*, *"raf-mek1/2-erk1/2"* — 2 tokens "sales" > 1), qui sont justement fréquents dans le domaine htfl (cardiologie). **Approche 1 retenue et implémentée** dans `is_valid_candidate()` (`src/loterre_extract_cli.py`, constante `_CONNECTOR_PUNCT`).

**Vérification sur le F1 réel (`acter_eval.py` complet, EN+FR, 8 combinaisons, `--min-freq 1`, `benchmark_results/acter_after_fix/`)** — comparé aux chiffres avant fix déjà journalisés ci-dessus :

| | avant fix | après fix | Δ |
|---|---:|---:|---:|
| ncvalue F1 | 0.391 | 0.398 | +0.007 |
| PositionRank (graph) F1 | 0.496 | 0.498 | +0.002 |
| embed (semi-supervisé) F1 | 0.364 | 0.359 | −0.005 |

**Résultat honnête, pas celui attendu** : le F1 officiel (mesuré après coupure top-N = nombre de termes gold uniques) ne bouge quasiment pas, malgré le gain net de rappel candidat brut (+5.3 pts global, +39 pts sur le sous-ensemble tiret/slash) mesuré plus haut. Explication cohérente : les candidats à tiret/slash nouvellement récupérés existent maintenant dans le pool, mais ce sont pour beaucoup des composés rares (fréquence basse dans un corpus de domaine restreint) — `ncvalue`/`graph`/`embed` les classent bas, et ils ne passent pas la coupure top-N qui détermine ce qui est réellement évalué. **Le fix lève un plafond dur (un candidat absent du pool ne peut jamais être retrouvé, quel que soit le scoring) mais ne suffit pas seul à en tirer parti** — il faut un mécanisme de scoring qui remonte ces candidats structurellement valides malgré leur rareté. Ça renforce directement l'intérêt de la piste 5 (scoring hybride embed + ncvalue/graph, §8 de `planif_extraction_terminologique.md`) : sans elle, une bonne partie du gain de ce fix reste latente, invisible dans la métrique top-N actuelle.

---

### Mesure du signal structurel (Option 3 §8) sur ACTER — 2026-09-07

**Contexte** : Option 3 (§8 de `planif_extraction_terminologique.md`) implémentée — double signal exposé (`enrichment_suggestion` = embed seul, `enrichment_suggestion_structural` = catégorie séparée pour les candidats absents du vocabulaire, sous le seuil embed, mais dans le top 10% du classement C-value/PositionRank). Mesure dédiée nécessaire (le F1 top-N existant ne s'applique pas à une décision de seuil binaire) : nouvelle fonction `evaluate_domain_lang_structural_signal()` dans `acter_eval.py`, même split seed/holdout que la variante embed semi-supervisée existante, mais applique les **vrais seuils de production** (`--enrichment-threshold 0.95`, `--structural-top-pct 10`) plutôt que la coupure oracle top-N=nb-de-termes-holdout (qui suppose connaître à l'avance combien de candidats chercher — un luxe qui n'existe pas en usage réel).

**Résultat (8 combinaisons domaine/langue, micro-moyenne)** :

| | Precision | Recall | F1 |
|---|---:|---:|---:|
| embed seul (`enrichment_suggestion`) | 0.858 | 0.127 | 0.222 |
| embed + structurel (`enrichment_suggestion` ∪ `enrichment_suggestion_structural`) | 0.422 | 0.313 | 0.360 |

**F1 net +0.138 (+62% relatif)**, porté par un rappel qui plus que double (0.127 → 0.313) — mais **la précision chute de moitié** (0.858 → 0.422). Décomposition isolée de la catégorie structurelle seule (par soustraction, tp=7103/fp=15583) : precision ≈ **0.313**, largement en dessous des 0.858 d'embed seul — c'est un signal beaucoup plus bruité pris isolément, cohérent avec le risque anticipé ("réintroduction du bruit que le passage centroïde → plus proche voisin avait filtré"). Le gain de F1 combiné vient du fait que le rappel de départ (0.127) était si bas qu'même un ajout bruité reste rentable en agrégé — pas d'une catégorie structurelle intrinsèquement fiable.

**Interprétation, pas de décision automatique prise** : le choix de garder les deux catégories **séparées** (Option 3, pas de fusion en un score unique) prend ici tout son sens — un curateur peut traiter `enrichment_suggestion` comme une liste haute confiance (P=0.858) et `enrichment_suggestion_structural` comme une liste "à vérifier" à part (P≈0.313, environ 1 candidat sur 3 pertinent). Fusionner les deux en un score aurait dilué cette distinction.

**Balayage de `--structural-top-pct` (2/5/10/15/20/30%), même méthodologie, une seule extraction par domaine/langue réutilisée pour tous les seuils testés** :

| Variante | Precision | Rappel | F1 |
|---|---:|---:|---:|
| embed seul | 0.858 | 0.127 | 0.222 |
| top 2% | 0.568 | 0.232 | 0.329 |
| top 5% | 0.482 | 0.271 | 0.347 |
| top 10% (défaut actuel) | 0.422 | 0.313 | 0.360 |
| top 15% | 0.383 | 0.343 | 0.362 |
| top 20% | 0.352 | 0.367 | 0.359 |
| top 30% | 0.346 | 0.436 | 0.386 |

**Le F1 n'a pas de pic net dans la plage testée** — il monte de 0.222 (embed seul) à 0.329 dès 2%, puis reste globalement plat entre 10% et 30% (0.360→0.362→0.359→0.386, non monotone, probablement du bruit inter-domaine plutôt qu'un vrai optimum local à 20%). Le vrai levier n'est pas où mettre le curseur pour maximiser le F1 (n'importe quelle valeur ≥10% donne un F1 comparable) mais **le compromis precision/volume que le curateur est prêt à absorber** : à 2%, la liste structurelle reste relativement propre (P=0.568, déjà +0.107 de F1 par rapport à embed seul) ; à 30%, le rappel est maximal mais la précision tombe à 0.346 (moins de 1 candidat sur 3 pertinent), sur une liste beaucoup plus longue. Le principe déjà acté du projet ("la précision des candidats proposés compte plus que l'exhaustivité", `CLAUDE.md` §Objectif produit principal) penche pour un défaut plus proche de 2-5% que de 10% — **non tranché, décision utilisateur à prendre**, le défaut code (10%) n'a pas été changé dans cette session.

Détail par domaine/langue : `benchmark_results/acter_structural_signal/acter_results_structural_signal.json` (non commité, gitignoré).

**Confirmation — run complet officiel `make benchmark-acter` après le changement de défaut (2026-09-07)** : ncvalue/graph à froid, embed semi-supervisé et signal structurel relancés ensemble (pas de scripts ad hoc séparés) avec les seuils désormais committés (`--structural-top-pct 2`, `--enrichment-threshold 0.95`). Chiffres identiques au sweep ci-dessus (P=0.568/R=0.232/F1=0.329 pour embed+structurel) — cohérence vérifiée entre le script de sweep et `acter_eval.py`. Artefacts canoniques dans `benchmark_results/acter/` (non commité, gitignoré).

---

### Motifs N-prep-N (`--prep-patterns`, adapté de TermSuite) — 2026-09-10

**Contexte** : question utilisateur suite à la lecture de `termsuite-resources/en/english-multi-word-rule-system.regex` — spaCy `doc.noun_chunks` (seule source de candidats jusqu'ici, `loterre_extract_cli.py`) a-t-il un angle mort structurel sur les termes de forme "N of/with N" (ex. *"quality of service"*, *"rate of change"*) ? Vérifié empiriquement avant tout code : sur EN (`en_core_web_sm`) et FR (`fr_core_news_sm`), `noun_chunks` scinde systématiquement ces constructions en deux chunks séparés ("Quality"/"service"), jamais un span unique — confirmé aussi par le motif `npn` (`N1 P ~D? N`) de TermSuite, qui existe précisément pour ce cas.

**Ce qui a été fait** : ajout de `--prep-patterns` (opt-in, défaut désactivé — même prudence que `--detect-variants`) dans `loterre_extract_cli.py` : un `spacy.matcher.Matcher` sur les POS tags (pas de dépendance au dependency parser) ajoute 4 motifs en EN (`npn`, `npnn`, `npan`, `anpn` — préposition `of`/`with`) et 2 en FR (`npn`, `npnn` — préposition `de`/`avec` ; motifs avec ADJ non repris en FR faute de liste d'exclusion d'adjectifs génériques validée pour cette langue, contrairement à l'anglais où TermSuite fournit la sienne). Chevauchement avec les noun_chunks dédupliqué par `spacy.util.filter_spans` (le plus long gagne). Mesuré en deux temps sur le gold ACTER (4 domaines × 2 langues, `--min-freq 1`) :
1. Rappel candidat oracle (avant tout scoring, `extract_candidates()` appelé directement) — global et sur le sous-ensemble de termes gold contenant `" of "`/`" with "` (EN) ou `" de "`/`" avec "` (FR).
2. F1 réel (`score_extracted_candidates()`, ncvalue et graph, coupure top-N = nb de termes gold uniques — même méthodologie qu'`evaluate_domain_lang()` dans `acter_eval.py`).

**Résultats** :

| | rappel global | rappel sous-ensemble N-prep-N (n=560) | n_candidats |
|---|---:|---:|---:|
| `--prep-patterns` désactivé (baseline) | 0.5435 | 0.0071 | 38 282 |
| `--prep-patterns` activé | 0.5799 | **0.4839** | 50 149 |

Gain massif et attendu sur le rappel candidat ciblé (0.7% → 48.4%) — le motif comble bien le trou identifié. Mais **vérification sur le F1 réel, résultat honnête, pas celui attendu** (même pattern que le fix tiret/slash du 2026-09-07) :

| Extracteur | F1 baseline | F1 avec `--prep-patterns` | Δ |
|---|---:|---:|---:|
| ncvalue | 0.3974 | 0.4003 | +0.003 (bruit) |
| graph (PositionRank) | **0.5001** | **0.4370** | **−0.063** |

Le C-value reste globalement stable ; PositionRank **régresse nettement** (précision et rappel baissent tous les deux dans la coupure top-N). Explication cohérente : les nouveaux candidats N-prep-N combinent souvent deux noms déjà "forts" isolément (les deux extrémités du span sont des nœuds centraux du graphe de co-occurrence) et héritent d'un bon score PositionRank sans être eux-mêmes de vrais termes gold — ils prennent la place de candidats corrects dans le budget fixe du top-N. Même diagnostic que pour le fix tiret/slash : lever un plafond dur sur la génération de candidats ne suffit pas seul si le scoring en aval ne sait pas distinguer les nouveaux candidats structurellement valides du bruit qu'ils introduisent — renforce à nouveau l'intérêt de la piste 5 (scoring hybride, §8 de `planif_extraction_terminologique.md`).

**Suite — sweep de la coupure top-N (question utilisateur "et si on baisse le top-N ?")** : la coupure `N = n_gold_terms` ci-dessus est un artefact d'évaluation (comparer un classement à taille de gold inconnue en pratique), pas une profondeur réelle d'usage — testé donc à plusieurs fractions de `n_gold_terms` (0.10 à 2.00×, même esprit que le sweep `--structural-top-pct` du 2026-09-07), micro-moyenne sur les 8 combinaisons :

| Fraction de n_gold_terms | ncvalue ΔF1 | graph ΔF1 |
|---:|---:|---:|
| 0.10 | **+0.032** | −0.017 |
| 0.25 | **+0.037** | −0.061 |
| 0.50 | **+0.036** | −0.056 |
| 0.75 | **+0.029** | −0.069 |
| 1.00 | +0.003 | −0.063 |
| 1.50 | −0.039 | −0.052 |
| 2.00 | −0.073 | −0.038 |

Résultat plus nuancé que la seule coupure N=1.00× : pour **ncvalue**, `--prep-patterns` améliore nettement le F1 aux coupures agressives/précision (+0.03 à +0.04 de N=0.10 à N=0.75×) et ne devient négatif qu'au-delà de N=1.5× (liste trop longue, bruit qui dépasse le gain). Pour **graph (PositionRank)**, la régression est présente à **toute profondeur testée**, y compris au sommet du classement (N=0.10× : déjà −0.017) — donc pas un simple artefact de coupure, mais une vraie pollution du haut du classement PositionRank par ces candidats composés. Cohérent avec l'hypothèse ci-dessus : PositionRank scoring des mots individuels puis agrégation par span profite structurellement aux N-prep-N (deux nœuds déjà centraux), alors que C-value (fréquence + emboîtement) est moins sensible à cet effet.

**Décision révisée** : `--prep-patterns` reste **opt-in, non activé par défaut** globalement, mais l'analyse par extracteur ouvre une piste concrète : combiné à `--extractor ncvalue` **et** une coupure précision (`--max-terms`/`--cvalue-threshold` restrictif, cohérent avec le principe projet "précision compte plus"), `--prep-patterns` apporte un gain net mesuré (+0.03 à +0.04 F1) plutôt qu'un simple pool de candidats élargi pour un futur scoring hybride. À ne **pas** combiner avec `--extractor graph`/`auto` sur corpus court (régression à toute profondeur) — c'est justement le régime par défaut sur un document unique, donc pas un candidat à l'activation par défaut de `--extractor auto`. Pas encore implémenté (pas de garde-fou code empêchant `--prep-patterns --extractor graph`) — décision utilisateur à prendre sur la suite (garde-fou explicite, documentation seule, ou rien pour l'instant). Scripts de mesure ad hoc, non committés (`bench_prep_patterns.py`/`bench_prep_patterns_f1.py`/`bench_prep_patterns_topn_sweep.py`) ; détail dans `benchmark_results/prep_patterns_*.json` (non commités, gitignorés).

---

### Grammaire complète TermSuite non-noisy (`--all-candidate-patterns`) — 2026-09-10

**Contexte** : suite du fil `--prep-patterns` — l'utilisateur fournit le vrai fichier TermSuite FR (`termsuite-resources/fr/french-multi-word-rule-system.regex`, mes motifs FR précédents `de`/`avec` seulement étaient une approximation ad hoc, pas la grammaire réelle) et demande d'implémenter **toutes** les règles non annotées "noisy" des deux fichiers (EN + FR), déclenchées par un nouveau flag, avec la question ouverte : réserver ça à `ncvalue` seulement ? et `embed` ?

**Ce qui a été fait** :
- Transcription fidèle des deux grammaires dans `loterre_extract_cli.py` (`_EN_GRAMMAR_RULES`/`_FR_GRAMMAR_RULES`, 37 règles EN + 34 règles FR, tout ce qui n'est pas marqué `# noisy` ou commenté par TermSuite elle-même). Simplifications documentées en commentaire faute de moteur Ruta pour vérifier certains opérateurs exacts (`~D`/`~D?` traité comme déterminant optionnel, `~Og`/`~Fg` comme guillemets littéraux non négés, A2(FR) simplifié à ADJ seul — `fr_core_news_sm` étiquette déjà la plupart des participes passés adjectivaux en ADJ directement, vérifié empiriquement).
- Correction FR importante par rapport à `--prep-patterns` : le motif `P` de base de la vraie grammaire FR n'est **pas** restreint à `de`/`avec` (contrairement à ce que j'avais supposé) — c'est n'importe quelle préposition (`ADP` général) ; seuls `Pde`/`Pa` (motifs `npnpn`/`npvinf`) sont restreints à `de`/`à` spécifiquement.
- **Bug potentiel identifié et corrigé avant tout bench** : avec autant de règles, beaucoup chevauchent un noun_chunk existant sans lui être identiques (ex. "quality" (noun_chunk) et "quality of service" (motif `npn`) au même point de départ). Une première version utilisait `spacy.util.filter_spans` (le plus long gagne) pour fusionner — ce qui aurait **supprimé** les candidats courts imbriqués dans un composé plus long à cette occurrence précise, cassant l'hypothèse de C-value classique (Frantzi et al. 1998) que la fréquence brute d'un candidat court inclut ses occurrences imbriquées (la formule C-value soustrait l'absorption elle-même). Remplacé par une déduplication stricte sur `(start_char, end_char)` **identiques** uniquement — un vrai doublon (ex. "machine learning" produit à la fois par noun_chunks et par le motif `nn`) est éliminé, mais les spans imbriqués-mais-différents (immense majorité des cas) sont tous deux conservés comme candidats séparés, conforme au design C-value existant.
- Flag `--all-candidate-patterns` (renommé depuis la suggestion `--all-candidats-patterns` pour rester cohérent avec le nommage anglais du reste de la CLI), prioritaire sur `--prep-patterns` si les deux sont passés (sous-ensemble strict). Même méthodologie de mesure que `--prep-patterns` : rappel candidat oracle + sweep top-N (ncvalue/graph, `--min-freq 1`, 8 combinaisons domaine/langue).

**Résultats** :

| | rappel candidat global | n_candidats |
|---|---:|---:|
| `--all-candidate-patterns` désactivé (baseline) | 0.5435 | 38 282 |
| `--all-candidate-patterns` activé | **0.8294** | 97 339 |

Rappel candidat oracle massivement amélioré (+28.6 pts absolus), au prix de +154% de candidats.

Sweep top-N (fraction de `n_gold_terms`), micro-moyenne 8 combinaisons :

| Fraction | ncvalue ΔF1 | graph ΔF1 |
|---:|---:|---:|
| 0.10 | **+0.129** | −0.033 |
| 0.25 | **+0.129** | −0.099 |
| 0.50 | **+0.120** | −0.122 |
| 0.75 | **+0.111** | −0.120 |
| 1.00 | **+0.079** | −0.118 |
| 1.50 | +0.018 | −0.100 |
| 2.00 | −0.031 | −0.074 |

Même schéma qu'avec `--prep-patterns` mais amplifié (grammaire ~9× plus large) : **ncvalue gagne nettement à presque toutes les profondeurs** (F1 0.257→0.386 à N=0.10×, soit +50% relatif ; reste positif jusqu'à N=1.5×), **graph régresse à toute profondeur testée**, plus fortement qu'avec `--prep-patterns` seul (jusqu'à −0.122 à N=0.50×). Cohérent avec le diagnostic déjà posé : PositionRank sur-score structurellement les composés dont les extrémités sont des nœuds déjà centraux du graphe de co-occurrence, quelle que soit leur validité terminologique réelle ; C-value (fréquence + emboîtement) n'a pas ce biais et profite au contraire du pool de candidats élargi.

**Question "et pour embed ??" — pas mesuré** : `sentence-transformers`/`torch` absents de cet environnement (pas de venv projet actif), utilisateur a explicitement refusé l'installation pour ce test (`--embed` du script de bench prévu mais non exécuté). Réponse qualitative faute de mesure : le mécanisme de pollution identifié pour `graph` est spécifique à PositionRank (un span hérite du score de ses mots parce qu'ils sont des nœuds centraux du graphe de co-occurrence, indépendamment de la validité du span composé) — `embed` ne partage pas ce mécanisme, il score chaque candidat indépendamment par similarité cosinus à son propre contenu sémantique, donc *a priori* moins vulnérable à ce biais précis. Mais attention : `_attach_structural_signal()` (le signal structurel secondaire d'`embed`, `enrichment_suggestion_structural`) réutilise en interne **exactement** `score_candidates`/`score_candidates_positionrank` (bascule auto selon le volume de corpus) — donc combiner `--all-candidate-patterns` avec `--extractor embed` sur un corpus court hériterait indirectement de la même pollution PositionRank **pour le signal structurel seulement**, pas pour `enrichment_suggestion_embed` (gouverné par le seuil de similarité, indépendant de ce mécanisme). Affirmation non vérifiée empiriquement — à mesurer avant toute décision de production sur ce point précis.

**Suite — question utilisateur "intéressant d'activer par défaut ?" → mesure de temps réel** : le gain F1 ci-dessus vient d'une coupure top-N artificielle de l'évaluation ; en usage réel le volume de candidats explosé (+154%) n'a pas de coupure équivalente par défaut. Mesuré le temps réel (`time`, CLI complète subprocess, modèle spaCy inclus) sur trois tailles de corpus réalistes, comparé à `annotate` (contrainte non négociable du projet, `CLAUDE.md` : "extract ne doit pas être significativement plus lent qu'annotate") :

| Corpus | annotate | extract ncvalue (baseline) | extract ncvalue (`--all-candidate-patterns`) |
|---|---:|---:|---:|
| 1 document (P66, ~3k car.) | 7.2s | 1.0s | 1.0s |
| 11 documents (P66 complet) | 8.4s | 1.2s | 1.3s |
| **190 documents (ACTER htfl EN, ~59k tokens)** | 10.6s | **12.2s** | **66.0s** |

Sur document unique ou petit lot (le cas d'usage courant), le flag est gratuit — le chargement du modèle spaCy domine tout. Mais sur un gros corpus (le régime exact où `--extractor ncvalue` est auto-sélectionné), `--all-candidate-patterns` fait passer `extract` de 12.2s à 66.0s, soit **~6× plus lent qu'annotate** — violation directe de la contrainte non négociable.

**Cause identifiée** : `build_containment_map()` (`loterre_cvalue.py`) est une double boucle sur tous les candidats — O(n²), déjà le cas avant ce flag. Le nombre de candidats sur ce domaine passe de ~6 500 à ~16 000 (×2,46) avec `--all-candidate-patterns` ; (2,46)² ≈ 6,05, cohérent avec le ×5,4 mesuré. Goulot d'étranglement architectural préexistant, amplifié par le volume de candidats supplémentaire — pas un bug introduit par ce flag, mais un effet de bord qui le rend inutilisable tel quel sur gros corpus.

**Décision finale** : `--all-candidate-patterns` reste **opt-in, non activé par défaut** — confirmé indépendamment par deux arguments distincts : (1) régression F1 systématique avec `graph`/`auto` sur corpus court (déjà établi ci-dessus), et (2) coût O(n²) prohibitif avec `ncvalue` sur gros corpus, précisément là où le gain F1 avait été mesuré. Pas de configuration où l'activation par défaut serait sûre sans changement complémentaire (coupure de candidats par défaut, et/ou optimisation de `build_containment_map` au-delà du scope de cette session). Pas de garde-fou code empêchant la combinaison risquée — décision utilisateur en attente si un garde-fou explicite est souhaité. Script de mesure ad hoc non committé (`bench_all_candidate_patterns.py`), sortie non sauvegardée en JSON (résultats agrégés reportés ci-dessus depuis la sortie console).

---

### Mesure de spécificité (Weirdness Ratio, TermSuite) — 2026-09-11

**Contexte** : suite du fil `planif_extraction_terminologique.md` §9 — TermSuite trie ses candidats par "Specificity" par défaut (pas C-value, confirmé dans `default-extractor-config.json` : `"ranking": {"property": "SPECIFICITY"}`), un contraste de fréquence corpus analysé vs référence "langue générale" (`{en,fr}-general-language.txt`, vendorisé dans `resources/termsuite_general_language/`). Sanity-check qualitatif préalable (bruit générique très fréquent en langue générale vs vrais termes de domaine absents/rares) concluant — voir §9 du plan pour le détail.

**Ce qui a été fait** : implémenté `src/loterre_specificity.py` (`score_candidates_specificity()`, moyenne géométrique du Weirdness Ratio sur les mots de contenu du candidat, réutilise `per_doc_tokens` déjà collecté par `extract_candidates()` — pas de second passage spaCy). Bug corrigé pendant le prototypage : mots-outils adjectivaux/adverbiaux absents de la table (limitée aux mots de contenu) lus à tort comme "très spécifiques" — corrigé en excluant `_GENERIC_ADJ_EN`/`_GENERIC_ADV_EN` de l'agrégation. Benchmarké sur ACTER (8 combinaisons domaine/langue, `--min-freq 1`, sweep top-N identique aux bench `--prep-patterns`/`--all-candidate-patterns` du 2026-09-10), deux framings :

**1. Classement autonome** (spécificité seule vs `ncvalue`/`graph`) :

| Fraction | ncvalue | graph | specificity |
|---|---:|---:|---:|
| 0.10 | 0.257 | 0.145 | 0.108 |
| 0.50 | 0.344 | 0.389 | 0.270 |
| 1.00 | 0.397 | 0.500 | 0.377 |
| 2.00 | 0.505 | 0.551 | 0.525 |

Plus faible que `ncvalue`/`graph` aux coupures serrées (précision-first) — la spécificité seule ne capture pas la structure/forme d'un terme. **Rejeté comme 4ᵉ `--extractor` autonome.**

**2. Filtre de bruit** (retire les candidats sous la spécificité médiane du corpus avant `ncvalue`/`graph`) :

| Fraction | ncvalue Δ | graph Δ |
|---|---:|---:|
| 0.10 | −0.030 | −0.002 |
| 0.50 | −0.024 | −0.007 |
| 1.00 | **+0.029** | −0.015 |
| 1.50 | **+0.045** | −0.030 |
| 2.00 | +0.001 | −0.040 |

**Résultat mitigé** : aide `ncvalue` aux coupures moyennes/larges (+0.02 à +0.045) mais nuit systématiquement à `graph` (jusqu'à −0.04, à toute profondeur). Coupure médiane (50%) probablement mal calibrée — même limite déjà rencontrée avant le sweep `--structural-top-pct` du 2026-09-07.

**Décision initiale** : ni classement autonome ni filtre médian fixe concluants tels quels avec une coupure à 50%. Suspendu avant de balayer le seuil de filtre.

**Suite (même session, 2026-09-11) — balayage du seuil (0/10/20/30/40/50/60/70%, `ncvalue` uniquement)** :

| % retiré | F1 top-N=0.10× | F1 top-N=0.50× | F1 top-N=1.00× | F1 top-N=1.50× |
|---:|---:|---:|---:|---:|
| 0 (baseline) | 0.257 | 0.344 | 0.397 | 0.455 |
| 10 | 0.258 | 0.346 | 0.402 | 0.462 |
| 20 | 0.259 | 0.350 | 0.420 | 0.474 |
| 30 | 0.258 | 0.350 | 0.431 | 0.495 |
| **40** | 0.252 | 0.345 | **0.447** | **0.518** |
| 50 | 0.227 | 0.319 | 0.427 | 0.500 |
| 60 | 0.199 | 0.320 | 0.426 | 0.455 |
| 70 | 0.171 | 0.304 | 0.390 | 0.392 |

**Résultat net cette fois** : **40% est un pic clair** aux coupures moyennes/larges (top-N=1.00× : +0.050 absolu/+12.6% relatif ; top-N=1.5× : +0.063/+13.8%), quasi neutre aux coupures serrées (−0.005 à top-N=0.10×, négligeable). Le 50% testé initialement était déjà **au-delà** du pic — d'où le résultat mitigé precedent, pas une propriété du signal lui-même mais un mauvais calibrage du seuil. Confirme le signal comme réellement exploitable, contrairement à la première mesure.

**Implémenté** : `filter_by_specificity()` dans `src/loterre_specificity.py`, exposé via `--specificity-filter-pctl` (0 = désactivé par défaut, appliqué **avant** `score_extracted_candidates()`) dans `loterre_extract_cli.py`/`loterre_cli.py`. Toujours **restreint à `--extractor ncvalue`** — aucun garde-fou code, juste documenté dans l'aide CLI (`graph`/PositionRank dégradé par tout filtrage, testé au seuil 50% avant ce sweep, pas re-testé aux autres seuils — priorité donnée à `ncvalue` où le signal est net).

Scripts ad hoc non committés (`bench_specificity.py`/`bench_specificity_filter.py`/`bench_specificity_threshold_sweep.py`), sortie non sauvegardée en JSON.

---

### Spécificité comme troisième signal de suggestion pour `embed` — 2026-09-11

**Contexte** : suite directe de l'entrée précédente — question utilisateur "pas de spécificité dans le cadre d'embed ?". Le filtre `ncvalue` (ci-dessus) est un mécanisme différent (retire des candidats avant scoring) ; ici on teste la spécificité comme **signal additionnel** pour `--extractor embed`, sur le modèle du signal structurel (Option 3, §8) plutôt qu'en filtre.

**Ce qui a été fait** : script ad hoc (`bench_specificity_embed.py`, pas `acter_eval.py`), méthodologie semi-supervisée seed/holdout identique à `evaluate_domain_lang_structural_signal()` (seed=42, fraction=0.5), 8 combinaisons domaine/langue ACTER. Nécessite `sentence-transformers`/`torch`, absents de l'environnement de dev WSL — installés en cours de session (`pip install --user --break-system-packages`, l'installation standard a échoué avec `externally-managed-environment`, protection PEP 668 de Debian/Ubuntu).

**Résultats** :

| | Precision | Rappel | F1 |
|---|---:|---:|---:|
| `embed` seul | 0.899 | 0.114 | 0.203 |
| + structurel (2%) seul | 0.641 | 0.171 | 0.270 |
| + spécificité (2%) seul | 0.656 | 0.135 | 0.224 |
| + spécificité (5%) seul | 0.580 | 0.156 | 0.246 |
| + spécificité (10%) seul | 0.500 | 0.182 | 0.267 |
| + structurel(2%) OU spécificité(2%) | 0.558 | 0.192 | 0.286 |
| + structurel(2%) OU spécificité(5%) | 0.530 | 0.212 | 0.302 |
| **+ structurel(2%) OU spécificité(10%)** | 0.492 | 0.231 | **0.314** |
| spécificité **isolée** (niveau 3 seul : ni embed ni structurel) | **0.271–0.305** | 0.021–0.060 | 0.039–0.099 |

La combinaison (union) bat les deux signaux séparés à tous les seuils testés (+16% relatif vs structurel seul, +18% vs spécificité seule à 10%) — les deux signaux ratent des choses différentes (structurel = force statistique/positionnelle dans le corpus, spécificité = rareté vs langue générale), leur union récupère plus de vrais termes (rappel 0.171→0.231). **Mais la précision isolée du niveau 3** (mesurée séparément, candidats marqués par la spécificité seule hors union) **est nettement plus faible que celle du niveau 2** (~0.27-0.30 contre ~0.64) — le gain de F1 combiné masquait un signal individuellement bien plus bruité, dans la même veine que le fix tiret/slash et `--all-candidate-patterns` : un chiffre agrégé flatteur peut cacher un coût réel côté qualité/volume.

**Décision (utilisateur : "on en tire les conséquences, que proposes-tu")** : implémenté comme **troisième niveau de suggestion séparé** `enrichment_suggestion_specificity` (jamais fusionné avec les niveaux 1/2), **opt-in, désactivé par défaut** (`--specificity-top-pct 0.0`, contrairement au niveau 2 qui est actif par défaut) — la précision isolée nettement plus faible justifie de ne pas l'imposer, contrairement au filtre `ncvalue` (purement technique, pas de coût qualité pour le curateur) qui n'avait que des contraintes de performance/extracteur. Si activé, **10%** est la valeur mesurée utile.

**Implémenté** :
- `score_extracted_candidates()` (`loterre_extract_cli.py`) prend un nouveau paramètre `lang` et appelle `score_candidates_specificity()` **systématiquement** pour `--extractor embed` (comme `_attach_structural_signal()`) — `specificity_score`/`specificity_rank` toujours renseignés pour `embed`, indépendamment de `--specificity-top-pct`.
- `run_extract_annotate_mode()` (`loterre_cli.py`) : nouveau flag `--specificity-top-pct` (défaut 0.0, sous-parseur `extract_annotate`, même emplacement que `--enrichment-threshold`/`--structural-top-pct`), calcule `enrichment_suggestion_specificity` — mutuellement exclusif des niveaux 1/2.
- `enrichment_suggestion_specificity` ajouté au schéma `CandidateTerm`/`to_dict()`/export CSV.
- Testé de bout en bout (texte jouet + faux dictionnaire) : exclusivité mutuelle vérifiée, comportement neutre par défaut confirmé.
- Documentation mise à jour : `CLAUDE.md`, `docs/README.md` (§5.1/§5.3/§5.4), `docs/underthehood.md` (étape 7), `docs/curation_guide.md` (précision isolée du niveau 3 signalée explicitement comme plus faible que le niveau 2).

Script ad hoc non committé (`bench_specificity_embed.py`), sortie non sauvegardée en JSON.

---

## Références

- Mao et al. 2024 — *Attention-Seeker: Dynamic Self-Attention Scoring for Unsupervised Keyphrase Extraction* : https://arxiv.org/html/2409.10907
- Frantzi et al. 2000 — *Automatic recognition of multi-word terms: the C-value/NC-value method* : https://www.researchgate.net/publication/2937844_Corpus-Based_Terminology_Extraction_Applied_to_Information_Access
- Campos et al. 2020 — *YAKE! Keyword extraction from single documents using multiple local features* (Information Sciences) : https://www.sciencedirect.com/science/article/abs/pii/S0020025519308588
- Boudin 2018 — *Unsupervised Keyphrase Extraction with Multipartite Graphs* : https://www.researchgate.net/publication/324005691_Unsupervised_Keyphrase_Extraction_with_Multipartite_Graphs
- Jemec Tomažin et al. 2025 — *Extracting domain-specific terms using contextual word embeddings* : https://arxiv.org/html/2502.17278
- Florescu & Caragea 2017 — *PositionRank: An Unsupervised Approach to Keyphrase Extraction from Scholarly Documents*
- Bougouin et al. 2013 — *TopicRank: Graph-Based Topic Ranking for Keyphrase Extraction*
- Papagiannopoulou & Tsoumakas 2019 — *A Review of Keyphrase Extraction* : https://arxiv.org/abs/1905.05044
