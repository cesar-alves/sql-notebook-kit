#!/usr/bin/env bash
set -euo pipefail

exec uv run python scripts/validate.py
