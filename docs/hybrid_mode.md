# Mode hybrid

Le mode hybrid utilise le fast path comme pré-filtre et le moteur v9 complet comme raffineur.

## Pipeline

```text
document
↓
fast path
↓
si non ambigu → résultat fast
↓
si ambigu → moteur v9 complet
↓
fusion
```

## Sortie

Chaque document contient :

```text
hybrid_source = fast
```

ou :

```text
hybrid_source = v9_refined
```

Le bloc global contient :

```json
"hybrid": {
  "refined_docs": 2,
  "fast_docs": 10
}
```
