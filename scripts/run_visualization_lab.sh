#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

exec uv run --group gui voila dev/visualization_lab.ipynb \
  --no-browser \
  --port="${SQL_NOTEBOOK_KIT_LAB_PORT:-8866}"
