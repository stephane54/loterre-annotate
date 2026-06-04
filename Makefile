PYTHON ?= python3

.PHONY: install models \
        test test-smoke test-non-regression test-profiling test-quality test-api \
        benchmark html \
        clean tree

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

# Lance le benchmark complet v9 vs API (EN + FR).
# Options transmissibles : make benchmark BENCHMARK_ARGS="--vocabs P66_en --skip-api"
benchmark:
	bash tests/smoke/compare_engines.sh $(BENCHMARK_ARGS)

# Génère les fichiers HTML annotés pour tous les corpus dans examples/texts/.
html:
	bash tests/smoke/render_html_annotation.sh

# ── Maintenance ───────────────────────────────────────────────────────────────

clean:
	rm -rf outputs outputs_tests_v9_cli outputs_predictions outputs_autoprofile_quality \
	       outputs_v9_contextual benchmark_results html_outputs \
	       eval_outputs profile_outputs .pytest_cache
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +

tree:
	find . -maxdepth 4 -type f | sort
