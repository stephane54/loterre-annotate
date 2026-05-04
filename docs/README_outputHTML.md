# Sortie HTML interactive Loterre — v2 batch

## Objectif

`src/loterre_html_renderer.py` permet :

1. convertir une sortie JSON existante en HTML ;
2. exécuter automatiquement le moteur pour une liste de vocabulaires EN/FR puis produire les HTML.

## Vocabulaires traités en batch

Anglais :

```text
P66, 9SD, 8HQ, B9M, 27X, BVM, QX8, 3JP, JVR
```

Français :

```text
P66, 9SD, 8HQ, B9M, 27X, BVM, QX8
```

## Usage 1 — convertir un JSON existant

```bash
python src/loterre_html_renderer.py render   --input predictions/P66_en.json   --out html_outputs/P66_en.html   --title "Annotation P66_en"
```

## Usage 2 — batch complet

```bash
python src/loterre_html_renderer.py batch   --cli ./src/loterre_cli.py   --text-root examples/texts   --outdir ./html_outputs
```

Ou :

```bash
./tests/smoke/render_html_annotation.sh   ./src/loterre_cli.py   examples/texts   ./html_outputs
```

## Sorties

```text
html_outputs/
  json/
    P66_en.json
  html/
    P66_en.html
  html_generation_summary.json
```

## Recherche automatique des textes

Pour `CODE_lang`, le script cherche :

```text
CODE_lang.jsonl
CODE.jsonl
*fichier contenant CODE et lang*
*fichier contenant CODE*
```

## Personnaliser les listes

```bash
python src/loterre_html_renderer.py batch   --cli ./src/loterre_cli.py   --text-root examples/texts   --outdir ./html_outputs   --en-codes P66,9SD,QX8   --fr-codes P66,QX8
```


---

# Mise à jour : `scripts/render_html_annotation.sh`

Ce script lance maintenant directement toutes les exécutions demandées.

## Vocabulaires anglais

```text
P66 9SD 8HQ B9M 27X BVM QX8 3JP JVR
```

Il utilise les `dict-id` :

```text
P66_en 9SD_en 8HQ_en B9M_en 27X_en BVM_en QX8_en 3JP_en JVR_en
```

## Vocabulaires français

```text
P66 9SD 8HQ B9M 27X BVM QX8
```

Il utilise les `dict-id` :

```text
P66_fr 9SD_fr 8HQ_fr B9M_fr 27X_fr BVM_fr QX8_fr
```

## Usage

```bash
./tests/smoke/render_html_annotation.sh   ./src/loterre_cli.py   examples/texts   ./html_outputs   ./src/loterre_html_renderer.py
```

## Sorties

```text
html_outputs/
  json/
    P66_en.json
    ...
  html/
    P66_en.html
    ...
  html_generation_summary.tsv
```

## Recherche des fichiers texte

Pour chaque couple `CODE_lang`, le script cherche :

```text
CODE_lang.jsonl
CODE_lang.json
CODE.jsonl
CODE.json
*fichier contenant CODE et lang*
*fichier contenant CODE*
```

## Modifier la base des liens Loterre

```bash
BASE_URL="https://www.loterre.fr/ark:/" bash scripts/render_html_annotation.sh ./src/loterre_cli.py examples/texts ./html_outputs ./src/loterre_html_renderer.py
```
