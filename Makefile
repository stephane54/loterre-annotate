PYTHON ?= python

.PHONY: install models test test-smoke test-profiling test-quality clean tree

install:
	$(PYTHON) -m pip install -r requirements.txt

models:
	$(PYTHON) -m spacy download en_core_web_sm
	$(PYTHON) -m spacy download fr_core_news_sm

test: test-smoke test-profiling test-quality

test-smoke:
	bash tests/smoke/test_v9_cli.sh

test-profiling:
	bash tests/profiling/test_auto_profile_quality.sh

test-quality:
	bash tests/quality/test_v9_contextual.sh

clean:
	rm -rf outputs eval_outputs profile_outputs .pytest_cache __pycache__
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +

tree:
	find . -maxdepth 4 -type f | sort
