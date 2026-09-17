# Les 3 méthodes d'extraction — explication et exemple

Ce document explique les trois méthodes de scoring de candidats disponibles via `--extractor ncvalue|graph|embed` (`loterre_extract_cli.py` / `loterre_cli.py`), avec un exemple travaillé pour chacune. Les chiffres ci-dessous ne sont pas inventés : ils viennent d'une exécution réelle du code (`src/loterre_cvalue.py`, `src/loterre_positionrank.py`, `src/loterre_embed.py`) sur des exemples jouets.

Pour le mécanisme détaillé pas-à-pas et les seuils de production, voir `docs/underthehood.md`. Pour la consigne de travail du curateur, voir `docs/curation_guide.md`.

---

## 1. `ncvalue` — C-value (Frantzi et al. 1998)

**Fichier** : `src/loterre_cvalue.py`
**Quand** : corpus volumineux (> 50 000 tokens / ~6-10 articles) — fiable statistiquement grâce au volume.
**Principe** : un candidat multi-mots est pénalisé par sa fréquence **en tant que sous-séquence** de candidats plus longs qui le contiennent. Un terme composé qui apparaît souvent fait baisser artificiellement le score de son fragment plus court, puisque ces occurrences ne sont pas de vraies attestations du fragment seul.

Formule (candidat de longueur ≥ 2) :
```
c-value(a) = log2(|a|) × ( freq(a) − Σ freq(b) / P(a) )
```
où `b` parcourt les candidats plus longs contenant `a`, et `P(a)` est leur nombre. Pour un candidat mono-token, `log2(1) = 0` → repli sur `frequency / max_frequency` (score de repli, comparable seulement entre mono-tokens).

### Exemple (exécution réelle)

4 candidats, avec un emboîtement délibéré (`ocean acidification` ⊂ `ocean acidification impact`) :

| candidat | fréquence |
|---|---|
| `ocean acidification` | 45 |
| `ocean acidification impact` | 12 |
| `coral reef acidification impact` | 5 |
| `acidification` | 3 |

```
=== C-value ===
ocean acidification                 freq= 45 score=33.000 rule=cvalue
ocean acidification impact          freq= 12 score=19.020 rule=cvalue
coral reef acidification impact     freq=  5 score=10.000 rule=cvalue
acidification                       freq=  3 score=0.067  rule=freq_single_token
```

**Lecture du calcul** :
- `ocean acidification impact` (12 occurrences) n'est contenu dans aucun candidat plus long → score = `log2(3) × 12 = 19.02`.
- `coral reef acidification impact` (4 tokens, 5 occurrences), pas non plus emboîté → `log2(4) × 5 = 10.0`.
- `ocean acidification` (45 occurrences) est lui contenu dans `ocean acidification impact` (12 occurrences) → on retire cette part avant de compter : `log2(2) × (45 − 12/1) = 33.0`. Sans la pénalité d'emboîtement, un compte naïf aurait donné `log2(2) × 45 = 45.0` — C-value corrige pour ne pas surcompter les 12 occurrences qui appartiennent en fait à la forme plus longue.
- `acidification` seul (mono-token, 3 occurrences) tombe sur le repli fréquentiel : `3/45 = 0.067` — non comparable directement aux scores C-value multi-tokens.

---

## 2. `graph` — PositionRank (Florescu & Caragea 2017)

**Fichier** : `src/loterre_positionrank.py`
**Quand** : corpus courts (< 10 000 tokens / document unique) — bascule automatique quand le volume est insuffisant pour C-value.
**Principe** : PageRank biaisé sur un graphe de co-occurrence des mots de contenu (NOUN/PROPN/ADJ, fenêtre de 4 mots). Le vecteur de personnalisation (état de départ, avant propagation) n'est pas uniforme comme dans TextRank classique : il est dérivé de la **position** du mot dans le document (`1/(index+1)` cumulé — les mots qui apparaissent tôt comptent plus). Le score final résulte d'un compromis entre ce biais de position et la **centralité** du mot dans le graphe de co-occurrence.

### Exemple (exécution réelle)

Texte jouet : *"Climate(0) change(1) increases(2) ocean(3) acidification(4) . Ocean(6) acidification(7) threatens(8) marine(9) biodiversity(10) ."*

**Étape 1 — poids de position** (`1/(index+1)` cumulé, mots de contenu seulement) :

| lemme | position_weight |
|---|---|
| climate | 1.0000 (apparaît en 1er) |
| change | 0.5000 |
| ocean | 0.3929 (2 occurrences) |
| acidification | 0.3250 (2 occurrences) |
| marine | 0.1000 |
| biodiversity | 0.0909 |

**Étape 2 — graphe de co-occurrence** (fenêtre 4, arêtes principales) :
```
acidification -- ocean : 4.0   (le plus connecté)
acidification -- change : 2.0
acidification -- marine : 2.0
change -- ocean : 2.0
climate -- ocean : 2.0
```

**Étape 3 — PageRank biaisé** (α=0,85, jusqu'à convergence) :

| lemme | score final |
|---|---|
| **ocean** | **0,2676** |
| **acidification** | **0,2539** |
| climate | 0,1476 |
| change | 0,1431 |
| marine | 0,1045 |
| biodiversity | 0,0833 |

**Étape 4 — score des candidats** (somme des scores de leurs lemmes) :
- `ocean acidification` = 0,2676 + 0,2539 = **0,5215**
- `climate change` = 0,1476 + 0,1431 = **0,2907**
- `marine biodiversity` = 0,1045 + 0,0833 = **0,1878**

**Lecture** : `climate` a le poids de position brut le plus élevé (premier mot du texte), mais c'est `ocean acidification` qui termine en tête — parce qu'il est le nœud le plus central du graphe de co-occurrence (relié fortement à `change`, `marine`, `biodiversity`, `climate`). PositionRank n'est donc pas "premier mot gagne" : c'est un compromis entre position précoce et centralité structurelle, ce qui le rend plus robuste que la fréquence brute sur un document trop court pour que C-value soit fiable.

---

## 3. `embed` — similarité au plus proche voisin (Phase 5)

**Fichier** : `src/loterre_embed.py`
**Modèle** : `paraphrase-multilingual-MiniLM-L12-v2` (118 Mo, CPU, FR+EN, `sentence-transformers`), chargé en local (`HF_HUB_OFFLINE=1`, pas d'appel réseau).
**Quand** : pipeline prioritaire pour la mise à jour d'une ressource Loterre existante (voir CLAUDE.md, §Objectif produit principal) — nécessite un vocabulaire cible.
**Principe** : chaque candidat est comparé par similarité cosinus à **chaque** terme du vocabulaire cible, et ne retient que le score du terme le **plus proche** (max, pas une moyenne/centroïde). Un centroïde unique brouillerait un vocabulaire hétérogène (ex. X64 : mélange de noms de langues à un seul mot et de notions linguistiques abstraites multi-mots).

### Exemple (exécution réelle, vrai modèle)

Vocabulaire cible jouet (4 termes) :
```
pollution atmosphérique
changement climatique
biodiversité marine
gestion des déchets
```

4 candidats extraits d'un corpus, comparés à ce vocabulaire :

```
=== embed (plus proche voisin) ===
pollution de l air             score=0.9564
recyclage des plastiques       score=0.6421
acidification des océans       score=0.4629
conférence internationale      score=0.3136
```

**Lecture** :
- `pollution de l'air` est presque identique sémantiquement à `pollution atmosphérique` du vocabulaire → 0,9564, passerait le seuil de production (0,95) pour une suggestion d'enrichissement niveau 1.
- `recyclage des plastiques` est modérément proche de `gestion des déchets` (0,64) — thématiquement lié mais pas une reformulation directe, resterait sous le seuil.
- `acidification des océans` n'est pas si proche de `biodiversité marine` (0,46) malgré un lien thématique intuitif — l'embedding capte une proximité lexicale/sémantique plus fine que la simple co-appartenance à un domaine.
- `conférence internationale` est hors sujet par rapport à tout terme du vocabulaire (0,31) — correctement écarté comme bruit.

C'est ce mécanisme, avec un seuil de 0,95, qui alimente `enrichment_suggestion_embed` (niveau 1 des trois niveaux de suggestion — voir CLAUDE.md et `docs/curation_guide.md` pour les niveaux 2/structurel et 3/spécificité, qui utilisent C-value/PositionRank et le Weirdness Ratio comme signaux complémentaires indépendants du vocabulaire).
