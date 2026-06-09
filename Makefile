PYTHON ?= python3

.PHONY: install models \
        test test-smoke test-non-regression test-profiling test-quality test-api \
        benchmark benchmark-local benchmark-api benchmark-resolvers html \
        run ezs-test ws-test ws-test-accel deploy build \
        clean tree

VOCAB    ?= P66
LOTLANG  ?= en

install:
	$(PYTHON) -m pip install -r requirements.txt

models:
	$(PYTHON) -m spacy download en_core_web_sm
	$(PYTHON) -m spacy download fr_core_news_sm

# ── Tests ─────────────────────────────────────────────────────────────────────

test: test-smoke test-profiling test-quality

test-smoke:
	bash tests/smoke/test_v9_cli.sh

test-non-regression:
	bash tests/smoke/test_p66_non_regression.sh

test-profiling:
	bash tests/profiling/test_auto_profile_quality.sh

test-quality:
	bash tests/quality/test_v9_contextual.sh

test-api:
	$(PYTHON) test_api.py

# ── Benchmark & rendu HTML ────────────────────────────────────────────────────

# Benchmark complet : v9 local + API Terms-Matcher + Resolvers (EN + FR).
# BENCHMARK_ARGS permet de passer des options supplémentaires :
#   make benchmark BENCHMARK_ARGS="--vocabs P66_en,9SD_en"
#   make benchmark BENCHMARK_ARGS="--out-dir results/$(shell date +%Y%m%d)"
benchmark:
	bash tests/smoke/compare_engines.sh $(BENCHMARK_ARGS)

# Moteur local uniquement (pas d'appels réseau)
benchmark-local:
	bash tests/smoke/compare_engines.sh --skip-api --skip-resolvers $(BENCHMARK_ARGS)

# v9 local vs API Terms-Matcher uniquement
benchmark-api:
	bash tests/smoke/compare_engines.sh --skip-resolvers $(BENCHMARK_ARGS)

# v9 local vs Loterre Resolvers uniquement
benchmark-resolvers:
	bash tests/smoke/compare_engines.sh --skip-api $(BENCHMARK_ARGS)

# Génère les fichiers HTML annotés pour tous les corpus dans data/texts/.
html:
	bash tests/smoke/render_html_annotation.sh

# ── Production ────────────────────────────────────────────────────────────────

run:
	bash production/run_local_ezs.sh $(VOCAB) $(LOTLANG)

ezs-test:
	bash production/test_local_ezs.sh

ws-test:
	bash production/test_ws.sh local

ws-test-accel:
	bash production/test_ws.sh accel

build:
	bash production/build_push_package.sh

deploy:
	bash production/ws_deploy_docker_local.sh

# ── Maintenance ───────────────────────────────────────────────────────────────

clean:
	rm -rf outputs outputs_tests_v9_cli outputs_predictions outputs_autoprofile_quality \
	       outputs_v9_contextual benchmark_results html_outputs \
	       eval_outputs profile_outputs .pytest_cache
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +

tree:
	find . -maxdepth 4 -type f | sort
