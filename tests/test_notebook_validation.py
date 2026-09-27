from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_notebooks import validate_notebook


def _write_notebook(path: Path, *, notebook_metadata=None, cell_metadata=None, **cell):
    payload = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "id": "safe-cell",
                "metadata": cell_metadata or {},
                "outputs": [],
                "source": ["value = '<placeholder>'\n"],
                **cell,
            }
        ],
        "metadata": notebook_metadata or {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(payload))


def test_clean_notebook_preserves_ids_and_intentional_tags(tmp_path):
    path = tmp_path / "clean.ipynb"
    _write_notebook(path, cell_metadata={"tags": ["release-smoke"]})
    assert validate_notebook(path) == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"execution_count": 1}, "execution_count"),
        ({"outputs": [{"output_type": "stream", "text": "result"}]}, "outputs"),
        ({"source": ["path = '/home/example/private/data.db'"]}, "absolute home path"),
        ({"source": ["password = 'usable-secret'"]}, "credential assignment"),
        (
            {"source": ["url = 'postgresql://dbuser:secret@db.example/test'"]},
            "credential-bearing database URL",
        ),
        ({"source": ["-----BEGIN PRIVATE KEY-----"]}, "private key"),
        (
            {"source": ["token = 'AKIA" + "ABCDEFGHIJKLMNOP'"]},
            "AWS access key",
        ),
        ({"source": ["A" * 100_001]}, "embedded text payload"),
    ],
)
def test_sensitive_notebook_cases_fail(tmp_path, change, message):
    path = tmp_path / "unsafe.ipynb"
    _write_notebook(path, **change)
    assert any(message in error for error in validate_notebook(path))


def test_unexpected_notebook_and_cell_metadata_fail(tmp_path):
    path = tmp_path / "unsafe.ipynb"
    _write_notebook(
        path,
        notebook_metadata={"widgets": {"state": "local"}},
        cell_metadata={"tags": ["safe"], "vscode": {"session": "private"}},
    )
    errors = validate_notebook(path)
    assert any("unexpected notebook metadata: widgets" in error for error in errors)
    assert any("unexpected metadata: vscode" in error for error in errors)
