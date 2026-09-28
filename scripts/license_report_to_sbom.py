#!/usr/bin/env python3
"""Convert sanitized Python or pnpm license inventories to CycloneDX 1.6 JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
import urllib.parse
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _component(name: str, version: str, license_name: str, ecosystem: str) -> dict[str, Any]:
    normalized = re.sub(r"[-_.]+", "-", name).lower() if ecosystem == "pypi" else name
    encoded = urllib.parse.quote(normalized, safe="/")
    return {
        "type": "library",
        "bom-ref": f"pkg:{ecosystem}/{encoded}@{version}",
        "name": name,
        "version": version,
        "licenses": [{"license": {"name": license_name or "UNKNOWN"}}],
        "purl": f"pkg:{ecosystem}/{encoded}@{version}",
    }


def python_components(report: Any, overrides: dict[str, str]) -> list[dict[str, Any]]:
    return [
        _component(
            item["Name"],
            item["Version"],
            overrides.get(item["Name"], item.get("License", "UNKNOWN")),
            "pypi",
        )
        for item in report
    ]


def pnpm_components(report: Any, overrides: dict[str, str]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for license_name, packages in report.items():
        for package in packages:
            for version in package["versions"]:
                reviewed_license = overrides.get(package["name"], license_name)
                components.append(_component(package["name"], version, reviewed_license, "npm"))
    return components


def artifact_component(path: Path, version: str) -> dict[str, Any]:
    return {
        "type": "file",
        "bom-ref": f"artifact:{path.name}",
        "name": path.name,
        "version": version,
        "hashes": [{"alg": "SHA-256", "content": hashlib.sha256(path.read_bytes()).hexdigest()}],
    }


def build_sbom(
    report: Any,
    *,
    ecosystem: str,
    project_version: str,
    artifacts: list[Path],
    overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    overrides = overrides or {}
    components = (
        python_components(report, overrides)
        if ecosystem == "pypi"
        else pnpm_components(report, overrides)
    )
    unique = {component["bom-ref"]: component for component in components}
    artifact_components = [artifact_component(path, project_version) for path in artifacts]
    return {
        "$schema": "https://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "component": {
                "type": "application",
                "bom-ref": f"pkg:pypi/sql-notebook-kit@{project_version}",
                "name": "sql-notebook-kit",
                "version": project_version,
                "purl": f"pkg:pypi/sql-notebook-kit@{project_version}",
            },
        },
        "components": [
            *artifact_components,
            *sorted(unique.values(), key=lambda item: item["bom-ref"]),
        ],
    }


def validate_shape(sbom: dict[str, Any]) -> None:
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert re.fullmatch(r"urn:uuid:[0-9a-f-]{36}", sbom["serialNumber"])
    refs = [component["bom-ref"] for component in sbom["components"]]
    assert len(refs) == len(set(refs))
    assert all("name" in component and "version" in component for component in sbom["components"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ecosystem", choices=("pypi", "npm"), required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--project-version", required=True)
    parser.add_argument("--artifact", type=Path, action="append", default=[])
    parser.add_argument("--review", type=Path, default=ROOT / "licenses" / "review.toml")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    overrides = tomllib.loads(args.review.read_text())["overrides"]
    sbom = build_sbom(
        json.loads(args.report.read_text()),
        ecosystem=args.ecosystem,
        project_version=args.project_version,
        artifacts=args.artifact,
        overrides=overrides,
    )
    validate_shape(sbom)
    args.output.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
