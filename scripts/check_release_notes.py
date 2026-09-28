#!/usr/bin/env python3
"""Require a changelog entry for user-facing pull-request changes."""

from __future__ import annotations

import argparse
import os
import subprocess
from collections.abc import Iterable

USER_FACING_PREFIXES = ("sql_notebook_kit/", "frontend/", "docs/")
USER_FACING_FILES = {"README.md", "pyproject.toml", "package.json"}


def needs_release_note(paths: Iterable[str]) -> bool:
    return any(
        path in USER_FACING_FILES or path.startswith(USER_FACING_PREFIXES)
        for path in paths
    )


def changed_paths(base: str) -> list[str]:
    result = subprocess.run(  # nosemgrep
        ["git", "diff", "--name-only", "--diff-filter=ACMRT", f"{base}...HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base revision for the PR diff")
    args = parser.parse_args()
    paths = changed_paths(args.base)
    if not needs_release_note(paths) or "CHANGELOG.md" in paths:
        return 0
    if os.environ.get("RELEASE_NOTE_EXEMPT", "").lower() == "true":
        print("Release-note exemption accepted from the pull-request label.")
        return 0
    print(
        "User-facing changes require CHANGELOG.md or the release-note:exempt label."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
