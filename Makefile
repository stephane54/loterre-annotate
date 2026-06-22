PYTHON ?= python3

.PHONY: install models \
        test test-smoke test-non-regression test-profiling test-quality \
        test-extraction test-extract test-cvalue test-positionrank test-extract-annotate \
        benchmark benchmark-local benchmark-api benchmark-resolvers html \
        extract extract-annotate \
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
	@$(PYTHON) -m spacy download en_core_web_sm
	@$(PYTHON) -m spacy download fr_core_news_sm

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

test-extraction: test-extract test-cvalue test-positionrank test-extract-annotate
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

# Les 3 sous-commandes via loterre_cli.py (annotate/extract/extract_annotate),
# y compris le croisement extract_annotate sans faux positif.
test-extract-annotate:
	@echo "[test-extract-annotate] Input    : data/jsonl/P66_en.jsonl"
	@echo "[test-extract-annotate] Resource : dictionnaire P66_en, modele spaCy EN (annotation + extraction)"
	@echo "[test-extract-annotate] Output   : fichiers temporaires /tmp (auto-nettoyes par le script)"
	@bash tests/smoke/test_extract_annotate_cli.sh

# ── Benchmark & rendu HTML ────────────────────────────────────────────────────

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

# Extraction de candidats termes, sans vocabulaire.
extract:
	@echo "[extract] Input    : data/jsonl/$(VOCAB)_$(LOTLANG).jsonl"
	@echo "[extract] Resource : modele spaCy $(LOTLANG) runtime (parser actif, pas de dictionnaire)"
	@echo "[extract] Output   : stdout (JSON candidats, mode=extract)"
	@$(PYTHON) src/loterre_cli.py extract --lang $(LOTLANG) --text data/jsonl/$(VOCAB)_$(LOTLANG).jsonl

# Extraction puis croisement avec le vocabulaire Loterre VOCAB_LOTLANG.
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
	@bash production/build_push_package.sh

deploy:
	@echo "[deploy] Input    : image source recuperee depuis GitHub (pip install git+...)"
	@echo "[deploy] Resource : Docker accessible localement, production/.env (WEBDAV_*)"
	@echo "[deploy] Output   : conteneur Docker local lance + tests executes dans le conteneur"
	@bash production/ws_deploy_docker_local.sh

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
