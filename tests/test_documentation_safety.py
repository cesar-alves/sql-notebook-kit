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


def test_quickstart_contains_only_placeholder_identity_values():
    text = (ROOT / "examples" / "quickstart.ipynb").read_text()
    for pattern in FORBIDDEN_PATTERNS.values():
        assert pattern.search(text) is None
    assert "<aws-account-id>" in text
    assert "<role-name>" in text
    assert "<user-email>" in text
