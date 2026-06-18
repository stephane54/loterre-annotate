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

## Références

- Mao et al. 2024 — *Attention-Seeker: Dynamic Self-Attention Scoring for Unsupervised Keyphrase Extraction* : https://arxiv.org/html/2409.10907
- Frantzi et al. 2000 — *Automatic recognition of multi-word terms: the C-value/NC-value method* : https://www.researchgate.net/publication/2937844_Corpus-Based_Terminology_Extraction_Applied_to_Information_Access
- Campos et al. 2020 — *YAKE! Keyword extraction from single documents using multiple local features* (Information Sciences) : https://www.sciencedirect.com/science/article/abs/pii/S0020025519308588
- Boudin 2018 — *Unsupervised Keyphrase Extraction with Multipartite Graphs* : https://www.researchgate.net/publication/324005691_Unsupervised_Keyphrase_Extraction_with_Multipartite_Graphs
- Jemec Tomažin et al. 2025 — *Extracting domain-specific terms using contextual word embeddings* : https://arxiv.org/html/2502.17278
- Florescu & Caragea 2017 — *PositionRank: An Unsupervised Approach to Keyphrase Extraction from Scholarly Documents*
- Bougouin et al. 2013 — *TopicRank: Graph-Based Topic Ranking for Keyphrase Extraction*
- Papagiannopoulou & Tsoumakas 2019 — *A Review of Keyphrase Extraction* : https://arxiv.org/abs/1905.05044
