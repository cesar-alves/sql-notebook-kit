import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_visualization_extras_declare_nbformat():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    extras = project["optional-dependencies"]

    assert "nbformat>=5.10,<6" in extras["viz"]
    assert "nbformat>=5.10,<6" in extras["all"]
