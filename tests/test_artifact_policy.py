from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from scripts.check_artifacts import _check_vscode, _sdist_allowed, check_wheel
from scripts.normalize_vsix import FIXED_TIMESTAMP, normalize

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
    entries = {
        "[Content_Types].xml": "content types",
        "extension.vsixmanifest": "manifest",
        "extension/package.json": json.dumps(manifest),
        "extension/LICENSE.txt": "MIT",
        "extension/dist/extension.cjs": "compiled",
        "extension/dist/renderer.js": "compiled",
        "extension/dist/widgetFallback.js": "compiled",
        "extension/syntaxes/sql-notebook-kit-sql-magic.tmLanguage.json": "{}",
    }
    if unexpected:
        entries["extension/private-notes.txt"] = "not shipped"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, value in sorted(entries.items()):
            archive.writestr(name, value)
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
    assert _sdist_allowed("scripts/normalize_vsix.py")
    assert _sdist_allowed("uv.lock")
    assert not _sdist_allowed("tests/test_private_contract.py")
    assert not _sdist_allowed("operator-notes.txt")


def test_vsix_normalization_is_byte_reproducible(tmp_path: Path):
    archives = [tmp_path / "first.vsix", tmp_path / "second.vsix"]
    for index, archive in enumerate(archives):
        names = ("b.txt", "a.txt") if index == 0 else ("a.txt", "b.txt")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for name in names:
                info = zipfile.ZipInfo(name, (2025 + index, 1, 2, 3, 4, 6))
                output.writestr(info, name.encode())
        normalize(archive)

    assert archives[0].read_bytes() == archives[1].read_bytes()
    with zipfile.ZipFile(archives[0]) as archive:
        assert archive.namelist() == ["a.txt", "b.txt"]
        assert all(info.date_time == FIXED_TIMESTAMP for info in archive.infolist())
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())


def test_frontend_builds_are_configured_for_checkout_path_independence():
    root = Path(__file__).parents[1]
    webpack = (root / "frontend/jupyterlab/webpack.config.cjs").read_text()
    scripts = json.loads((root / "package.json").read_text())["scripts"]

    assert "moduleIds: 'natural'" in webpack
    assert "chunkIds: 'natural'" in webpack
    assert "scripts/normalize_vsix.py" in scripts["package:vscode"]
