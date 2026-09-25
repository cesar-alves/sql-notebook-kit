#!/usr/bin/env python3
"""Enforce the documented wheel, sdist, JupyterLab, and VSIX content contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {
    ".env",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "local",
    "node_modules",
    "site",
    "tests",
}
LOCAL_PATH = re.compile(rb"(?:/home/[^/\s]+/|/Users/[^/\s]+/|[A-Za-z]:\\Users\\)")
WHEEL_PACKAGE_SUFFIXES = (".py", ".css", ".vsix")
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
SDIST_ROOT_FILES = {
    ".node-version",
    ".python-version",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "PKG-INFO",
    "README.md",
    "RELEASING.md",
    "SECURITY.md",
    "SPEC.md",
    "SUPPORT.md",
    "hatch_build.py",
    "mkdocs.yml",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "scripts/normalize_vsix.py",
    "uv.lock",
}


def _forbidden(name: str) -> bool:
    return bool(FORBIDDEN_PARTS.intersection(Path(name).parts)) or name.endswith(
        (".pyc", ".pyo", ".map")
    )


def _wheel_allowed(name: str, *, expected_version: str) -> bool:
    if name.endswith("/"):
        return True
    if name == "sql_notebook_kit/py.typed":
        return True
    if name.startswith("sql_notebook_kit/") and name.endswith(WHEEL_PACKAGE_SUFFIXES):
        return True
    jupyter_prefix = (
        f"sql_notebook_kit-{expected_version}.data/data/share/jupyter/labextensions/"
        "@sql-notebook-kit/jupyterlab/"
    )
    if name in {f"{jupyter_prefix}install.json", f"{jupyter_prefix}package.json"}:
        return True
    if name.startswith(f"{jupyter_prefix}static/") and name.endswith((".js", ".json")):
        return True
    dist_info = f"sql_notebook_kit-{expected_version}.dist-info/"
    return name in {
        f"{dist_info}METADATA",
        f"{dist_info}RECORD",
        f"{dist_info}WHEEL",
        f"{dist_info}entry_points.txt",
        f"{dist_info}licenses/LICENSE",
    }


def _sdist_allowed(name: str) -> bool:
    if name in SDIST_ROOT_FILES or name.endswith("/"):
        return True
    return name.startswith(("docs/", "examples/", "frontend/", "sql_notebook_kit/"))


def _check_vscode(archive: zipfile.ZipFile, *, expected_version: str) -> list[str]:
    errors: list[str] = []
    ordered_names = archive.namelist()
    names = set(ordered_names)
    required = {
        "[Content_Types].xml",
        "extension.vsixmanifest",
        "extension/package.json",
        "extension/LICENSE.txt",
        "extension/dist/extension.cjs",
        "extension/dist/renderer.js",
        "extension/dist/widgetFallback.js",
        "extension/syntaxes/sql-notebook-kit-sql-magic.tmLanguage.json",
    }
    if missing := required - names:
        errors.append(f"VSIX is missing: {', '.join(sorted(missing))}")
    if "extension/package.json" in names:
        manifest = json.loads(archive.read("extension/package.json"))
        if manifest.get("version") != expected_version:
            errors.append("VSIX manifest version does not match the Python distribution")
        for field in ("description", "categories", "keywords", "repository", "bugs"):
            if not manifest.get(field):
                errors.append(f"VSIX manifest field {field!r} is empty")
    vscode_forbidden = FORBIDDEN_PARTS - {"dist"}
    if any(
        bool(vscode_forbidden.intersection(Path(name).parts))
        or name.endswith((".map", ".ts", ".tsx"))
        for name in names
    ):
        errors.append("VSIX contains a forbidden development or source-map file")
    unexpected = names - required
    if unexpected:
        errors.append(f"VSIX contains files outside its allowlist: {', '.join(sorted(unexpected))}")
    if ordered_names != sorted(ordered_names):
        errors.append("VSIX entries are not in deterministic order")
    if any(info.date_time != FIXED_ZIP_TIMESTAMP for info in archive.infolist()):
        errors.append("VSIX entries do not use the deterministic timestamp")
    if any(info.compress_type != zipfile.ZIP_STORED for info in archive.infolist()):
        errors.append("VSIX entries do not use deterministic stored encoding")
    return errors


def check_wheel(path: Path, *, expected_version: str) -> list[str]:
    errors: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        unexpected = [
            name
            for name in names
            if not _wheel_allowed(name, expected_version=expected_version)
        ]
        if unexpected:
            errors.append(
                "wheel contains files outside its allowlist: " + ", ".join(sorted(unexpected))
            )
        if any(_forbidden(name) for name in names):
            errors.append("wheel contains a forbidden development file")
        if any(name.startswith("sql_notebook_kit/labextension/") for name in names):
            errors.append("wheel duplicates the JupyterLab payload inside the Python package")
        jupyter = [
            name
            for name in names
            if ".data/data/share/jupyter/labextensions/@sql-notebook-kit/jupyterlab/" in name
        ]
        if not jupyter:
            errors.append("wheel has no JupyterLab shared-data payload")
        required_suffixes = ("/install.json", "/package.json", "/static/third-party-licenses.json")
        for suffix in required_suffixes:
            if sum(name.endswith(suffix) for name in jupyter) != 1:
                errors.append(f"wheel must contain exactly one JupyterLab {suffix[1:]}")
        if not any(name.endswith(".dist-info/licenses/LICENSE") for name in names):
            errors.append("wheel metadata has no root MIT license")
        metadata_name = f"sql_notebook_kit-{expected_version}.dist-info/METADATA"
        if metadata_name not in names:
            errors.append("wheel has no distribution metadata")
        elif b"API-unstable alpha" not in archive.read(metadata_name):
            errors.append("wheel metadata does not identify the API-unstable alpha")
        vsix_names = [name for name in names if name.endswith("sql-notebook-kit-vscode.vsix")]
        if len(vsix_names) != 1:
            errors.append("wheel must contain exactly one embedded VSIX")
        else:
            import io

            with zipfile.ZipFile(io.BytesIO(archive.read(vsix_names[0]))) as vsix:
                errors.extend(_check_vscode(vsix, expected_version=expected_version))
        for name in names:
            if LOCAL_PATH.search(archive.read(name)):
                errors.append(f"wheel member {name} contains an absolute home path")
    return sorted(set(errors))


def check_sdist(path: Path, *, expected_version: str) -> list[str]:
    errors: list[str] = []
    prefix = f"sql_notebook_kit-{expected_version}/"
    with tarfile.open(path, "r:gz") as archive:
        names = archive.getnames()
        if not names or any(not name.startswith(prefix) for name in names):
            errors.append("sdist has an unexpected root directory")
        relative = [name.removeprefix(prefix) for name in names]
        unexpected = [name for name in relative if not _sdist_allowed(name)]
        if unexpected:
            errors.append(
                "sdist contains files outside its allowlist: " + ", ".join(sorted(unexpected))
            )
        if any(_forbidden(name) for name in relative):
            errors.append("sdist contains a forbidden development file")
        required = {
            "LICENSE",
            "README.md",
            "CHANGELOG.md",
            "pyproject.toml",
            "uv.lock",
            "hatch_build.py",
            "pnpm-lock.yaml",
            "scripts/normalize_vsix.py",
            "frontend/vscode/package.json",
            "frontend/protocol/LICENSE",
            "sql_notebook_kit/labextension/static/third-party-licenses.json",
            "sql_notebook_kit/vscode/sql-notebook-kit-vscode.vsix",
            "examples/duckdb.ipynb",
        }
        if missing := required - set(relative):
            errors.append(f"sdist is missing rebuild/runtime inputs: {', '.join(sorted(missing))}")
        for member in archive.getmembers():
            if not member.isfile():
                continue
            extracted = archive.extractfile(member)
            assert extracted is not None
            if LOCAL_PATH.search(extracted.read()):
                errors.append(f"sdist member {member.name} contains an absolute home path")
    return sorted(set(errors))


def write_hashes(paths: list[Path], output: Path) -> None:
    lines = []
    for path in sorted(paths, key=lambda item: item.name):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}\n")
    output.write_text("".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--write-hashes", type=Path)
    args = parser.parse_args(argv)
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    wheels = sorted(args.directory.glob("*.whl"))
    sdists = sorted(args.directory.glob("*.tar.gz"))
    errors: list[str] = []
    if len(wheels) != 1 or len(sdists) != 1:
        errors.append("artifact directory must contain exactly one wheel and one sdist")
    if len(wheels) == 1:
        errors.extend(check_wheel(wheels[0], expected_version=version))
    if len(sdists) == 1:
        errors.extend(check_sdist(sdists[0], expected_version=version))
    if args.write_hashes and not errors:
        write_hashes(wheels + sdists, args.write_hashes)
    for error in errors:
        print(f"artifact policy: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
