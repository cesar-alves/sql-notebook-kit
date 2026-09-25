from __future__ import annotations

import json
import re
import subprocess
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
VERSION = "0.1.0"
PYTHON_VERSIONS = ("3.11", "3.12", "3.13", "3.14")
MANIFESTS = (
    ROOT / "frontend" / "protocol" / "package.json",
    ROOT / "frontend" / "jupyterlab" / "package.json",
    ROOT / "frontend" / "vscode" / "package.json",
    ROOT / "sql_notebook_kit" / "labextension" / "package.json",
)
LEGACY_IDENTITY_ALLOWLIST = {
    "docs/migration.md",
    "frontend/protocol/src/index.test.ts",
    "frontend/protocol/src/index.ts",
    "frontend/vscode/src/cellMetadata.test.ts",
    "sql_notebook_kit/notebook.py",
    "sql_notebook_kit/results.py",
    "sql_notebook_kit/labextension/static/949.ffead9a0c26c08af.js",
}


def _project():
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]


def test_build_backend_is_pinned_before_core_metadata_2_5_default():
    build_system = tomllib.loads((ROOT / "pyproject.toml").read_text())["build-system"]
    assert build_system["requires"] == ["hatchling==1.31.0"]


def test_alpha_wording_is_consistent_across_public_surfaces():
    wording = "API-unstable alpha"
    for path in (ROOT / "README.md", ROOT / "docs" / "index.md", ROOT / "CHANGELOG.md"):
        assert wording.lower() in path.read_text().lower(), path
    project = _project()
    assert "Development Status :: 3 - Alpha" in project["classifiers"]


def test_compatibility_contract_matches_python_and_frontend_manifests():
    project = _project()
    classifiers = set(project["classifiers"])
    compatibility = (ROOT / "docs" / "compatibility.md").read_text()

    assert project["requires-python"] == ">=3.11"
    for version in PYTHON_VERSIONS:
        assert f"Programming Language :: Python :: {version}" in classifiers
        assert version in compatibility
    assert "Framework :: Jupyter :: JupyterLab :: 4" in classifiers

    vscode = json.loads((ROOT / "frontend" / "vscode" / "package.json").read_text())
    assert vscode["engines"]["vscode"] == "^1.100.0"
    assert vscode["extensionDependencies"] == ["ms-toolsai.jupyter"]
    assert "1.100.0" in compatibility
    assert "`vscode.dev` | Unsupported" in compatibility


def test_every_source_and_generated_manifest_uses_release_version():
    assert _project()["version"] == VERSION
    assert all(json.loads(path.read_text())["version"] == VERSION for path in MANIFESTS)

    vsix = ROOT / "sql_notebook_kit" / "vscode" / "sql-notebook-kit-vscode.vsix"
    if vsix.is_file():
        with zipfile.ZipFile(vsix) as archive:
            manifest = json.loads(archive.read("extension/package.json"))
        assert manifest["version"] == VERSION


def test_backend_support_claims_are_consistent():
    for path in (ROOT / "README.md", ROOT / "docs" / "compatibility.md", ROOT / "CHANGELOG.md"):
        text = path.read_text().lower()
        assert "duckdb" in text and "certified" in text, path
        for backend in ("redshift", "databricks", "bigquery"):
            pattern = rf"(?:{backend}.{{0,120}}preview|preview.{{0,120}}{backend})"
            assert re.search(pattern, text, re.S), path


def test_legacy_identity_occurrences_are_narrowly_allowlisted():
    patterns = ("redshift-notebooks", "redshift_notebooks", "redshift notebooks")
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout.split(b"\0")
    found = {
        relative.decode()
        for relative in tracked
        if relative
        for path in [ROOT / relative.decode()]
        if path.is_file()
        if any(pattern in path.read_text(errors="ignore").lower() for pattern in patterns)
    }
    assert found == LEGACY_IDENTITY_ALLOWLIST


def test_vscode_manifest_has_coherent_embedded_artifact_metadata():
    manifest = json.loads((ROOT / "frontend" / "vscode" / "package.json").read_text())
    assert manifest["description"]
    assert manifest["categories"]
    assert manifest["keywords"]
    assert manifest["repository"]["url"].endswith("sql-notebook-kit.git")
    assert manifest["bugs"]["url"].endswith("/issues")
