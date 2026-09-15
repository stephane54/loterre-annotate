# Provenance

- Source EN : https://github.com/termsuite/termsuite-resources/blob/master/en/english-general-language.txt
- Source FR : https://github.com/termsuite/termsuite-resources/blob/master/fr/french-general-language.txt
- Licence : Apache License 2.0 (CNRS, 2015 — TermSuite/TTC), même base que `resources/termsuite_morphology/`.
- Récupérés le 2026-09-11 pour le calcul de spécificité (Weirdness Ratio) — voir
  `planification/planif_extraction_terminologique.md` §9.

## Format

Une entrée par ligne : `lemme::POS::fréquence`, plus une ligne d'en-tête
`__NB_CORPUS_WORDS__::option::<N>` donnant la taille totale (en mots) du
corpus de référence ayant servi à calculer ces fréquences (28 758 450 mots
pour l'anglais, 82 629 305 pour le français).

**Pas d'en-tête de provenance inline dans les fichiers `.txt` eux-mêmes**
(contrairement à `termsuite_morphology/`) : le corpus de référence contient
de vrais tokens commençant par `#` (ex. `#1.1m::N::39`, `#10,000::N::344`),
donc une ligne de commentaire `#` en tête serait ambiguë avec une donnée
réelle. La provenance est documentée ici à la place ; les fichiers `.txt`
sont copiés tels quels depuis la source, sans aucune modification, pour
rester diffables contre l'original en cas de mise à jour.
