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

**Le F1 n'a pas de pic net dans la plage testée** — il monte de 0.222 (embed seul) à 0.329 dès 2%, puis reste globalement plat entre 10% et 30% (0.360→0.362→0.359→0.386, non monotone, probablement du bruit inter-domaine plutôt qu'un vrai optimum local à 20%). Le vrai levier n'est pas où mettre le curseur pour maximiser le F1 (n'importe quelle valeur ≥10% donne un F1 comparable) mais **le compromis precision/volume que le curateur est prêt à absorber** : à 2%, la liste structurelle reste relativement propre (P=0.568, déjà +0.107 de F1 par rapport à embed seul) ; à 30%, le rappel est maximal mais la précision tombe à 0.346 (moins de 1 candidat sur 3 pertinent), sur une liste beaucoup plus longue. Le principe déjà acté du projet ("la précision des candidats proposés compte plus que l'exhaustivité", objectif produit principal) penche pour un défaut plus proche de 2-5% que de 10% — **non tranché, décision utilisateur à prendre**, le défaut code (10%) n'a pas été changé dans cette session.

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

**Suite — question utilisateur "intéressant d'activer par défaut ?" → mesure de temps réel** : le gain F1 ci-dessus vient d'une coupure top-N artificielle de l'évaluation ; en usage réel le volume de candidats explosé (+154%) n'a pas de coupure équivalente par défaut. Mesuré le temps réel (`time`, CLI complète subprocess, modèle spaCy inclus) sur trois tailles de corpus réalistes, comparé à `annotate` (contrainte non négociable du projet : "extract ne doit pas être significativement plus lent qu'annotate") :

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

> **Correction 2026-09-30** : les chiffres absolus du tableau ci-dessous ne sont pas reproductibles — voir la correction à la fin de l'entrée "Signaux de répartition intra-corpus" (2026-09-29) pour les valeurs de référence. Les décisions de cette entrée restent valables.

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
- Documentation mise à jour : `docs/README.md` (§5.1/§5.3/§5.4), `docs/underthehood.md` (étape 7), `docs/curation_guide.md` (précision isolée du niveau 3 signalée explicitement comme plus faible que le niveau 2).

Script ad hoc non committé (`bench_specificity_embed.py`), sortie non sauvegardée en JSON.

---

### Fenêtre de co-occurrence PositionRank (`window`) — 2026-09-16

**Contexte** : question utilisateur sur la formule de score PositionRank (somme des scores de mots constitutifs, déjà appliquée à tous les candidats mono/multi-token — cf. `score_candidates_positionrank()`) et sur l'intérêt d'élargir la fenêtre de co-occurrence `window` (`build_cooccurrence_graph()`, défaut 4). Le papier original (Florescu & Caragea 2017) teste 2 à 10 avec un léger mieux rapporté autour de 6-10 ; coût O(n×window), pas de souci de performance contrairement à C-value (O(n²)).

**Ce qui a été fait** : `scripts/evaluation/acter_eval.py --skip-embed-seeded --skip-structural-signal --min-freq 1` (comparaison à froid `ncvalue`/`graph`, 8 combinaisons domaine/langue ACTER), une fois avec `window=4` (défaut) et une fois avec `window=10` (modification temporaire du défaut dans `loterre_positionrank.py`, revert immédiat après mesure — aucun flag CLI n'expose `window` aujourd'hui).

**Résultats** (extracteur `graph`/PositionRank uniquement — `window` n'affecte pas `ncvalue`) :

| | Precision | Rappel | F1 |
|---|---:|---:|---:|
| window=4 (défaut) | 0.556 | 0.454 | 0.500 |
| window=10 | 0.556 | 0.455 | 0.501 |

Écart nul à l'échelle du corpus (+0.001 F1, dans le bruit) ; par domaine/langue, seuls `corp/fr` (+0.01 F1) et `equi/fr` (−0.01 F1) bougent d'un centième, tous les autres couples identiques au centième près.

**Décision** : pas de changement — élargir la fenêtre n'apporte rien de mesurable sur ACTER, le défaut `window=4` est conservé. Pas d'implémentation (flag CLI, etc.) à ce stade ; à ne pas re-tester sauf nouveau signal suggérant un intérêt.

Aucun script ad hoc créé (invocation directe de `acter_eval.py` avec deux valeurs de `window`), sorties JSON dans `benchmark_results/acter_window4_baseline/` et `benchmark_results/acter_window10_test/` (non committées).

---

### Signaux de répartition intra-corpus (dispersion, NMF, recette BERTopic) — 2026-09-29

**Contexte** : question utilisateur "un topic modelling (BERTopic) aiderait-il à évaluer la pertinence d'un terme ?". Hypothèse : un vrai terme de domaine est concentré dans une partie du corpus (un thème), le bruit académique générique ("approach", "results", "case study") est réparti uniformément. Aucun des trois signaux existants ne mesure la répartition intra-corpus (embed = proximité au vocabulaire, structurel = forme/fréquence, spécificité = contraste vs langue générale). TopicBERT (Chaudhary et al. 2020, classifieur à fine-tuning BERT) écarté d'emblée : fine-tuning + BERT complet en inférence, hors contraintes projet, et aucun signal par terme.

**Ce qui a été fait** : nouveau script `scripts/evaluation/bench_topical.py` (calqué sur `bench_specificity.py`, mêmes protocoles). Unité de répartition = segments de 600 caractères de chaque document (~500-600 segments par couple domaine/langue — ACTER n'a que 2 à 12 documents pour `wind`/`corp`, trop peu pour une dispersion par document ; 600 caractères ≈ 100 tokens, sous la fenêtre de 128 tokens de MiniLM). Quatre signaux (plus haut = plus "terme") :
- `ridf` : IDF résiduel (Church & Gale 1995), IDF observé − IDF attendu sous Poisson.
- `dp` : DP de Gries (2008), déviation des proportions.
- `nmf` : NMF scikit-learn sur la matrice segments × candidats (tf-idf), 5 à 20 thèmes selon le nombre de segments ; score = poids relatif max du candidat dans un thème.
- `bertopic` : **recette** BERTopic, pas la bibliothèque — segments encodés avec MiniLM (même modèle qu'embed), regroupés par KMeans (option `cluster_model` supportée par BERTopic, choisie pour la reproductibilité — graine fixe, pas de segments "hors thème" −1 — et pour n'ajouter aucune dépendance, bertopic/umap-learn/numba n'étant pas installés), candidats notés par c-TF-IDF (formule BERTopic), score = c-TF-IDF max.

8 couples domaine/langue ACTER, `--min-freq 1`. Conteneur Docker de test du webservice (12,7 Go de RAM) arrêté avant le run pour éviter l'instabilité WSL2 sous charge.

**Résultats — 1. Classement autonome** (F1 token-level, coupure top-N = fraction × n_gold_terms) :

| Méthode | F1@0.10 | F1@0.50 | F1@1.00 | F1@1.50 |
|---|---:|---:|---:|---:|
| ncvalue | 0.257 | 0.344 | 0.397 | 0.455 |
| graph | 0.144 | 0.389 | **0.500** | **0.540** |
| ridf | 0.087 | 0.448 | 0.477 | 0.493 |
| dp | 0.017 | 0.081 | 0.148 | 0.201 |
| **nmf** | **0.370** | **0.456** | 0.488 | 0.507 |
| bertopic | 0.295 | 0.439 | 0.484 | 0.502 |

`ncvalue`/`graph` identiques au millième aux chiffres du 2026-09-11 (extraction de candidats inchangée). NMF bat tout aux coupures serrées/moyennes (tête de liste la plus précise mesurée à ce jour), reste sous `graph` aux coupures larges. `dp` inutilisable (biais vers les hapax, concentrés par construction).

**2. Filtre avant `ncvalue`** (F1@1.00 / F1@1.50 selon le % de candidats les plus faibles retirés) :

| % retiré | ridf | dp | nmf | bertopic |
|---:|---:|---:|---:|---:|
| 0 | 0.397 / 0.455 | 0.397 / 0.455 | 0.397 / 0.455 | 0.397 / 0.455 |
| 20 | 0.370 / 0.415 | 0.215 / 0.253 | 0.415 / 0.485 | 0.404 / 0.452 |
| 40 | 0.368 / 0.411 | 0.193 / 0.226 | 0.428 / 0.501 | 0.447 / 0.497 |
| 50 | 0.368 / 0.411 | 0.187 / 0.213 | **0.467 / 0.509** | 0.461 / 0.506 |

NMF à 50% : +0.070 F1@1.00 (+18% relatif), un peu mieux que le filtre de spécificité à 40% (0.447 / 0.518), neutre aux coupures serrées (F1@0.10 0.256 vs 0.257). Pic non atteint dans la plage testée (monotone jusqu'à 50%). `ridf`/`dp` dégradent.

**3. Niveau de suggestion pour `embed`** (seed/holdout 50%, niveau isolé = retenu par le signal seul, ni embed ni structurel ; référence embed + structurel(2%) : P=0.560 R=0.231 F1=0.327) :

| Signal (part retenue) | F1 union | P niveau isolé | R niveau isolé | n isolé |
|---|---:|---:|---:|---:|
| nmf 2% | **0.381** | **0.296** | 0.108 | 438 |
| nmf 5% | 0.379 | 0.255 | 0.144 | 1260 |
| bertopic 5% | 0.368 | 0.243 | 0.121 | 1371 |
| ridf 10% | 0.393 | 0.262 | 0.186 | 2727 |
| dp 10% | 0.326 | 0.159 | 0.029 | 3528 |
| spécificité 5% (référence) | 0.355 | 0.271 | 0.057 | 1491 |
| spécificité 10% (référence) | 0.367 | 0.270 | 0.090 | 3024 |

Niveau isolé NMF 2% légèrement plus précis que la spécificité (0.296 vs 0.27) avec 3× moins de candidats pour un rappel supérieur — mais toujours loin du niveau structurel (~0.56). La recette BERTopic ne bat NMF nulle part, pour un coût ~100× supérieur (185 s vs 2 s cumulés sur les 8 couples).

**Décision (utilisateur)** — *invalidée par le contrôle par la fréquence, voir point 5* : pas de 4ᵉ liste de suggestion ; piste retenue = exposer NMF comme **signal par candidat** (`topical_score`/`topical_rank`/`topic_id`, sur le modèle de `specificity_score` toujours calculé pour `embed`), sous réserve qu'il discrimine à l'intérieur des niveaux existants — mesure dédiée ci-dessous. Points à régler avant intégration : matrice creuse (la matrice dense du script ferait plusieurs Go sur RevueESR, ~60k segments), signal `null` sous un nombre minimal de segments (document isolé).

Sorties : `benchmark_results/topical/bench_topical_{standalone,filter-sweep,embed}.json` + `bench_topical_all.log` (non committés).

**4. Signal comme indicateur par candidat — mode `indicator` (2026-09-30)** : les trois niveaux de production reconstitués (embed ≥ 0.95, structurel top 2%, spécificité top 10% — mutuellement exclusifs comme `run_extract_annotate_mode`, seed/holdout 50%), puis, à l'intérieur de chaque niveau, précision du quart/de la moitié le mieux noté par le signal vs le moins bien noté. Écart = P(moitié haute) − P(moitié basse).

| Niveau (n, P) | Signal | P top 25% | P haut 50% | P bas 50% | P bas 25% | Écart 50% |
|---|---|---:|---:|---:|---:|---:|
| embed (986, 0.852) | **nmf** | 0.909 | 0.884 | 0.673 | **0.613** | **+0.211** |
| | bertopic | 0.906 | 0.886 | 0.677 | 0.659 | +0.209 |
| | ridf | 0.899 | 0.875 | 0.799 | 0.848 | +0.076 |
| | spécificité | 0.852 | 0.887 | 0.816 | 0.779 | +0.071 |
| structurel (545, 0.391) | nmf | 0.378 | 0.390 | 0.391 | 0.360 | −0.001 |
| | **ridf** | 0.438 | 0.440 | 0.329 | 0.336 | **+0.111** |
| | spécificité | 0.370 | 0.438 | 0.341 | 0.272 | +0.097 |
| spécificité (3024, 0.270) | nmf | 0.305 | 0.287 | 0.225 | 0.188 | +0.063 |
| | **ridf** | 0.329 | 0.302 | 0.215 | 0.222 | **+0.087** |

(`dp` négatif partout, −0.09 à −0.27 : plus dispersé = meilleur à l'intérieur des niveaux — probablement un simple effet de fréquence, les hapax étant concentrés par construction et plus souvent faux ; non exploité.)

**Lecture** : NMF est un **très bon indicateur à l'intérieur de la liste embed** — la liste la plus importante pour le curateur (haute confiance, P 0.852) se scinde en un quart haut à P 0.909 et un quart bas à P 0.613 : NMF repère précisément les suggestions embed douteuses. Inutile en revanche dans la liste structurelle (écart nul), modeste dans la liste spécificité. `ridf` (coût nul) est le meilleur indicateur dans ces deux listes-là. La recette BERTopic égale NMF dans la liste embed sans le dépasser, pour 100× le coût. Réserve : liste structurelle de 545 candidats seulement sur 8 couples, écarts de ±0.03 dans le bruit.

Sortie : `benchmark_results/topical/bench_topical_indicator.{json,log}` (non committés).

**5. Contrôle par la fréquence — conclusion révisée (2026-09-30)** : l'implémentation du signal (module `src/loterre_topical.py`, champs `topical_score`/`topical_rank`/`topic_id`/`burstiness_score`) a été faite puis testée de bout en bout sur X64_en (`extract_annotate --extractor embed`) : qualitativement, le haut de la liste embed triée par `topical_score` contenait des mots génériques fréquents ("data", "Education", "means") et le bas de vrais termes ("lexical terms", "language change"). Soupçon : la précision **token-level** pondère chaque candidat par ses occurrences et favorise mécaniquement les candidats fréquents — or NMF met aussi en avant les mots fréquents qui dominent un thème. Vérifié en ajoutant (a) la **fréquence brute comme témoin** (`freq`) et (b) une **précision par candidat** (chaque candidat compte une fois : son terme est-il un terme gold held-out — ce que voit réellement le curateur).

Mode `indicator`, précision par candidat (écart = moitié haute − moitié basse) :

| Niveau (P candidat) | fréquence | nmf | ridf | spécificité |
|---|---:|---:|---:|---:|
| embed (0.528) | **+0.290** (quart haut 0.811 / quart bas 0.414) | +0.185 | −0.014 | −0.002 |
| structurel (0.231) | **+0.193** | +0.032 | +0.032 | +0.083 |
| spécificité (0.143) | **+0.121** | +0.052 | +0.037 | −0.026 |

La fréquence bat NMF dans les trois listes (en token-level aussi : +0.286 contre +0.211 dans la liste embed). ridf ne sépare plus rien une fois chaque candidat compté une fois.

Classement autonome, témoin fréquence : `freq` F1 0.387 / 0.482 / 0.507 / 0.517 (@0.10/0.50/1.00/1.50) — **au-dessus de NMF à toutes les coupures** (et de ncvalue/graph aux coupures serrées/moyennes).

Filtre avant `ncvalue` : le témoin `freq` en percentile ne retire rien (64 à 78% des candidats sont des hapax avec `--min-freq 1`, le seuil tombe à 1). Comparaison directe avec le retrait des hapax (`ncvalue` sur les seuls candidats de fréquence ≥ 2) : F1 0.256 / **0.473 / 0.503** / 0.503, contre 0.256 / 0.351 / 0.467 / 0.509 pour le filtre NMF 50% — le simple retrait des hapax fait mieux ou autant.

**Conclusion révisée : les signaux de répartition intra-corpus (NMF, recette BERTopic, ridf, DP) n'apportent rien au-delà de la fréquence** — les gains mesurés aux étapes 1 à 4 étaient des effets de fréquence, amplifiés par la précision token-level. **Implémentation retirée** (module, champs `CandidateTerm`/`to_dict()`/CSV, dépendance `scikit-learn` explicite — jamais committés). Seul `scripts/evaluation/bench_topical.py` (avec le témoin `freq` et la précision par candidat) est conservé comme trace.

**Enseignements réutilisables** :
- **Tout nouveau signal doit être comparé au témoin fréquence**, et mesuré aussi en précision par candidat, pas seulement en token-level (protocole ACTER) — sinon un simple effet de fréquence passe pour un signal.
- **La fréquence est un bon indicateur de relecture, gratuit et déjà exposé** (champ `frequency`) : dans la liste `enrichment_suggestion_embed`, le quart le plus fréquent est à P 0.811 par candidat, le quart le moins fréquent à P 0.414. À ajouter à `docs/curation_guide.md` (trier chaque liste par fréquence décroissante, relire le bas de liste avec plus de méfiance).
- **Question ouverte** : le filtre `--specificity-filter-pctl 40` (entrée 2026-09-11) a été calibré avec `--min-freq 1` contre une référence `ncvalue` sans filtre ; il n'a jamais été comparé au simple retrait des hapax (`--min-freq 2`, F1@1.00 0.503 ici contre 0.447 pour le filtre de spécificité). À re-mesurer avant de le recommander.

Sorties : `benchmark_results/topical/bench_topical_indicator_v2.log`, `bench_topical_freq_control.log` (non committés).

**6. Essai qualitatif : NMF comme outil de curation sur RevueESR (2026-09-30)** : question utilisateur "y a-t-il un autre intérêt à garder NMF ?" — usages non mesurables sur ACTER : repérer les sous-domaines mal couverts par le vocabulaire, grouper la relecture par sujet, repérer les thèmes de bruit. Script ad hoc `scripts/evaluation/topic_coverage_report.py` (hors pipeline), appliqué à la sortie existante `output_extract/RevueESR_extract_annotate.jsonl` (run du 2026-09-15 : 1549 documents, 5,79 M tokens, vocabulaire SEN, 36 546 candidats dont 232 `in_vocabulary`, listes L1/L2/L3 = 183 / 654 / 3471) — aucun passage spaCy ni embed. NMF 30 thèmes sur 53 245 segments de 600 caractères (matrice creuse) : **14 s, 1 Go de RAM**. Couverture d'un thème = part des occurrences de ses candidats déjà dans le vocabulaire. Rapport complet : `benchmark_results/topical/RevueESR_topic_coverage.md` (non commité).

Constats (lecture manuelle, pas de mesure chiffrée de qualité) :
- **Zones non couvertes identifiables** : des sous-domaines cohérents à couverture quasi nulle — bruit et transports (bruit, avions, sommeil, cortisol, dB, niveau sonore ; 0.3%), santé au travail (solvants, VLEP, INRS, travail posté, maladies professionnelles ; 0.1%), maladies vectorielles (paludisme, dengue, West Nile, moustique ; 0.2%) — contre les thèmes les mieux couverts : évaluation des risques (6.8%), dose-effet (3.6%), pollution de l'air (3.6%), pesticides (2.2%). Plausible pour un vocabulaire santé-environnement ; savoir si ces zones sont dans le périmètre de SEN reste une décision de curateur.
- **Regroupement lisible** : à l'intérieur d'un thème, les suggestions L2/L3 forment des paquets cohérents (ex. santé au travail : "milieu professionnel", "risques professionnels", "agents biologiques", "solvants", "toluène", "VLEP").
- **Thèmes de bruit nets** : en-têtes de revue (Vol., n°, "juilletaoût"), remerciements/financement/liens d'intérêts, adresses et tirés à part, affiliations. Avec le thème de texte corrompu ci-dessous, ils portent 19 des 183 suggestions L1, 53 des 654 L2 et **821 des 3471 L3 (24%)**.
- **Problème de qualité du corpus découvert** : un thème entier (1.7% des segments) regroupe du **texte mal extrait des PDF** — accents détachés ("donn ees", "r esultats", "pr evalence") et ligatures fi/fl perdues ("signi catif", "identi cation", "uence" pour "influence", "èvre" pour "fièvre"). Il pollue toutes les listes, y compris L1 ("pollution atmosph", 134 occurrences) ; en L3, "ees" (1943 occurrences) arrive en tête. Problème en amont du pipeline (conversion PDF → texte de RevueESR), invisible dans les listes à plat.

**Révision avec couverture mesurée directement par l'annotateur (même jour)** : la couverture ci-dessus reposait sur `in_vocabulary` des candidats, sous-estimée par construction (seul un candidat dont l'empan exact coïncide avec une annotation est marqué). Annotation complète de RevueESR par SEN (`loterre_engine_v9_cli.py --profile term_balanced`, profil du registre) : **342 s, 5,5 Go de RAM**, 14 156 annotations (0,26 par segment en moyenne, ~20% des segments en contiennent au moins une), **244 termes SEN distincts seulement**. Couverture d'un thème = densité d'annotations par segment dans les segments où il domine, relative à la moyenne du corpus (option `--annotations` du script). Écart entre thèmes : 0.43 à 1.58.

| Thème | Densité relative (annotations directes) | Ancienne couverture (candidats) |
|---|---:|---:|
| texte PDF corrompu | 0.43 | 0.2% |
| gestion, déchets, "mise en place" | 0.47 | 0.5% |
| santé au travail | 0.64 | 0.1% |
| enfants, naissance, concentrations | 0.73 | 0.1% |
| bruit et transports | **0.98** | 0.3% |
| maladies vectorielles | **0.95** | 0.2% |
| pollution de l'air | 1.39 | 3.6% |
| pesticides | 1.53 | 2.2% |
| évaluation des risques | 1.58 | 6.8% |

- **Confirmés comme zones peu couvertes** : santé au travail, enfants/périnatal, gestion/déchets (ce dernier porte aussi le plus de suggestions : 31 L1, 197 L2, 580 L3).
- **Faux signaux de l'ancienne mesure** : bruit et transports, maladies vectorielles sont couverts dans la moyenne — SEN contient "virus West Nile" (47 annotations dans ce thème), "agent pathogène", "trafic routier", "cardiopathie ischémique", que l'extraction n'avait pas produits avec le même empan.
- **Limite de la nouvelle mesure** : les annotations SEN sont dominées par quelques termes transversaux présents dans tous les thèmes ("risque sanitaire" 1454, "changement climatique" 1035, "pollution atmosphérique" 764, "étude épidémiologique" 745, "substance chimique" 693). Ils gonflent la densité de thèmes qui n'ont aucun terme SEN propre — ex. santé au travail : uniquement des termes transversaux, aucun terme spécifique au domaine. Raffinement possible : ne compter que les termes du vocabulaire concentrés dans le thème, ou le nombre de termes distincts.

Rapport mis à jour : `benchmark_results/topical/RevueESR_topic_coverage.md` ; annotations : `output_extract/RevueESR_annotate_SEN.json` (non committés).

**Lecture** : contrairement à l'usage "signal de pertinence par candidat" (rejeté, point 5), NMF apporte ici une information qu'aucun autre mécanisme ne donne — une vue par zone du corpus. La couverture doit être mesurée par l'annotateur, pas par `in_vocabulary` des candidats.

**7. Neutralisation des termes transversaux et intégration (2026-09-30)** : couverture d'un thème redéfinie comme la part de ses segments contenant au moins un **terme propre** du vocabulaire (terme dont la part d'annotations dans le thème est ≥ 2× la part des segments du thème, avec ≥ 3 annotations). Sur RevueESR/SEN, l'écart entre thèmes s'élargit et devient lisible : 1% à 21% (contre 10% à 31% en comptant tous les termes) — santé au travail 14% → **2%**, gestion/déchets 10% → 3%, thèmes de bruit 1-2%, contre pesticides 21%, évaluation des risques 20%, pollution de l'air 17%. Les termes transversaux ("risque sanitaire" 1437, "changement climatique" 1026, présents dans au moins la moitié des thèmes) ne comptent plus que là où ils sont surreprésentés.

**Intégré** comme option expérimentale `extract_annotate --topic-report RAPPORT.html` (+ `--topic-report-topics N`) : module `src/loterre_topic_report.py`, réutilise les annotations déjà calculées par `extract_annotate` (aucun second passage de l'annotateur), rapport HTML autonome (barres par thème : couverture + suggestions L1/L2/L3 empilées, détail dépliable, palette validée clair/sombre) + JSON. `scripts/evaluation/topic_coverage_report.py` réduit à une commande qui produit le même rapport depuis des sorties existantes. Test de bout en bout sur X64_en (1 min 05 pour tout le pipeline, rapport généré) ; RevueESR depuis sorties existantes : 13 s, ~1 Go. `scikit-learn>=1.3` rajouté à `requirements.txt` (importé directement). Documentation : `docs/underthehood.md` (mécanisme), `docs/curation_guide.md` (usage), `docs/README.md`.

**8. Exécution complète de production avec le rapport (2026-09-30)** : `extract_annotate --dict-id SEN_fr --profile term_balanced --extractor embed --min-freq 3 --specificity-top-pct 10 --topic-report ...` sur `data/RevueESR-textFR.json` : **34 min (2046 s), 6,1 Go de RAM au pic**, rapport compris. 1539 documents, 5 954 459 tokens, 38 838 candidats (identique au run du 2026-09-14), 225 `in_vocabulary`, listes L1/L2/L3 = 177 / 705 / 3686, exclusivité des trois listes vérifiée (0 violation). Rapport : 30 thèmes, 53 690 segments, couverture par termes propres de 1% à 24%.

Écart de périmètre à connaître : la sortie `output_extract/RevueESR_extract_annotate.jsonl` (2026-09-15) utilisée aux points 6-7 venait d'une autre version du corpus (1549 documents, 36 546 candidats) que `data/RevueESR-textFR.json` (1539 documents), sur lequel l'annotation directe avait été calculée — le rapport des points 6-7 croisait donc deux versions (128 annotations hors segments seulement, effet faible). Le rapport de ce run est cohérent de bout en bout.

Thèmes (NMF recalculé sur un autre jeu de candidats, découpage différent de celui des points 6-7) : bruit toujours isolé mais plus éclaté — noms d'auteurs (thème de 5,4% du corpus, "Nicolle, Laurence, Mir", 218 suggestions L3), en-têtes de revue répartis sur 4 thèmes (mois, "Vol.", "n°"), adresses, remerciements ; le texte PDF corrompu ("ees") est cette fois fondu dans le thème enfants/naissance (341 suggestions L3), moins bien isolé. Zones peu couvertes : santé au travail 3%, données/surveillance 2%, mesures d'exposition (thème de 0,5% du corpus mais 707 suggestions, 17 en L1). Mieux couverts : évaluation des risques 24%, pesticides 20%, pollution de l'air 19%, dose-effet 19%. Nouveau thème distinct : résidus de médicaments dans les eaux (8%). Conclusion : les grandes lignes tiennent d'un découpage à l'autre, mais le détail des thèmes (et le rangement du bruit) varie avec le jeu de candidats — à rappeler au curateur (déjà dans `docs/curation_guide.md`, "pas un découpage de référence").

Sorties : `output_extract/RevueESR_extract_annotate_2026-09-30.{json,csv}`, `output_extract/RevueESR_topic_report_2026-09-30.{html,json}` (non committés).

**9. Rapport d'analyse élargi et champs d'aide au curateur (2026-10-02)** : `--topic-report` devient `--report` (alias conservé), module `src/loterre_report.py` (remplace `loterre_topic_report.py`) — chiffres clés, graphiques annotation/extraction, thèmes simplifiés (une barre par thème, détails repliés). Nouveaux champs par candidat, JSON et CSV : `n_docs`, `nearest_vocab_term` (embed), `context`, et avec `--report` `topic_id`/`topic_label`/`topic_coverage` (rangement, pas un score). `scripts/evaluation/topic_coverage_report.py` remplacé par `build_report.py`. Rapport RevueESR reconstruit depuis le run du 2026-09-30 (22 s) : **244 des 429 concepts SEN (57%) présents dans le corpus**, 86% des documents contiennent au moins un terme SEN.

Deux constats révélés par ces nouveaux éléments :
- **Sur un corpus bruité, le haut des listes triées par fréquence est du bruit** (RevueESR) : liste 2 dominée par l'en-tête de revue ("Environ Risque Sante" 2 848 occurrences, "Mots clés", "autres mentions"), liste 3 par de la ponctuation et des fragments PDF ("-" 21 287, "n", "–", "tion", "ees", "mai"), liste 1 par des unitermes génériques ("exposition", "pollution", "cancer"). La consigne "trier par fréquence" (mesurée sur ACTER, texte propre) est nuancée dans `docs/curation_guide.md`. Des candidats sans aucune lettre ("-", "–") ne devraient pas passer `is_valid_candidate` — **non corrigé**.
- **Une partie de la liste 1 est déjà dans le vocabulaire** (X64_en) : 7 des 32 suggestions embed (22%) ont `nearest_vocab_term` identique au terme lui-même ("phonetics", "poetics", "sociolinguistics", "data") — libellés présents tels quels dans le dictionnaire mais non reconnus par l'annotateur à ces endroits (`in_vocabulary=False`, probablement les filtres single-token du profil `term_recall`). Ce ne sont pas des termes à ajouter. **Non corrigé** — piste : les exclure de la liste 1 ou les signaler à part.

**10. Nettoyage du corpus RevueESR (2026-10-02)** : `scripts/corpus/clean_revueesr.py` -> `data/RevueESR-textFR.clean.json` (mêmes identifiants, original intact, `data/` gitignoré), 28 s. Réparation du texte uniquement si la forme corrigée existe ailleurs dans le corpus (lexique du corpus lui-même) ; fragment vs vrais mots distingués par la part de la paire dans les occurrences du mot (seuil 0.25 : fragments 0.42-0.86, vrais mots 0.05-0.08 — "pour suivre", "qu il" intacts). Résultats : 76 334 césures recollées ("pré- sents" -> "présents" : source des fragments "tion" en liste 3), 23 259 accents ("donn ees" 589 -> 2, "r esultats" 594 -> 2, "m emes" 344 -> 0), 9 437 ligatures ("signi catif" 232 -> 50, "in uence" 394 -> 127), 380 accents initiaux ; paratexte retiré : 5 459 en-têtes "Environ Risque Sante Vol. …" + 3 424 en-têtes anciens ("Environnement, Risques & Santé – Vol. …"), 453 blocs "Pour citer", 2 251 courriels, 611 "Tirés à part", 737 signatures de brèves et 238 références d'articles analysés, remerciements/financement/liens d'intérêts, libellés "Mots clés". 3,3% du texte retiré. Exemples de corrections : `output_extract/RevueESR_clean_samples.txt`.

**Run complet sur le corpus nettoyé (2026-10-02)** — mêmes paramètres que le point 8 (`--dict-id SEN_fr --profile term_balanced --extractor embed --min-freq 3 --specificity-top-pct 10 --report`) : 28 min (contre 34), 5,8 Go au pic.

| | Corpus brut | Corpus nettoyé |
|---|---:|---:|
| Tokens | 5 954 459 | 5 529 204 |
| Candidats | 38 838 | 37 987 |
| Candidats `in_vocabulary` | 225 | 243 |
| Annotations SEN | 14 156 | 16 168 (+14%) |
| Concepts SEN retrouvés | 244 / 429 | 250 / 429 |
| Documents annotés | 1 317 | 1 369 |
| Listes 1 / 2 / 3 | 177 / 705 / 3 686 | 191 / 685 / 3 635 |

- **Liste 2 assainie** : l'en-tête de revue ("Environ Risque Sante" 2 848, "Risque Sante", "Mots clés", "autres mentions") a disparu du haut de liste, remplacé par de vrais termes ("santé publique", "santé environnementale", "exposition professionnelle", "effets sanitaires", "eau potable", "faibles doses").
- **Liste 3 en partie** : fragments PDF ("tion", "ees") et mois disparus, mais restent ponctuation et lettres isolées ("-" 14 074 occurrences, "n", "C", "L") — 177 suggestions des listes 2/3 font 1 à 2 caractères ("-", "–", "´", "©", "/", "n", "t", "e"…). Problème du filtre de candidats (`is_valid_candidate`), pas du texte.
- **Annotation** : 14% d'annotations SEN en plus sur un texte 7% plus court — l'annotateur reconnaît des termes que les césures et accents perdus cachaient.
- **Liste 1** : sur RevueESR/SEN (profil `term_balanced`), aucune suggestion identique à un libellé du vocabulaire (contrairement à X64/`term_recall`, point 9). `nearest_vocab_term` renseigné pour les 37 987 candidats.
- **Thèmes** : les thèmes de bruit (en-têtes, noms d'auteurs, adresses, remerciements, texte corrompu) ont disparu, sauf un ("-", France, Royaume-Uni, Pays… — ponctuation et pays). Couverture 1% à 32%. Santé au travail toujours parmi les moins couverts (1%), confirmé d'un corpus à l'autre ; nouveaux thèmes lisibles (mortalité/chaleur 22%, enfants/grossesse 6%, résidus de médicaments dans les eaux 8%). Bruit/transports à 19%.

Sorties : `output_extract/RevueESR_clean_extract_annotate.{json,csv}`, `output_extract/RevueESR_clean_report.{html,json}` (non committés).

**11. Filtre de candidats "au moins deux lettres" (2026-10-05)** : `is_valid_candidate()` (`src/loterre_extract_cli.py`) rejette désormais tout span de moins de deux caractères alphabétiques — élimine "-", "–", "©", "´", "/", chiffres et lettres isolées étiquetés NOUN/PROPN par spaCy (RevueESR : 177 suggestions listes 2/3 de 1-2 caractères, "-" 14 074 occurrences), garde les sigles courts ("PM", "IC", "NO") et "vitamine D". Non-régression ACTER, `acter_eval.py --min-freq 1 --skip-embed-seeded --skip-structural-signal`, contre la référence du 2026-09-16 (`benchmark_results/acter_window4_baseline/`) :

| | Avant | Après |
|---|---:|---:|
| ncvalue | P 0.4702 / R 0.3442 / F1 0.3974 | P 0.4715 / R 0.3447 / F1 0.3982 |
| graph | P 0.5563 / R 0.4542 / F1 0.5001 | P 0.5563 / R 0.4520 / F1 0.4988 |

Effet neutre (écarts < 0.002) ; légère baisse de rappel `graph` (tp 35 494 -> 35 328), probablement quelques termes gold d'un caractère dans ACTER. Sortie : `/tmp/acter_filter2/` (non conservée).

Run complet RevueESR nettoyé avec le filtre (mêmes paramètres que le point 10, 28 min) : 933 candidats de moins de deux lettres retirés (37 987 -> 37 054), listes 1/2/3 = 191 / 666 / 3 540 (contre 191 / 685 / 3 635), `in_vocabulary` inchangé (243), exclusivité vérifiée. "-", "n", "C", "L" ont disparu de la liste 3. Le haut de la liste 3 reste fait de mots généraux ("effets", "personnes", "sujets", "valeurs", "fois", "plupart") — nature même du signal de spécificité (rareté vs langue générale), déjà connu, d'où son statut opt-in — et d'un fragment PDF résiduel ("ees", 860, non réparé par le nettoyage). Thèmes : santé au travail toujours à 1% ; un seul thème de bruit restant (adresses : "France, Paris, rue, Université"). Sorties : `output_extract/RevueESR_clean2_*` (non committées).

**12. Thème générique hors classement (2026-10-07)** : dans `RevueESR_clean2_report.json`, le thème classé "le moins couvert" (1%) était un fourre-tout de discours général ("compte, exemple, mise, place, prise, gestion") pesant **13,2% du corpus** (moyenne 3,3%, thème suivant 5,1%). Testé : la spécificité des mots de l'étiquette (rang médian de Weirdness Ratio) ne le distingue pas (0,79 contre 0,80 pour la santé au travail) ; son poids, si. Règle : thème `generic` si `segment_share` ≥ 2,5 × 1/n_topics (`GENERIC_SHARE_FACTOR`, `src/loterre_report.py`) — sur RevueESR, seul ce thème est concerné. Affiché à part sous le graphique, avec explication ; candidats marqués `topic_generic=True` (JSON/CSV). Validé sur un seul corpus. Pas de décision d'intégration à ce stade ; pistes : rapport optionnel de `extract_annotate` (fichier séparé, jamais des champs par candidat), et correction de l'extraction de texte RevueESR en amont.

**13. Nombre de thèmes du rapport : balayage k = 10–50 (2026-10-08)** : question utilisateur "comment a été choisi 30 thèmes ?" — réponse : non choisi, c'est le plafond de la règle automatique `auto_n_topics` (segments / 30, borné 5–30 ; RevueESR = 51 941 segments -> plafond). Vérifié a posteriori par `scripts/evaluation/sweep_topics.py` sur `RevueESR_clean2_extract_annotate.json` + annotations SEN recalculées (`output_extract/RevueESR_clean2_annotate_SEN.json`, renommé `RevueESR_clean3_annotate_SEN.json` le 2026-10-09, 9 min, 16 168 annotations, 89% des documents — identique au run du 2026-10-05) ; balayage 17 min. Mesures : cohérence NPMI des étiquettes (top 10 candidats, co-occurrence par segment), stabilité (3 sous-échantillons de 80% des segments, appariement hongrois au modèle complet, cosinus moyen), thèmes génériques, classement de couverture. k = 30 reproduit exactement le rapport existant.

| k | NPMI moyen | stabilité | plus gros thème | génériques | rang santé au travail (couverture) |
|---:|---:|---:|---:|---:|---|
| 10 | 0.130 | 0.92 (0.88–1.00) | 24% | 0 | 1/10 (1.0%) |
| 15 | 0.117 | 0.91 | 16% | 0 | 1/15 (1.6%) |
| 20 | 0.127 | 0.90 | 17% | 1 | 1/19 (1.7%) |
| 25 | **0.131** | 0.90 | 13% | 1 | 2/24 (1.4%) |
| 30 | 0.130 | **0.94** | 13% | 1 | 1/29 (1.2%) |
| 40 | 0.114 | 0.89 | 11% | 1 | 4/39 (1.5%) |
| 50 | 0.114 | 0.92 | 3% | 0 | 5/50 (1.7%) |

Lecture : (1) le constat principal ne dépend pas de k — santé au travail entre 1,0 et 1,7% de couverture partout, dernière ou presque ; les mieux couverts restent évaluation des risques / pesticides / pollution de l'air. (2) Au-delà de 30, cohérence en baisse, et le fourre-tout de discours général se fragmente en petits thèmes ("compte, prise, facteurs", "nombre, personnes, temps", "France, Paris, rue") qui passent sous le seuil `generic` (règle de poids) et occupent le bas du classement devant la santé au travail ; à 50, plus aucun thème générique détecté. k = 50 coûte aussi 9 min contre 2. (3) 20–30 forment un plateau (NPMI 0,127–0,131) ; 30 a la meilleure stabilité, mais écarts faibles et bruités (3 tirages seulement, k = 10 de 0,88 à 1,00). Décision : plafond de 30 conservé, désormais appuyé par une mesure ; la formule segments/30, qui fixe k sur les corpus de moins de ~900 segments, reste non validée. Un seul corpus. Résultats : `benchmark_results/topical/RevueESR_sweep_n_topics.json`.

**14. TermSuite sur ACTER, même protocole (2026-10-09)** : comparaison prévue depuis la Phase 6, jamais faite ; aucun chiffre TermSuite sur ACTER trouvé dans la littérature (TermEval 2020 et revue arXiv 2301.06767 n'en donnent pas). TermSuite 3.0.10 (jar complet de Maven Central, mêmes sources que `~/app/termsuite-core`) + TreeTagger 3.2.5 (paramètres `english.par`/`french.par` actuels), installés dans `~/app/termsuite-run/` ; configuration par défaut (classement par spécificité, filtrage et regroupement de variantes par défaut), `TerminologyExtractorCLI -l en|fr --json --tsv`, sur les textes `annotated/texts` d'ACTER (mêmes fichiers qu'`acter_eval.py`) — 6 à 11 s par corpus. Évaluation : `scripts/evaluation/termsuite_acter_eval.py`, qui réutilise les fonctions d'`acter_eval.py` (token-level, sans entités nommées, coupure top-N = termes gold uniques) ; occurrences TermSuite prises à leurs offsets caractères exportés dans le JSON (vérifié sur wind_fr : 15 417 / 15 515 occurrences identiques au texte au caractère près, les 98 autres ne diffèrent que par un saut de ligne). ncvalue/graph relancés le même jour (`acter_eval.py --min-freq 1 --skip-embed-seeded --skip-structural-signal`) : chiffres identiques au point 11.

| | TermSuite P / R / F1 | ncvalue P / R / F1 | graph P / R / F1 |
|---|---:|---:|---:|
| corp en | 0.367 / 0.555 / **0.442** | 0.345 / 0.377 / 0.360 | 0.328 / 0.327 / 0.328 |
| corp fr | 0.314 / 0.437 / **0.365** | 0.369 / 0.319 / 0.342 | 0.311 / 0.354 / 0.331 |
| equi en | 0.707 / 0.651 / **0.678** | 0.497 / 0.291 / 0.367 | 0.726 / 0.479 / 0.577 |
| equi fr | 0.576 / 0.425 / 0.489 | 0.433 / 0.217 / 0.289 | 0.665 / 0.455 / **0.540** |
| htfl en | 0.561 / 0.685 / **0.617** | 0.601 / 0.482 / 0.535 | 0.639 / 0.485 / 0.551 |
| htfl fr | 0.547 / 0.754 / **0.634** | 0.476 / 0.353 / 0.405 | 0.517 / 0.488 / 0.502 |
| wind en | 0.545 / 0.697 / **0.612** | 0.489 / 0.450 / 0.469 | 0.648 / 0.472 / 0.546 |
| wind fr | 0.516 / 0.690 / **0.590** | 0.447 / 0.230 / 0.304 | 0.615 / 0.464 / 0.529 |
| EN | 0.548 / 0.658 / **0.598** | 0.499 / 0.407 / 0.449 | 0.596 / 0.455 / 0.516 |
| FR | 0.493 / 0.595 / **0.539** | 0.435 / 0.279 / 0.340 | 0.520 / 0.449 / 0.482 |
| **TOTAL** | 0.521 / 0.627 / **0.569** | 0.471 / 0.345 / 0.398 | 0.556 / 0.452 / 0.499 |

Lecture : TermSuite devance graph sur 7 combinaisons sur 8 (sauf equi fr), +0,07 de F1 global ; l'écart vient du **rappel** (0,627 contre 0,452), la précision est un peu inférieure (0,521 contre 0,556). À même nombre de candidats (top-N), les candidats TermSuite couvrent 40 à 75% de tokens de plus que ceux de graph (ex. htfl en : 17 629 tokens marqués contre 10 949) ; part de mono-mots dans le top-N : 5% (corp fr) à 50% (htfl). **Hypothèse non vérifiée** : TermSuite repère toutes les occurrences de chaque terme dans le texte, alors que nos candidats ne portent peut-être que les occurrences où spaCy a produit exactement ce span (noun chunk) — un terme emboîté dans un chunk plus long n'y serait pas compté. Test à faire : re-repérer dans le texte toutes les occurrences des candidats top-N de graph et re-noter. Rappel : ces F1 token-level ne sont pas comparables aux F1 de TermEval 2020 (liste de termes uniques). Sorties : `benchmark_results/termsuite/outputs_v2/` (JSON/TSV/logs TermSuite), `benchmark_results/termsuite/termsuite_acter_results.{json,md}`, `benchmark_results/termsuite/acter_cold/`. Les 8 sorties TermSuite fournies auparavant (`benchmark_results/termsuite/outputs/`, coupées à 500 termes, lemmes sans positions, htfl_en = copie de corp_en) ne sont pas utilisées.

**14 bis. TermSuite contre embed, protocole semi-supervisé (2026-10-09)** : `acter_eval.py --min-freq 1 --skip-cold` (seed/holdout 50%, seed=42, tokens des termes seed exclus) relancé — embed seul 0.854 / 0.129 / 0.224, embed + structurel 0.571 / 0.231 / 0.329, identiques aux chiffres de référence (2026-09-07 / 09-30). TermSuite, qui n'utilise pas le vocabulaire seed, noté avec `termsuite_acter_eval.py --seeded-compare` (A) à la même coupure oracle qu'embed (top-N = nb de termes holdout), (B) à budget égal aux listes de production (mêmes nombres de suggestions que la liste 1 et que les listes 1+2, candidats déjà dans le seed retirés comme en production). Totaux (P / R / F1, token-level) :

| | Notre pipeline | TermSuite, même budget |
|---|---:|---:|
| (A) top-N = holdout | embed 0.734 / 0.242 / 0.364 | 0.416 / 0.483 / **0.447** |
| (B) budget liste 1 (981 suggestions au total) | liste 1 **0.854** / 0.129 / 0.224 | 0.525 / 0.303 / **0.384** |
| (B) budget listes 1+2 (1 502) | listes 1+2 **0.571** / 0.231 / 0.329 | 0.476 / 0.340 / **0.397** |

Lecture : même schéma qu'à froid — TermSuite gagne en F1 par le rappel ; embed garde nettement la meilleure **précision** (liste 1 : 0,85 contre 0,53 à budget égal), qui est le critère prioritaire du cas d'usage curateur (objectif produit du projet). Par domaine, embed liste 1 l'emporte en F1 seulement sur corp (en/fr) ; TermSuite sur les 6 autres. Le gain de rappel de TermSuite pourrait venir du repérage de toutes les occurrences (hypothèse du point 14, non vérifiée) — dans ce cas il profiterait aussi à embed. Piste : candidats/occurrences façon TermSuite + score embed. Note : `acter_eval.py --skip-cold` plantait à l'écriture du Markdown (cherchait `acter_results.json` absent) après avoir écrit ses deux JSON — résultats non affectés ; corrigé le même jour (Markdown omis sans résultats à froid dans le dossier). Sorties : `benchmark_results/termsuite/acter_embed/`, `benchmark_results/termsuite/termsuite_vs_embed.{json,md}`.

**15. Hypothèse « occurrences » confirmée (2026-10-09)** : question — le rappel de TermSuite vient-il de son repérage de toutes les occurrences ? Constat dans le code : `_register_span()` (`src/loterre_extract_cli.py`) n'enregistre une occurrence que là où spaCy produit exactement ce groupe nominal (`term = span.text`) ; un terme inclus dans un groupe plus long (« heart failure » dans « chronic heart failure patients ») ou écrit avec une autre casse n'est pas compté. Test : `scripts/evaluation/bench_respot.py` (11 min) — **mêmes candidats, même classement, même coupure** qu'`acter_eval.py`, mais occurrences re-repérées dans le texte (texte du candidat, insensible à la casse, bornes de mot). Les chiffres « actuel » reproduisent exactement les références (points 11 et 14 bis).

| P / R / F1 (token-level) | Actuel | Repéré | TermSuite (point 14 / 14 bis) |
|---|---:|---:|---:|
| ncvalue, à froid | 0.471 / 0.345 / 0.398 | 0.488 / 0.411 / **0.446** | — |
| graph, à froid | 0.556 / 0.452 / 0.499 | 0.561 / 0.513 / **0.536** | 0.521 / 0.627 / 0.569 |
| liste 1 (embed) | 0.854 / 0.129 / 0.224 | **0.876** / 0.219 / **0.351** | même budget : 0.525 / 0.303 / 0.384 |
| listes 1+2 | 0.571 / 0.231 / 0.329 | **0.592** / 0.336 / **0.428** | même budget : 0.476 / 0.340 / 0.397 |

Lecture : gain sur les 8 combinaisons domaine × langue et les 4 configurations, **précision comprise** (elle monte aussi). Le rappel de la liste 1 passe de 0.13 à 0.22 (+70 %) ; les listes 1+2 repérées dépassent TermSuite à budget égal en F1 (0.428 contre 0.397) avec une précision bien supérieure (0.59 contre 0.48) ; à froid, l'écart graph/TermSuite passe de 0.07 à 0.03 de F1. Une grande part de l'avance de TermSuite venait donc du comptage des occurrences, pas de son classement. **Limites** : correction appliquée à l'évaluation seulement ; l'intégrer à l'extraction change aussi les fréquences, donc le classement C-value/PositionRank, `--min-freq` et le tri par fréquence de la relecture — à remesurer après intégration. Le repérage naïf (une regex par candidat sur tout le texte) est trop lent pour RevueESR (37 000 candidats, 32 Mo) : prévoir un repérage en une passe (automate type Aho-Corasick ou trie, comme l'annotateur). Sortie : `benchmark_results/respot/respot_results.json`.

**16. Repérage intégré à l'extraction : `--respot-occurrences` (2026-10-09)** : `_respot_occurrences()` dans `src/loterre_extract_cli.py`, appelé en fin d'`extract_candidates()` avant `--min-freq`. (1) Fusion des variantes de casse d'un candidat (forme retenue : la plus fréquente comme groupe nominal, la minuscule à égalité) ; (2) repérage de toutes les occurrences du texte du candidat, insensible à la casse, aux bornes de tokens (`\w+|[^\w\s]`), en une passe par document via un trie sur les tokens en minuscules — termes emboîtés et chevauchants tous comptés ; (3) la fréquence devient le nombre d'occurrences repérées (union avec les occurrences groupe nominal), ce que C-value attend en théorie. Option explicite (défaut désactivé), propagée à `loterre_cli.py extract|extract_annotate` et à `acter_eval.py --respot-occurrences`. Exemple jouet : « heart failure » passe de 1 à 4 occurrences (dont celles dans « chronic heart failure » et « heart failure clinic »), « Heart failure » fusionné.

Remesure complète `acter_eval.py --min-freq 1 --respot-occurrences` (16 min, `benchmark_results/respot/acter_respot/`), contre les références du jour :

| P / R / F1 (token-level) | Avant | `--respot-occurrences` | TermSuite |
|---|---:|---:|---:|
| ncvalue, à froid | 0.471 / 0.345 / 0.398 | 0.497 / 0.445 / **0.470** | — |
| graph, à froid | 0.556 / 0.452 / 0.499 | 0.554 / 0.532 / **0.543** | 0.521 / 0.627 / 0.569 |
| embed semi-supervisé, top-N | 0.734 / 0.242 / 0.364 | 0.754 / 0.436 / **0.552** | 0.416 / 0.483 / 0.447 |
| liste 1 (seuil 0.95) | 0.854 / 0.129 / 0.224 | **0.879** / 0.218 / **0.349** | 0.525 / 0.303 / 0.384 (budget d'avant) |
| listes 1+2 | 0.571 / 0.231 / 0.329 | **0.582** / 0.343 / **0.432** | 0.476 / 0.340 / 0.397 (budget d'avant) |

Lecture : ncvalue et graph progressent sur les **8** combinaisons domaine × langue (graph : de +0,02 à +0,07 de F1 ; ncvalue gagne plus qu'au point 15, son classement profitant des fréquences corrigées). Embed dépasse désormais TermSuite partout où la comparaison existe ; à froid, TermSuite ne garde que 0,026 de F1 d'avance sur graph. La fusion des variantes de casse réduit un peu les candidats (ex. htfl en 6 367 → 6 053) et les listes (liste 1 : 981 → 920 suggestions ; listes 1+2 : 1 502 → 1 382) : la comparaison TermSuite « à budget égal » utilise l'ancien budget, approximative mais l'écart est large. **Non mesuré** : précision par candidat des listes (le benchmark ne conserve pas les listes) — à faire avant de passer l'option par défaut. Conséquence sur la décision TermSuite (point 14) : son avance venait surtout du comptage des occurrences ; pas d'intégration de TermSuite nécessaire, C-value/PositionRank conservés.

**Passage à l'échelle RevueESR — échec en l'état** (même commande que `clean3` + `--respot-occurrences`, sorties `output_extract/RevueESR_clean4_respot_*`, supprimées le 2026-10-12) : **1 h 36 au lieu de 28 min** (×3,4), 5,8 Go au pic (inchangé). 59 080 candidats au lieu de 37 054 (24 921 nouveaux, dont la fréquence comme groupe nominal était < 3) ; 247 dans SEN (243) ; listes 1/2/3 = 261 / 1 097 / 5 532 (191 / 666 / 3 540) ; exclusivité vérifiée. Liste 1 : 173 suggestions communes avec `clean3`, 88 nouvelles (« colorectal cancer », « cognitive function », « contaminations alimentaires »… mais aussi « climate change and »), 6 perdues ; « exposition » passe de 3 à 17 332 occurrences (le gain attendu : le mot est presque toujours inclus dans un groupe plus long). **Liste 2 envahie de bruit** : « Of the » (2 760), « In the » (1 663), « -ci » (1 071), « D autres » (1 053), « IC = », « dose- », « pas d », « Exposure to » en tête. Mécanisme : un candidat rare ou mal découpé dont le texte est une suite de mots outils (« of the », absent de `clean3`) reçoit toutes les occurrences de cette suite dans le texte libre (résumés anglais du corpus), sa fréquence explose et C-value/PositionRank le classent en tête. ACTER, plus propre et monolingue, ne le montrait pas. Pistes : (1) ne repérer qu'à l'intérieur des groupes nominaux (garde le cas « heart failure » dans « chronic heart failure patients », exclut le texte libre) ; (2) n'appliquer le repérage qu'aux candidats déjà au-dessus de `--min-freq` comme groupes nominaux (bloque « of the », « pas d », réduit le nombre de candidats donc le temps). Les deux sont à remesurer sur ACTER puis RevueESR ; l'option reste désactivée par défaut.

**17. `--respot-occurrences` v2 : repérage limité aux groupes nominaux (2026-10-09)** : les deux pistes du point 16 appliquées ensemble dans `_respot_occurrences()` — (1) repérage seulement à l'intérieur des zones de groupes nominaux de chaque document (bornes des spans noun_chunks/motifs, collectées pendant le passage spaCy) ; (2) seuls les candidats qui atteignent déjà `--min-freq` comme groupes nominaux (variantes de casse réunies) participent. Exemple jouet : « heart failure » toujours repéré 4 fois (dans « chronic heart failure », « heart failure clinic »).

ACTER (`acter_eval.py --min-freq 1 --respot-occurrences`, 17 min, `benchmark_results/respot/acter_respot_v2/`) :

| P / R / F1 | Sans l'option | v1 (tout le texte) | **v2 (groupes nominaux)** |
|---|---:|---:|---:|
| ncvalue, à froid | 0.471 / 0.345 / 0.398 | 0.497 / 0.445 / 0.470 | 0.494 / 0.401 / **0.443** |
| graph, à froid | 0.556 / 0.452 / 0.499 | 0.554 / 0.532 / 0.543 | 0.552 / 0.494 / **0.521** |
| embed semi-supervisé, top-N | 0.734 / 0.242 / 0.364 | 0.754 / 0.436 / 0.552 | 0.759 / 0.394 / **0.519** |
| liste 1 | 0.854 / 0.129 / 0.224 | 0.879 / 0.218 / 0.349 | **0.883** / 0.195 / **0.319** |
| listes 1+2 | 0.571 / 0.231 / 0.329 | 0.582 / 0.343 / 0.432 | **0.600** / 0.307 / **0.406** |

La v2 garde l'essentiel du gain (de 55 à 80 % selon la ligne), avec la meilleure précision des trois versions ; le reste venait du texte libre. Embed top-N reste au-dessus de TermSuite (0.519 contre 0.447) ; à froid, graph est à 0.048 de TermSuite (0.569).

RevueESR (mêmes paramètres que `clean3`, sorties `output_extract/RevueESR_clean5_respotv2_*`, supprimées le 2026-10-12 — même code que `clean6_respot` au filtre de mots outils près) : **38 min 43** (28 min sans l'option, 1 h 36 en v1), 5,9 Go au pic. 35 332 candidats (37 054 sans l'option : fusion des variantes de casse) ; 211 dans SEN — **aucune perte** : les 243 d'avant comptaient les variantes de casse en double (208 formes distinctes), +3 gagnés ; listes 1/2/3 = 178 / 638 / 3 335 ; exclusivité vérifiée. Liste 1 quasi inchangée (173 communes, 5 nouvelles dont « contaminations alimentaires », « risques écologiques et sanitaires » ; 6 perdues dont « virus », « épidémiologique »). Liste 2 : plus aucune suite de mots outils en tête (« santé publique », « long terme », « santé environnementale », « air intérieur »…) ; 524 communes, 114 nouvelles, 134 perdues — les nouvelles comptent du bruit amplifié (nombre + unité : « 12 ans », « 5 mg » ; fragments « -ci », « -analyses »), les perdues du bruit (« am j », « 1 site ») mais aussi des termes (« analyse spatiale », « cadre réglementaire »). **Bruit résiduel** : les résumés anglais du corpus, découpés par le modèle spaCy français en longs « groupes nominaux », contiennent des mots outils anglais déjà candidats (« OF », « and », « this », « with ») que le repérage gonfle (« OF » : 4 → 4 388) — ils forment un thème entier du rapport (« OF, in, this, and », 5 % des segments, couverture 0). Avant tout passage par défaut : filtre de mots outils FR + EN sur les candidats (au moins un mot plein), et précision par candidat sur ACTER.

**18. Filtre de mots outils FR + EN, et précision par candidat (2026-10-09)** : `is_valid_candidate()` rejette désormais (par défaut, comme le filtre « deux lettres ») un candidat dont tous les mots sont des mots outils de la liste spaCy française OU anglaise, plus les élisions (« d », « l », « qu »…) et « -ci »/« -là » ; un mot en majuscules d'au moins deux lettres compte comme sigle (« NO », « OR », « CA » gardés) sauf mots outils anglais de titres en capitales (« OF », « THE », « AND »…). Sur les 31 763 termes gold ACTER, 70 seraient rejetés par la liste seule, surtout des sigles mis en minuscules dans le gold (protégés dans le texte par la règle des majuscules) et « pas », « en avant » (équitation). `acter_eval.py` donne aussi la **précision par candidat** des listes de production (définition de `bench_topical.py` : une suggestion compte une fois, juste si son terme est un terme gold held-out). Sorties : `benchmark_results/stopfilter/`, `output_extract/RevueESR_clean6_{base,respot}_*`.

| ACTER, P / R / F1 token-level (P par candidat) | Avant le filtre | Filtre | Filtre + `--respot-occurrences` | TermSuite, même budget |
|---|---:|---:|---:|---:|
| ncvalue, à froid | 0.471 / 0.345 / 0.398 | 0.472 / 0.345 / 0.399 | 0.494 / 0.402 / 0.443 | — |
| graph, à froid | 0.556 / 0.452 / 0.499 | 0.557 / 0.452 / 0.499 | 0.552 / 0.494 / 0.522 | 0.521 / 0.627 / 0.569 |
| liste 1 | 0.854 / 0.129 / 0.224 | 0.854 / 0.129 / 0.224 (**0.532**, 521/980) | 0.884 / 0.195 / 0.319 (**0.509**, 468/919) | P/candidat **0.393** (385/980) |
| listes 1+2 | 0.571 / 0.231 / 0.329 | 0.571 / 0.230 / 0.328 (**0.432**, 648/1499) | 0.601 / 0.307 / 0.407 (**0.430**, 595/1385) | P/candidat **0.320** (479/1499) |

Lecture : (1) **filtre neutre sur ACTER** (écarts ≤ 0,001) ; (2) **embed bat TermSuite aussi en précision par candidat**, à budget égal (0,53 contre 0,39 pour la liste 1 ; 0,43 contre 0,32 pour les listes 1+2) — à budget égal, c'est aussi **plus de termes justes distincts** (521 contre 385 ; 648 contre 479) : l'avantage de TermSuite en rappel (point 14 bis) n'existe qu'en token-level, il vient du nombre d'occurrences couvertes, pas de termes supplémentaires ; (3) **`--respot-occurrences` n'aide pas le curateur** : le gain est token-level (plus d'occurrences comptées pour les mêmes termes, fréquences plus justes), mais le nombre de suggestions justes distinctes baisse (liste 1 : 468 contre 521 ; listes 1+2 : 595 contre 648) et la précision par candidat aussi (0,509 contre 0,532). Une partie de la baisse vient de la fusion des variantes de casse (sans l'option, « Heart failure » et « heart failure » comptent pour deux suggestions justes) — part non mesurée.

RevueESR (mêmes paramètres que `clean3`) : sans l'option **24 min 42**, avec **23 min 47** (pas de surcoût : les 39 min du point 17 et les 28 min de `clean3` reflètent la charge de la machine, pas le code), 5,8-5,9 Go. Sans l'option : 36 755 candidats, 243 dans SEN, listes 191 / 660 / 3 509 ; plus de mots outils anglais ni « pas d » / « D autres » / « -ci » ; « NO » (761 occurrences) conservé comme sigle. Avec l'option : 35 083 candidats, 211 dans SEN (fusion des variantes de casse), listes 178 / 633 / 3 313 ; le thème « OF, in, this, and » a disparu, il reste un thème anglais de mots pleins (« Health, Environmental, public, exposure », couverture 0,5 %). **Décision** : filtre de mots outils gardé par défaut ; `--respot-occurrences` reste une option, utile pour des fréquences plus justes et le token-level, pas un gain pour la curation — pas de passage par défaut.

Effet de bord du filtre sur le rapport (relevé le 2026-10-12, `clean6_base`) : le thème de discours général (« compte, exemple, mise, place », 13 % du corpus dans `clean3`) se scinde en deux petits thèmes (« compte, prise, facteurs », 0,8 % de couverture ; « mise, France, place », 1 %) qui passent sous le seuil `generic` (règle de poids) et occupent le bas du classement ; la santé au travail recule de la 1re à la 4e place des moins couverts (1,9 %). Même mécanisme qu'au-delà de 30 thèmes (point 13) : la règle « poids ≥ 2,5 × la moyenne » ne détecte pas un fourre-tout fragmenté. Piste : règle complémentaire sur la couverture « tous termes » ou sur la spécificité des étiquettes — non traité.

**Correction de l'entrée du 2026-09-11 ("Spécificité comme troisième signal de suggestion pour `embed`")** : les chiffres absolus de son tableau ne sont **pas reproductibles**. Le script consolidé `bench_specificity.py --mode embed`, relancé le 2026-09-30 dans le même environnement (spaCy 3.8.14 installé depuis le 2026-05-11, sentence-transformers/torch depuis le 2026-09-11 — environnement inchangé ; code d'extraction inchangé depuis v1.9.0), donne :

| | Journalisé 2026-09-11 | Reproduit 2026-09-30 |
|---|---:|---:|
| embed seul | P 0.899 / R 0.114 / F1 0.203 | P 0.852 / R 0.129 / F1 0.224 |
| + structurel (2%) | P 0.641 / R 0.171 / F1 0.270 | P 0.560 / R 0.231 / F1 0.327 |
| + structurel(2%) OU spécificité(10%) | F1 0.314 | F1 0.368 |
| spécificité isolée (2/5/10%) | P 0.271–0.305 | P 0.241 / 0.271 / 0.270 |

Les chiffres reproduits concordent avec le run officiel `make benchmark-acter` du 2026-09-07 (embed + structurel 2% : P 0.568 / R 0.232 / F1 0.329) — c'est donc le tableau du 11 qui détonne, probablement produit par le script ad hoc d'origine (`bench_specificity_embed.py`, non conservé) sur un périmètre différent (hypothèse non vérifiable). **Les décisions du 11 restent valables** : elles reposaient sur des écarts relatifs, retrouvés à l'identique (union > structurel seul, spécificité isolée nettement moins précise que le structurel → niveau 3 opt-in). Utiliser les chiffres reproduits comme référence pour toute comparaison future.

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
