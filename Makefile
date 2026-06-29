PYTHON ?= python3

.PHONY: install models models-embed \
        test test-smoke test-non-regression test-profiling test-quality \
        test-extraction test-extract test-cvalue test-positionrank test-extract-annotate test-embed test-variants \
        benchmark benchmark-local benchmark-api benchmark-resolvers html \
        extract extract-annotate corpus-acter benchmark-acter \
        run ezs-test ws-test ws-test-accel deploy build \
        clean tree

VOCAB    ?= P66
LOTLANG  ?= en

install:
	@echo "[install] Input    : requirements.txt"
	@echo "[install] Resource : acces reseau (PyPI)"
	@echo "[install] Output   : paquets installes dans l'environnement Python actif"
	@$(PYTHON) -m pip install -r requirements.txt

# Modèles spaCy de reconnaissance runtime (resources/spacy_models.yaml) :
# en_core_web_sm / fr_core_news_sm. C'est ce qui est chargé par défaut par
# load_model() dans loterre_engine_v9_cli.py — pas les modèles _lg (réservés
# à un usage manuel, voir le commentaire dans spacy_models.yaml) ni scispaCy
# (en_core_sci_sm a été testé comme défaut EN et abandonné : -8 points de F1
# sur P66, voir CLAUDE.md / journal des versions).
models:
	@echo "[models] Input    : aucun"
	@echo "[models] Resource : acces reseau (telechargement spaCy)"
	@echo "[models] Output   : modeles en_core_web_sm + fr_core_news_sm installes dans l'environnement Python actif"
	@echo "[models] Voir aussi : make models-embed (modele sentence-transformers, Phase 5 extraction)"
	@$(PYTHON) -m spacy download en_core_web_sm
	@$(PYTHON) -m spacy download fr_core_news_sm

# Modèle d'embeddings pour --extractor embed (Phase 5, scoring de candidats
# par similarite au vocabulaire cible) : paraphrase-multilingual-MiniLM-L12-v2
# (~118 Mo, CPU, FR+EN) — telecharge et mis en cache au premier appel sinon ;
# cette cible permet de le pre-telecharger explicitement.
models-embed:
	@echo "[models-embed] Input    : aucun"
	@echo "[models-embed] Resource : acces reseau (telechargement Hugging Face, ~118 Mo)"
	@echo "[models-embed] Output   : modele paraphrase-multilingual-MiniLM-L12-v2 mis en cache localement"
	@$(PYTHON) -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# ── Tests : annotation (v1.0) ──────────────────────────────────────────────────

test: test-smoke test-profiling test-quality test-extraction
	@echo "[test] Toutes les sous-cibles ci-dessus ont leur propre detail input/resource/output."

# Smoke test CLI complet (sous-commande `annotate`), auto-profile, EN + FR.
test-smoke:
	@echo "[test-smoke] Input    : data/jsonl/{P66,9SD,B9M,QX8}_{en,fr}.jsonl, configs/example_p66_en_quick.yaml"
	@echo "[test-smoke] Resource : dictionnaires associes (dictionary/), modeles spaCy runtime"
	@echo "[test-smoke] Output   : outputs_tests_v9_cli/ (json + md + yaml par test)"
	@bash tests/smoke/test_v9_cli.sh

# Pipeline complet prédiction -> gold -> rendu HTML -> conversion batch (P66).
test-non-regression:
	@echo "[test-non-regression] Input    : data/jsonl/P66_en.jsonl"
	@echo "[test-non-regression] Resource : dictionnaire P66_en, renderer HTML, convertisseurs prediction->gold"
	@echo "[test-non-regression] Output   : /tmp/loterre_p66_nonreg/ (pred.json, expected.jsonl, html, bulk_out)"
	@bash tests/smoke/test_p66_non_regression.sh

test-profiling:
	@echo "[test-profiling] Input    : data/jsonl/{P66,9SD,8HQ,B9M,27X,BVM,QX8,3JP,JVR}_en.jsonl + equivalents _fr (sans 3JP/JVR)"
	@echo "[test-profiling] Resource : dictionnaires correspondants, modeles spaCy runtime"
	@echo "[test-profiling] Output   : outputs_autoprofile_quality/ (yaml auto-profile + json par vocabulaire)"
	@bash tests/profiling/test_auto_profile_quality.sh

test-quality:
	@echo "[test-quality] Input    : textes inline dans le script (garde-fous and/it, mots vides)"
	@echo "[test-quality] Resource : dictionnaire 9SD_en"
	@echo "[test-quality] Output   : outputs_v9_contextual/ (json)"
	@bash tests/quality/test_v9_contextual.sh

# ── Tests : extraction terminologique (v2.0) ───────────────────────────────────
# Sous-commandes `extract` / `extract_annotate` de src/loterre_cli.py.

test-extraction: test-extract test-cvalue test-positionrank test-embed test-variants test-extract-annotate
	@echo "[test-extraction] Toutes les sous-cibles ci-dessus ont leur propre detail input/resource/output."

# Extraction noun chunks de base (Phase 1) via loterre_extract_cli.py.
test-extract:
	@echo "[test-extract] Input    : data/jsonl/P66_en.jsonl, data/jsonl/P66_fr.jsonl"
	@echo "[test-extract] Resource : modeles spaCy runtime EN+FR (parser actif, sans vocabulaire)"
	@echo "[test-extract] Output   : fichiers temporaires /tmp (auto-nettoyes par le script)"
	@bash tests/smoke/test_extract_cli.sh

# Scoring C-value (Phase 2) : termes emboîtés, repli mono-token, seuil.
test-cvalue:
	@echo "[test-cvalue] Input    : data/jsonl/P66_en.jsonl"
	@echo "[test-cvalue] Resource : modele spaCy EN runtime (parser actif)"
	@echo "[test-cvalue] Output   : fichiers temporaires /tmp (auto-nettoyes par le script)"
	@bash tests/smoke/test_cvalue.sh

# Scoring PositionRank + bascule automatique selon le volume de tokens.
test-positionrank:
	@echo "[test-positionrank] Input    : data/jsonl/P66_en.jsonl"
	@echo "[test-positionrank] Resource : modele spaCy EN runtime (parser actif)"
	@echo "[test-positionrank] Output   : fichiers temporaires /tmp (auto-nettoyes par le script)"
	@bash tests/smoke/test_positionrank.sh

# [Extraction] Scoring par embeddings (Phase 5) : similarite au terme le plus
# proche (plus proche voisin) du vocabulaire cible, filtrage par seuil,
# suggestions d'enrichissement.
test-embed:
	@echo "[test-embed] Input    : data/jsonl/P66_en.jsonl"
	@echo "[test-embed] Resource : dictionnaire P66_en, modele sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2)"
	@echo "[test-embed] Output   : fichiers temporaires /tmp (auto-nettoyes par le script)"
	@bash tests/smoke/test_embed.sh

# Détection de variantes (Phase 4) : graphiques/morphologiques/syntaxiques,
# mécanismes inspirés de TermSuite — --detect-variants (option explicite).
test-variants:
	@echo "[test-variants] Input    : data/jsonl/P66_en.jsonl + candidats construits a la main (test unitaire)"
	@echo "[test-variants] Resource : resources/termsuite_morphology/{fr,en}/*.txt, modele spaCy EN runtime"
	@echo "[test-variants] Output   : fichiers temporaires /tmp (auto-nettoyes par le script)"
	@bash tests/smoke/test_variants.sh

# [Les deux] Les 3 sous-commandes via loterre_cli.py (annotate/extract/
# extract_annotate), y compris le croisement extract_annotate sans faux positif.
test-extract-annotate:
	@echo "[test-extract-annotate] Input    : data/jsonl/P66_en.jsonl"
	@echo "[test-extract-annotate] Resource : dictionnaire P66_en, modele spaCy EN (annotation + extraction)"
	@echo "[test-extract-annotate] Output   : fichiers temporaires /tmp (auto-nettoyes par le script)"
	@bash tests/smoke/test_extract_annotate_cli.sh

# ── Benchmark & rendu HTML (annotation, v1.0) ──────────────────────────────────

# Benchmark complet : loterre_cli (local) + API terms-tools (production) + Resolvers (EN + FR).
# BENCHMARK_ARGS permet de passer des options supplémentaires :
#   make benchmark BENCHMARK_ARGS="--vocabs P66_en,9SD_en"
#   make benchmark BENCHMARK_ARGS="--out-dir results/$(shell date +%Y%m%d)"
benchmark:
	@echo "[benchmark] Input    : data/jsonl/ (text-root, tous vocabulaires sauf JVR — volumineux, exclu par defaut)"
	@echo "[benchmark] Resource : dictionnaires du registre, API terms-tools + API Resolvers (reseau)"
	@echo "[benchmark] Output   : benchmark_results/<horodatage>_local_api_resolvers/ (json + summary)"
	@bash tests/smoke/compare_engines.sh $(BENCHMARK_ARGS)

# Moteur local uniquement (pas d'appels réseau)
benchmark-local:
	@echo "[benchmark-local] Input    : data/jsonl/ (text-root, sauf JVR — exclu par defaut)"
	@echo "[benchmark-local] Resource : dictionnaires du registre — aucun acces reseau"
	@echo "[benchmark-local] Output   : benchmark_results/<horodatage>_local/ (json + summary)"
	@bash tests/smoke/compare_engines.sh --skip-api --skip-resolvers $(BENCHMARK_ARGS)

# loterre_cli (local) vs API terms-tools (production, terms-tools.services.istex.fr)
benchmark-api:
	@echo "[benchmark-api] Input    : data/jsonl/ (text-root, sauf JVR — exclu par defaut)"
	@echo "[benchmark-api] Resource : dictionnaires du registre, API terms-tools (reseau)"
	@echo "[benchmark-api] Output   : benchmark_results/<horodatage>_local_api/ (json + summary)"
	@bash tests/smoke/compare_engines.sh --skip-resolvers $(BENCHMARK_ARGS)

# loterre_cli (local) vs Loterre Resolvers uniquement
benchmark-resolvers:
	@echo "[benchmark-resolvers] Input    : data/jsonl/ (text-root, sauf JVR — exclu par defaut)"
	@echo "[benchmark-resolvers] Resource : dictionnaires du registre, API Loterre Resolvers (reseau)"
	@echo "[benchmark-resolvers] Output   : benchmark_results/<horodatage>_local_resolvers/ (json + summary)"
	@bash tests/smoke/compare_engines.sh --skip-api $(BENCHMARK_ARGS)

# ── Benchmark ACTER (Phase 6, extraction "a froid" sans vocabulaire) ───────────
# Corpus externe (https://github.com/AylaRT/ACTER, CC BY-NC-SA 4.0) : 4 domaines
# x langues, gold standard de termes pour comparer C-value/PositionRank a des
# baselines publiees (D-Terminer, voir CLAUDE.md). Pas committe dans le repo
# (volumineux, licence a part) — clone a la demande dans corpus_acter/ (gitignore).

corpus-acter:
	@echo "[corpus-acter] Input    : aucun"
	@echo "[corpus-acter] Resource : acces reseau (clone GitHub, ~73 Mo)"
	@echo "[corpus-acter] Output   : corpus_acter/ (4 domaines x 3 langues, CC BY-NC-SA 4.0)"
	@if [ -d corpus_acter ]; then echo "deja present : corpus_acter/"; else \
		git clone --depth 1 https://github.com/AylaRT/ACTER.git corpus_acter; fi

# [Extraction] Compare C-value/PositionRank au gold ACTER (token-level P/R/F1)
# — extractor embed exclu (necessite un vocabulaire Loterre cible, qu'ACTER n'a pas).
benchmark-acter:
	@echo "[benchmark-acter] Input    : corpus_acter/{en,fr}/{corp,equi,htfl,wind}/annotated/ (make corpus-acter d'abord)"
	@echo "[benchmark-acter] Resource : modeles spaCy runtime EN+FR — aucun acces reseau"
	@echo "[benchmark-acter] Output   : benchmark_results/acter/ (json + markdown par domaine/langue/extracteur)"
	@$(PYTHON) scripts/evaluation/acter_eval.py --corpus-root corpus_acter --out-dir benchmark_results/acter --min-freq 1

# Génère les fichiers HTML annotés pour tous les corpus dans data/jsonl/.
html:
	@echo "[html] Input    : data/jsonl/*.json(l) (tous les corpus du repertoire)"
	@echo "[html] Resource : dictionnaires correspondant a chaque dict_id, modeles spaCy runtime"
	@echo "[html] Output   : html_outputs/json/, html_outputs/html/, html_outputs/*_summary.tsv"
	@bash tests/smoke/render_html_annotation.sh

# ── Extraction terminologique — invocation directe ─────────────────────────────
# Raccourcis ad-hoc sur un seul vocabulaire/langue (make extract VOCAB=P66 LOTLANG=en).
# Pour les paramètres d'extraction (--min-freq, --extractor, ...), invoquer
# src/loterre_cli.py directement — voir loterre_cli.py extract --help.

# [Extraction] Candidats termes, sans vocabulaire.
extract:
	@echo "[extract] Input    : data/jsonl/$(VOCAB)_$(LOTLANG).jsonl"
	@echo "[extract] Resource : modele spaCy $(LOTLANG) runtime (parser actif, pas de dictionnaire)"
	@echo "[extract] Output   : stdout (JSON candidats, mode=extract)"
	@$(PYTHON) src/loterre_cli.py extract --lang $(LOTLANG) --text data/jsonl/$(VOCAB)_$(LOTLANG).jsonl

# [Les deux] Extraction puis croisement avec le vocabulaire Loterre VOCAB_LOTLANG.
extract-annotate:
	@echo "[extract-annotate] Input    : data/jsonl/$(VOCAB)_$(LOTLANG).jsonl"
	@echo "[extract-annotate] Resource : dictionnaire $(VOCAB)_$(LOTLANG), modele spaCy $(LOTLANG) runtime"
	@echo "[extract-annotate] Output   : stdout (JSON candidats croises in_vocabulary/uri/pref, mode=extract_annotate)"
	@$(PYTHON) src/loterre_cli.py extract_annotate --dict-id $(VOCAB)_$(LOTLANG) --profile term_recall --text data/jsonl/$(VOCAB)_$(LOTLANG).jsonl

# ── Production ────────────────────────────────────────────────────────────────

run:
	@echo "[run] Input    : fichier corpus en argument ou stdin (voir production/run_local_ezs.sh --help)"
	@echo "[run] Resource : pipeline EZS (npm install dans github-web-services), dictionnaire $(VOCAB)_$(LOTLANG)"
	@echo "[run] Output   : stdout (JSON annote)"
	@bash production/run_local_ezs.sh $(VOCAB) $(LOTLANG)

ezs-test:
	@echo "[ezs-test] Input    : data/json/*.json (tableaux JSON complets id+value)"
	@echo "[ezs-test] Resource : pipeline EZS local (sans Docker, sans service HTTP)"
	@echo "[ezs-test] Output   : production/results/ (logs horodates)"
	@bash production/test_local_ezs.sh

ws-test:
	@echo "[ws-test] Input    : corpus de test embarques (test_ws_annotate.sh)"
	@echo "[ws-test] Resource : service loterre-annotate local (HTTP)"
	@echo "[ws-test] Output   : production/results/<horodatage>_local.log"
	@bash production/test_ws.sh local

ws-test-accel:
	@echo "[ws-test-accel] Input    : corpus de test embarques (test_ws_annotate.sh)"
	@echo "[ws-test-accel] Resource : service de production distant (reseau)"
	@echo "[ws-test-accel] Output   : production/results/<horodatage>_accel.log"
	@bash production/test_ws.sh accel

build:
	@echo "[build] Input    : VERSION, src/, requirements.txt"
	@echo "[build] Resource : cle SSH configuree pour github.com (push du wheel)"
	@echo "[build] Output   : wheel/tarball buildes + push sur le remote Git"
	@echo "[build] Exemple  : make build BUILD_ARGS=\"--patch --tag\"  (ou --minor/--major/--version X.Y.Z)"
	@bash production/build_push_package.sh $(BUILD_ARGS)

deploy:
	@echo "[deploy] Input    : image source recuperee depuis GitHub (pip install git+...)"
	@echo "[deploy] Resource : Docker accessible localement, production/.env (WEBDAV_*)"
	@echo "[deploy] Output   : conteneur Docker local lance + tests executes dans le conteneur"
	@echo "[deploy] Exemple  : make deploy DOCKER_ARGS=--force-tag (si VERSION inchangee mais tag deplace)"
	@bash production/ws_deploy_docker_local.sh $(DOCKER_ARGS)

# ── Maintenance ───────────────────────────────────────────────────────────────

clean:
	@echo "[clean] Input    : aucun"
	@echo "[clean] Resource : aucune"
	@echo "[clean] Output   : suppression des repertoires generes (outputs*, benchmark_results, html_outputs, eval_outputs, profile_outputs, __pycache__)"
	@rm -rf outputs outputs_tests_v9_cli outputs_predictions outputs_autoprofile_quality \
	       outputs_v9_contextual benchmark_results html_outputs \
	       eval_outputs profile_outputs .pytest_cache
	@find . -name "__pycache__" -type d -prune -exec rm -rf {} +

tree:
	@echo "[tree] Input    : aucun"
	@echo "[tree] Resource : aucune"
	@echo "[tree] Output   : stdout (liste des fichiers du repo, profondeur 4)"
	@find . -maxdepth 4 -type f | sort
