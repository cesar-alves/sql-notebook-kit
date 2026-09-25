#!/usr/bin/env python3
"""Validate tracked notebooks as deterministic, release-safe source files."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_NOTEBOOK_METADATA = {"kernelspec", "language_info", "voila"}
ALLOWED_CELL_METADATA = {"tags"}
MAX_EMBEDDED_TEXT = 100_000
SENSITIVE_PATTERNS = {
    "absolute home path": re.compile(r"(?:/home/[^/\s]+/|/Users/[^/\s]+/|[A-Za-z]:\\\\Users\\\\)"),
    "credential assignment": re.compile(
        r"(?i)(?:password|passwd|token|api[_-]?key|client[_-]?secret)\s*[:=]\s*['\"][^<\s][^'\"]+"
    ),
    "credential-bearing database URL": re.compile(
        r"(?i)\b(?:postgres(?:ql)?|redshift|mysql|mariadb|mssql)\+?[\w-]*://[^\s/@:]+:[^\s/@]+@"
    ),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
}


def tracked_notebooks() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "*.ipynb"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in completed.stdout.splitlines() if line]


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _walk_strings(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _walk_strings(item)]
    return []


def validate_notebook(path: Path) -> list[str]:
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid notebook JSON: {exc}"]

    errors: list[str] = []
    metadata = notebook.get("metadata", {})
    unexpected = sorted(set(metadata) - ALLOWED_NOTEBOOK_METADATA)
    if unexpected:
        errors.append(f"unexpected notebook metadata: {', '.join(unexpected)}")

    for index, cell in enumerate(notebook.get("cells", [])):
        prefix = f"cell {index}"
        cell_metadata = cell.get("metadata", {})
        unexpected = sorted(set(cell_metadata) - ALLOWED_CELL_METADATA)
        if unexpected:
            errors.append(f"{prefix}: unexpected metadata: {', '.join(unexpected)}")
        if cell.get("cell_type") == "code":
            if cell.get("execution_count") is not None:
                errors.append(f"{prefix}: execution_count must be null")
            if cell.get("outputs"):
                errors.append(f"{prefix}: outputs must be empty")

    for text in _walk_strings(notebook):
        if len(text) > MAX_EMBEDDED_TEXT:
            errors.append(f"embedded text payload exceeds {MAX_EMBEDDED_TEXT} characters")
        for name, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"contains {name}")

    return sorted(set(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    paths = args.paths or tracked_notebooks()
    failures = {
        path: errors
        for path in paths
        if (errors := validate_notebook(path if path.is_absolute() else ROOT / path))
    }
    for path, errors in failures.items():
        label = path if path.is_absolute() else path.relative_to(ROOT)
        for error in errors:
            print(f"{label}: {error}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
