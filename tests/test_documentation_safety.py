import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DOCUMENTATION_FILES = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
FORBIDDEN_PATTERNS = {
    "12-digit account identifier": re.compile(r"(?<![<\d])\d{12}(?![>\d])"),
    "concrete role ARN": re.compile(r"arn:aws:iam::(?!<aws-account-id>)"),
    "email address": re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    "environment-specific VPN name": re.compile(r"Dataeng-Prod", re.IGNORECASE),
}


@pytest.mark.parametrize("path", DOCUMENTATION_FILES, ids=lambda path: path.name)
def test_documentation_contains_no_real_infrastructure_identifiers(path):
    text = path.read_text()
    violations = [name for name, pattern in FORBIDDEN_PATTERNS.items() if pattern.search(text)]
    assert not violations, f"{path.relative_to(ROOT)} contains: {', '.join(violations)}"


def test_quickstart_is_credential_free_and_uses_the_certified_backend():
    notebook = json.loads((ROOT / "examples" / "quickstart.ipynb").read_text())
    text = "\n".join(
        cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])
        for cell in notebook["cells"]
    )
    for pattern in FORBIDDEN_PATTERNS.values():
        assert pattern.search(text) is None
    assert "<" not in text
    assert 'backend="duckdb"' in text
    assert '"database": ":memory:"' in text
    assert "needs no credentials or external data" in text
