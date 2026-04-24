# 🧠 Loterre v9 — Guide avancé d’optimisation des terminologies

## 🎯 Objectif
Ce guide explique comment améliorer concrètement les performances du moteur Loterre en jouant sur :
- profile
- quality
- dictionnaire
- analyse des erreurs

---

## ⚖️ Compromis fondamental
PRÉCISION ↔ RAPPEL

- P66 → manque (FN)
- 9SD → bruit (FP)

---

## 🔍 Diagnostic avec evaluate_json_v3

python evaluate_json_v3.py --gold gold.jsonl --pred pred.json

### Lecture
- FP élevés → bruit
- FN élevés → manque

Utiliser top_errors comme roadmap.

---

## 🟦 P66 (multi-termes)

Objectif : augmenter le rappel

profile: term_recall

quality:
  enabled: true
  penalize_single_token: true
  multi_token_bonus: 0.05

Actions :
- ajouter variants
- ajouter patterns

---

## 🟥 9SD (mono-termes)

Objectif : réduire le bruit

profile: entity_strict

quality:
  enabled: true
  strict_stopwords: true
  require_pos_match: true
  single_token_penalty: 0.3
  context_guard: true

Actions :
- ajouter POS
- filtrer contexte

---

## 🟨 Terminologie mixte

profile: term_balanced

quality:
  enabled: true
  contextual_scoring: true

---

## 🧠 Règles clés

1. Mono-termes = dangereux → filtrer
2. Multi-termes = robustes → favoriser
3. Contexte = essentiel

---

## 🔬 Méthode

1. annoter
2. évaluer
3. analyser FP/FN
4. ajuster
5. reboucler

---

## ⚠️ Pièges

- mauvais gold
- dictionnaire incohérent
- sur-filtrage

---

## 🚀 Résumé

P66 → ouvrir (recall)
9SD → filtrer (precision)
mix → équilibrer
