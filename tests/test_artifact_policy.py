from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from scripts.check_artifacts import _check_vscode, _sdist_allowed, check_wheel

VERSION = "0.1.0"


def _vsix_bytes(*, unexpected: bool = False) -> bytes:
    output = io.BytesIO()
    manifest = {
        "version": VERSION,
        "description": "Companion",
        "categories": ["Data Science"],
        "keywords": ["sql"],
        "repository": {"url": "https://example.invalid/repository"},
        "bugs": {"url": "https://example.invalid/issues"},
    }
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "content types")
        archive.writestr("extension.vsixmanifest", "manifest")
        archive.writestr("extension/package.json", json.dumps(manifest))
        archive.writestr("extension/LICENSE.txt", "MIT")
        archive.writestr("extension/dist/extension.cjs", "compiled")
        archive.writestr("extension/dist/renderer.js", "compiled")
        archive.writestr("extension/dist/widgetFallback.js", "compiled")
        archive.writestr(
            "extension/syntaxes/sql-notebook-kit-sql-magic.tmLanguage.json", "{}"
        )
        if unexpected:
            archive.writestr("extension/private-notes.txt", "not shipped")
    return output.getvalue()


def test_vsix_allowlist_rejects_unexpected_file():
    with zipfile.ZipFile(io.BytesIO(_vsix_bytes(unexpected=True))) as archive:
        assert any("outside its allowlist" in error for error in _check_vscode(
            archive, expected_version=VERSION
        ))


def test_wheel_allowlist_and_alpha_metadata_reject_unexpected_file(tmp_path: Path):
    wheel = tmp_path / "package.whl"
    jupyter = (
        f"sql_notebook_kit-{VERSION}.data/data/share/jupyter/labextensions/"
        "@sql-notebook-kit/jupyterlab/"
    )
    dist_info = f"sql_notebook_kit-{VERSION}.dist-info/"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("sql_notebook_kit/__init__.py", "")
        archive.writestr("sql_notebook_kit/vscode/sql-notebook-kit-vscode.vsix", _vsix_bytes())
        archive.writestr(f"{jupyter}install.json", "{}")
        archive.writestr(f"{jupyter}package.json", "{}")
        archive.writestr(f"{jupyter}static/third-party-licenses.json", "{}")
        archive.writestr(f"{dist_info}METADATA", "API-unstable alpha")
        archive.writestr(f"{dist_info}WHEEL", "")
        archive.writestr(f"{dist_info}entry_points.txt", "")
        archive.writestr(f"{dist_info}licenses/LICENSE", "MIT")
        archive.writestr(f"{dist_info}RECORD", "")
        archive.writestr("private-notes.txt", "not shipped")
    assert any("outside its allowlist" in error for error in check_wheel(
        wheel, expected_version=VERSION
    ))


def test_sdist_allowlist_is_explicit():
    assert _sdist_allowed("docs/index.md")
    assert _sdist_allowed("frontend/vscode/src/extension.ts")
    assert _sdist_allowed("uv.lock")
    assert not _sdist_allowed("tests/test_private_contract.py")
    assert not _sdist_allowed("operator-notes.txt")
