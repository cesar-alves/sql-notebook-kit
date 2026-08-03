import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_visualization_extras_declare_nbformat():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    extras = project["optional-dependencies"]

    assert "nbformat>=5.10,<6" in extras["viz"]
    assert "nbformat>=5.10,<6" in extras["all"]


def test_bundled_vscode_extension_matches_python_version():
    vsix = ROOT / "redshift_notebooks/vscode/redshift-notebooks-vscode.vsix"
    assert vsix.is_file()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    with zipfile.ZipFile(vsix) as archive:
        package = __import__("json").loads(archive.read("extension/package.json"))
        renderer = archive.read("extension/dist/renderer.js")
    assert package["version"] == project["version"]
    assert package["extensionDependencies"] == ["ms-toolsai.jupyter"]
    assert package["extensionKind"] == ["workspace"]
    assert b"export {" in renderer
    assert b"activate" in renderer
