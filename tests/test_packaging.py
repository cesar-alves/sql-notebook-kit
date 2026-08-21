import json
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def test_core_dependencies_include_jupysql_toml_support():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

    assert "toml>=0.10.2,<1" in project["dependencies"]


def test_visualization_extras_declare_nbformat():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    extras = project["optional-dependencies"]

    assert "nbformat>=5.10,<6" in extras["viz"]
    assert "nbformat>=5.10,<6" in extras["all"]


def test_gui_group_declares_python_kernel():
    dependency_groups = tomllib.loads((ROOT / "pyproject.toml").read_text())[
        "dependency-groups"
    ]

    assert "ipykernel>=6,<8" in dependency_groups["gui"]


def test_vscode_extension_manifest_matches_python_version():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    package = json.loads((ROOT / "frontend/vscode/package.json").read_text())

    assert package["version"] == project["version"]
    assert package["extensionDependencies"] == ["ms-toolsai.jupyter"]
    assert package["extensionKind"] == ["workspace"]


def test_staged_vscode_extension_contains_compiled_renderers():
    vsix = ROOT / "sql_notebook_kit/vscode/sql-notebook-kit-vscode.vsix"
    if not vsix.is_file():
        pytest.skip("generated VSIX has not been staged")

    with zipfile.ZipFile(vsix) as archive:
        renderer = archive.read("extension/dist/renderer.js")
        widget_fallback = archive.read("extension/dist/widgetFallback.js")

    assert b"export {" in renderer
    assert b"activate" in renderer
    assert b"jupyter-ipywidget-renderer" in widget_fallback
