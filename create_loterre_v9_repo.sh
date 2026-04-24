#!/usr/bin/env bash
set -euo pipefail

mkdir -p loterre-v9/{src,configs/examples,scripts/{profiling,prediction,evaluation,benchmark},tests/{smoke,profiling,quality},gold,predictions,eval_outputs}

cat > loterre-v9/.gitignore <<'EOF'
__pycache__/
*.py[cod]
.venv/
venv/
eval_outputs/
profile_outputs/
outputs/
dicts/
texts/
examples/
*.zip
.DS_Store
EOF

cat > loterre-v9/requirements.txt <<'EOF'
spacy>=3.7
pyyaml>=6.0
EOF

cat > loterre-v9/Makefile <<'EOF'
PYTHON ?= python
CLI := ./src/loterre_cli.py
EVAL := ./scripts/evaluation/evaluate_json.py

.PHONY: install models test clean

install:
	$(PYTHON) -m pip install -r requirements.txt

models:
	$(PYTHON) -m spacy download en_core_web_sm
	$(PYTHON) -m spacy download fr_core_news_sm

test:
	bash tests/smoke/test_v9_cli.sh
	bash tests/profiling/test_auto_profile_quality.sh
	bash tests/quality/test_v9_contextual.sh

clean:
	rm -rf outputs eval_outputs profile_outputs __pycache__
EOF

echo "Repo skeleton created in ./loterre-v9"
echo "Copy src/, scripts/, tests/, configs/ from the package into this skeleton."
