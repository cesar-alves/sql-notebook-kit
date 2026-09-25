#!/usr/bin/env bash
set -euo pipefail

uv run ruff check .
uv run mypy sql_notebook_kit
uv run pytest --cov=sql_notebook_kit --cov-branch --cov-report=term-missing
pnpm check
pnpm test
uv run --group docs mkdocs build --strict
uv run python scripts/check_notebooks.py
