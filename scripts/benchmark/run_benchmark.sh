#!/usr/bin/env bash
set -e

CLI_V8=$1
CLI_V81=$2
EVAL_DIR=$3
OUTDIR=benchmark_outputs

mkdir -p $OUTDIR

echo "== P66 v8 =="
python $CLI_V8 --text $EVAL_DIR/gold/texts_p66_en.jsonl --dict-id P66_en --silent > $OUTDIR/p66_v8.json
python $EVAL_DIR/scripts/evaluate_json.py --gold $EVAL_DIR/gold/gold_p66_en.jsonl --pred $OUTDIR/p66_v8.json > $OUTDIR/p66_v8_eval.json

echo "== P66 v8.1 =="
python $CLI_V81 --text $EVAL_DIR/gold/texts_p66_en.jsonl --dict-id P66_en --silent > $OUTDIR/p66_v81.json
python $EVAL_DIR/scripts/evaluate_json.py --gold $EVAL_DIR/gold/gold_p66_en.jsonl --pred $OUTDIR/p66_v81.json > $OUTDIR/p66_v81_eval.json

echo "== 9SD v8 =="
python $CLI_V8 --text $EVAL_DIR/gold/texts_9sd_en.jsonl --dict-id 9SD_en --silent > $OUTDIR/9sd_v8.json
python $EVAL_DIR/scripts/evaluate_json.py --gold $EVAL_DIR/gold/gold_9sd_en.jsonl --pred $OUTDIR/9sd_v8.json > $OUTDIR/9sd_v8_eval.json

echo "== 9SD v8.1 =="
python $CLI_V81 --text $EVAL_DIR/gold/texts_9sd_en.jsonl --dict-id 9SD_en --silent > $OUTDIR/9sd_v81.json
python $EVAL_DIR/scripts/evaluate_json.py --gold $EVAL_DIR/gold/gold_9sd_en.jsonl --pred $OUTDIR/9sd_v81.json > $OUTDIR/9sd_v81_eval.json

echo "== Done =="