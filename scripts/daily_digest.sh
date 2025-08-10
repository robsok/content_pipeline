#!/usr/bin/env bash
set -Eeuo pipefail

REPO="/home/rms110/Agents/content_pipeline"
PY="$REPO/.venv/bin/python"

cd "$REPO"

echo "[$(date +'%F %T')] daily: fetch"
$PY pipeline.py voice_act fetch

echo "[$(date +'%F %T')] daily: score"
$PY pipeline.py voice_act score

echo "[$(date +'%F %T')] daily: review-email"
$PY pipeline.py voice_act review-email
