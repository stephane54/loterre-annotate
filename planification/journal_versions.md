# Journal des versions — loterre-annotate

---

## v1.0.0 — Moteur d'annotation terminologique (release majeure)

**Date :** 2026-06-13  
**Statut :** stable

### Fonctionnalités

**Annotation par dictionnaire (mode unique)**

- Détection des termes d'un vocabulaire Loterre dans un texte libre
- Stratégie de matching en 5 passes : patrons POS+lemme, surface exacte, séquence lemme, surface structurelle, lemme structurel
- Scoring de confiance par passe (1.0 → 0.70) avec seuils configurables
- Matching par Trie (recherche longest-match)
- Génération automatique de variantes (parenthèses, apostrophes, casse)

**Langues supportées**

- Français (`fr_core_news_sm`)
- Anglais (`en_core_web_sm`)

**Profils préconfigurés**

- `entity_strict` (seuil 0.80) — entités nommées, haute précision
- `term_balanced` (seuil 0.75) — terminologie mixte
- `term_recall` (seuil 0.70) — rappel maximum, termes compositionnels

**Filtres qualité**

- Élimination des stopwords
- Gardes syntaxiques (copule, motifs discursifs faibles)
- Pénalités contextuelles pour termes mono-token ambigus
- Fenêtre de contexte ±2 tokens

**Vocabulaires**

- 30+ vocabulaires Loterre indexés via `configs/registry.yaml`
- Résolution par identifiant court (ex. `P66`, `9SD`) ou URI complète
- Dictionnaires au format JSONL (label, pref, id, pattern, altLabels)

**CLI**

- `loterre-annotate` — point d'entrée principal avec résolution du registre
- `loterre-engine` — moteur bas niveau
- `loterre-benchmark` — comparaison locale vs API ISTEX de production
- `loterre-render` — visualisation HTML interactive avec surlignage des termes

**Modes de sortie**

- JSONL (défaut)
- HTML interactif avec comparaison gold standard

---

## v1.1.0 — Maintenance outillage release (patch)

**Date :** 2026-06-13  
**Statut :** stable

### Changements

- `make build` / `make deploy` : passage des arguments (`BUILD_ARGS`, `DOCKER_ARGS`) et exemples d'usage ajoutés au texte d'aide affiché — aucun changement fonctionnel côté annotation/extraction

---

## v2.0.0 — Extraction terminologique intégrée *(implémentée sur `master`, non encore versionnée officiellement)*

**Statut réel :** toutes les phases prévues (0 à 6, y compris la détection de variantes Phase 4) sont **terminées** dans le code (`src/loterre_extract_cli.py`, `loterre_cvalue.py`, `loterre_positionrank.py`, `loterre_embed.py`, `loterre_variants.py`) et documentées dans [planif_extraction_terminologique.md](planif_extraction_terminologique.md) — mais `VERSION` reste à `1.1.0` : aucune release `2.0.0` n'a encore été taguée/publiée (voir `production/release.sh`).

### Fonctionnalités livrées

- Extraction de candidats termes par noun chunks spaCy + scoring C-value (Frantzi et al. 1998)
- Bascule automatique C-value/PositionRank selon le volume de corpus (`--extractor auto`, seuil configurable)
- Trois sous-commandes CLI positionnelles : `annotate` / `extract` / `extract_annotate`
- Détection de variantes morphologiques, graphiques et syntaxiques, inspirée de TermSuite (CNRS/TTC) — `--detect-variants`
- Croisement extraction/vocabulaire Loterre natif (`in_vocabulary` / `enrichment_suggestion`)
- Scoring par embeddings au plus proche voisin d'un vocabulaire cible (`--extractor embed`, `paraphrase-multilingual-MiniLM-L12-v2`) — **pas** `--extractor bert`
- Benchmark intégré contre le gold ACTER (`make benchmark-acter`) : F1 PositionRank=0.496, C-value=0.391, au sommet de la fourchette D-Terminer (0.32–0.50, GPU) obtenue en CPU pur
