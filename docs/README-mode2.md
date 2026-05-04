# Patch Loterre CLI — mode hybrid complet

## Fichiers

```text
src/loterre_cli.py
src/loterre_fast_path.py
docs/hybrid_mode.md
README.md
```

## Installation

Copier dans ton repo v9 :

```text
src/loterre_cli.py
src/loterre_fast_path.py
```

Le moteur v9 complet doit rester ici :

```text
src/loterre_engine_v9_cli.py
```

## Modes disponibles

```bash
--execution-strategy full
--execution-strategy fast
--execution-strategy hybrid
```

## Test fast

```bash
python src/loterre_cli.py \
  --execution-strategy fast \
  --dict-id P66_en \
  --text ../examples/texts/P66_en.jsonl \
  --out outputs/P66_fast.json
```

## Test hybrid

```bash
python src/loterre_cli.py \
  --execution-strategy hybrid \
  --dict-id P66_en \
  --text ../examples/texts/P66_en.jsonl \
  --out outputs/P66_hybrid.json
```

## Hybrid strict pour ressources ambiguës

```bash
python src/loterre_cli.py \
  --execution-strategy hybrid \
  --dict-id 9SD_en \
  --text ../examples/texts/9SD_en.jsonl \
  --hybrid-refine-single-tokens \
  --hybrid-refine-low-score 0.95 \
  --out outputs/9SD_hybrid.json
```

## Principe hybrid

```text
1. fast path sur tous les documents
2. détection des documents ambigus
3. passage de ces documents au moteur v9 complet
4. fusion fast + v9
```

## Critères de raffinement

Un document est raffiné si :

- un match est ambigu
- ou un score est inférieur à `--hybrid-refine-low-score` (0.90 par défaut)
- ou le nombre de matches est supérieur à `--hybrid-max-fast-matches`
- ou `--hybrid-refine-single-tokens` est activé et un mono-token est détecté
