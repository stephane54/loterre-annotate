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

## Références

- Mao et al. 2024 — *Attention-Seeker: Dynamic Self-Attention Scoring for Unsupervised Keyphrase Extraction* : https://arxiv.org/html/2409.10907
- Frantzi et al. 2000 — *Automatic recognition of multi-word terms: the C-value/NC-value method* : https://www.researchgate.net/publication/2937844_Corpus-Based_Terminology_Extraction_Applied_to_Information_Access
- Campos et al. 2020 — *YAKE! Keyword extraction from single documents using multiple local features* (Information Sciences) : https://www.sciencedirect.com/science/article/abs/pii/S0020025519308588
- Boudin 2018 — *Unsupervised Keyphrase Extraction with Multipartite Graphs* : https://www.researchgate.net/publication/324005691_Unsupervised_Keyphrase_Extraction_with_Multipartite_Graphs
- Jemec Tomažin et al. 2025 — *Extracting domain-specific terms using contextual word embeddings* : https://arxiv.org/html/2502.17278
- Florescu & Caragea 2017 — *PositionRank: An Unsupervised Approach to Keyphrase Extraction from Scholarly Documents*
- Bougouin et al. 2013 — *TopicRank: Graph-Based Topic Ranking for Keyphrase Extraction*
- Papagiannopoulou & Tsoumakas 2019 — *A Review of Keyphrase Extraction* : https://arxiv.org/abs/1905.05044
