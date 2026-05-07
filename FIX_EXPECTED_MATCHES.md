# Fix pour la visualisation des termes expected_matches

## Problème
La visualisation des termes `expected_matches` ne fonctionnait pas dans les fichiers HTML générés par `loterre_html_renderer.py` via le script `render_html_annotation.sh`.

## Causes identifiées
1. Le script `render_html_annotation.sh` ne cherchait pas les fichiers gold contenant les `expected_matches`
2. Le script n'avait pas d'argument `--gold` à passer au renderer

## Solution implémentée

### 1. Modification du script `tests/smoke/render_html_annotation.sh`
- Ajout d'une fonction `find_gold_file()` qui cherche les fichiers gold dans les emplacements courants:
  - `$GOLD_ROOT/gold_${dict_id}.jsonl` (si `GOLD_ROOT` est défini)
  - Répertoire contenant le fichier texte d'entrée
  - Emplacements courants: `examples/gold_1`, `gold_1`, etc.

- Modification de `run_one()` pour:
  - Utiliser `python3` au lieu de `python` (compatible WSL)
  - Chercher le fichier gold correspondant
  - Passer l'argument `--gold` au renderer si le fichier existe

- Ajout de variable d'environnement `GOLD_ROOT` pour spécifier le répertoire des fichiers gold

### 2. Vérification du renderer `src/loterre_html_renderer.py`
Le renderer fonctionne correctement avec les fichiers gold. Il:
- Fusionne les `expected_matches` avec les résultats de prédiction
- Classe les termes selon 3 catégories:
  - **"both"** (vert): trouvé dans expected_matches ET prédictions
  - **"expected_only"** (orange): attendu mais pas prédit
  - **"predicted_only"** (bleu): prédit mais pas attendu
- Affiche les statistiques correctement: nombre de termes prédits vs attendus

## Utilisation

### Sans fichiers gold
```bash
bash tests/smoke/render_html_annotation.sh \
  ./src/loterre_cli.py \
  examples/texts \
  ./html_outputs \
  ./src/loterre_html_renderer.py
```

### Avec fichiers gold (pour fusionner expected_matches)
```bash
GOLD_ROOT=examples/gold_1 bash tests/smoke/render_html_annotation.sh \
  ./src/loterre_cli.py \
  examples/texts \
  ./html_outputs \
  ./src/loterre_html_renderer.py
```

## Format des données

### Fichier texte d'entrée (JSONL)
```json
{"id": "0", "value": "Le texte du document...", "expected_matches": [...]}
```

### Fichier JSON généré par loterre_cli (résultats de prédictions)
```json
{"results": [{"id": "0", "text": "...", "matches": [...]}]}
```

### Fichier HTML généré
- Affiche le texte avec les termes surligné en couleur selon leur statut
- Légende: 3 couleurs pour les 3 catégories
- Table détaillée des termes avec tous les métadonnées

## Exemple de visualisation HTML

**Statistiques:**
```
prédits: 2 - attendus: 2 - attendus+prédits: 1 - attendus non prédits: 1 - prédits non attendus: 1
```

**Texte annoté:**
- Terme en **vert** (both): terme trouvé à la fois dans expected_matches et prédictions
- Terme en **orange** (expected_only): terme attendu mais non prédit
- Terme en **bleu** (predicted_only): terme prédit mais non attendu

## Tests effectués
✓ Test avec données de test (test_data.json + test_gold.jsonl)
✓ Fusion correcte des expected_matches
✓ Affichage correct des 3 catégories de termes
✓ Statistiques correctes dans le résumé
