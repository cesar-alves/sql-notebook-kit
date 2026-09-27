#!/usr/bin/env python3
"""Reject unreviewed dependency-license metadata and unsafe build-only redistribution."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
UNREVIEWED = {"", "unknown", "unlicensed", "none", "n/a"}


def findings(report: Any, *, ecosystem: str, overrides: dict[str, str]) -> list[str]:
    packages: list[tuple[str, str]] = []
    if ecosystem == "pypi":
        packages = [(item["Name"], item.get("License", "")) for item in report]
    else:
        packages = [
            (item["name"], license_name)
            for license_name, items in report.items()
            for item in items
        ]
    errors = []
    for name, license_name in packages:
        reviewed = overrides.get(name, license_name).strip().lower()
        if reviewed in UNREVIEWED:
            errors.append(f"{name} has unreviewed license metadata: {license_name or '<empty>'}")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ecosystem", choices=("pypi", "npm"), required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    policy = tomllib.loads((ROOT / "licenses" / "review.toml").read_text())
    errors = findings(
        json.loads(args.report.read_text()),
        ecosystem=args.ecosystem,
        overrides=policy["overrides"],
    )
    for error in errors:
        print(f"license policy: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
