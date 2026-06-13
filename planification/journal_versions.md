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

## v2.0.0 — Extraction terminologique intégrée *(planifié)*

**Date cible :** 2026-Q3  
**Statut :** en planification — voir [analyse_extraction_terminologique.md](analyse_extraction_terminologique.md)

### Fonctionnalités prévues

- Extraction de candidats termes par algorithme C-value (Frantzi et al. 1998)
- Trois modes CLI : `--mode annotate` / `--mode extract` / `--mode extract+annotate`
- Détection de variantes morphologiques, graphiques et syntaxiques
- Croisement extraction/vocabulaire Loterre natif
- Option re-ranking par sentence-transformers (`--extractor bert`)
- Métriques d'extraction intégrées au benchmark existant
