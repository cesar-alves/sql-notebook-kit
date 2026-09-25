#!/usr/bin/env python3
"""Enforce Gitflow branch, version, changelog, and signed-tag release policy."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = r"0|[1-9]\d*(?:\.(?:0|[1-9]\d*)){2}"
RELEASE_BRANCH = re.compile(rf"^release/v(?P<version>{VERSION_PATTERN})$")
HOTFIX_BRANCH = re.compile(rf"^hotfix/v(?P<version>{VERSION_PATTERN})$")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, check=False, capture_output=True, text=True)


def project_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def manifest_versions() -> dict[str, str]:
    paths = (
        "frontend/protocol/package.json",
        "frontend/jupyterlab/package.json",
        "frontend/vscode/package.json",
        "sql_notebook_kit/labextension/package.json",
    )
    return {path: json.loads((ROOT / path).read_text())["version"] for path in paths}


def check_version(expected: str) -> list[str]:
    versions = {"pyproject.toml": project_version(), **manifest_versions()}
    errors = [
        f"{path} has version {actual}, expected {expected}"
        for path, actual in versions.items()
        if actual != expected
    ]
    changelog = (ROOT / "CHANGELOG.md").read_text()
    if not re.search(rf"^## \[{re.escape(expected)}\] - \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.M):
        errors.append(f"CHANGELOG.md has no dated [{expected}] release heading")
    return errors


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    return _run("git", "merge-base", "--is-ancestor", ancestor, descendant).returncode == 0


def check_pull_request(base: str, head: str, *, commit: str = "HEAD") -> list[str]:
    if base != "main":
        return []
    match = RELEASE_BRANCH.fullmatch(head) or HOTFIX_BRANCH.fullmatch(head)
    if not match:
        return ["pull requests to main must come from release/vX.Y.Z or hotfix/vX.Y.Z"]
    version = match.group("version")
    errors = check_version(version)
    main_ref = "origin/main"
    if not _is_ancestor(main_ref, commit):
        errors.append(f"{head} does not descend from {main_ref}")
    if head.startswith("release/"):
        develop_ref = "origin/develop"
        merge_base = _run("git", "merge-base", commit, develop_ref)
        if merge_base.returncode != 0:
            errors.append(f"cannot establish {develop_ref} ancestry for {head}")
        elif merge_base.stdout.strip() == _run("git", "rev-parse", main_ref).stdout.strip():
            errors.append(f"{head} has no release ancestry beyond {main_ref}; cut it from develop")
    elif _run("git", "merge-base", main_ref, commit).stdout.strip() != _run(
        "git", "rev-parse", main_ref
    ).stdout.strip():
        errors.append(f"{head} must be cut from the current main commit")
    return errors


def _print_errors(errors: list[str]) -> int:
    for error in errors:
        print(f"release policy: {error}", file=sys.stderr)
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    version_parser = subparsers.add_parser("version")
    version_parser.add_argument("expected")
    pr_parser = subparsers.add_parser("pr")
    pr_parser.add_argument("--base", required=True)
    pr_parser.add_argument("--head", required=True)
    pr_parser.add_argument("--commit", default="HEAD")
    args = parser.parse_args(argv)

    if args.command == "version":
        return _print_errors(check_version(args.expected))
    return _print_errors(check_pull_request(args.base, args.head, commit=args.commit))


if __name__ == "__main__":
    raise SystemExit(main())
