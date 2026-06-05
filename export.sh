#!/usr/bin/env bash
set -euo pipefail

OUTPUT="/tmp/zerohour-aviation.zip"

rm -f "$OUTPUT"

zip -r "$OUTPUT" . \
  -x ".venv/*" \
  -x ".venv312/*" \
  -x "__pycache__/*" \
  -x "*/__pycache__/*" \
  -x ".pytest_cache/*" \
  -x ".mypy_cache/*" \
  -x ".ruff_cache/*" \
  -x ".git/*"

echo "Exported project archive to $OUTPUT"
