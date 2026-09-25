#!/usr/bin/env python3
"""Run the complete cross-platform local validation suite."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)  # noqa: S603


def main() -> int:
    commands = [
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "mypy", "sql_notebook_kit"],
        [
            "uv",
            "run",
            "pytest",
            "--cov=sql_notebook_kit",
            "--cov-branch",
            "--cov-report=term-missing",
        ],
        ["pnpm", "check"],
        ["pnpm", "test"],
        ["pnpm", "build:artifacts"],
        [
            "git",
            "diff",
            "--exit-code",
            "--",
            "sql_notebook_kit/labextension",
            "sql_notebook_kit/vscode",
        ],
        ["uv", "run", "--group", "docs", "mkdocs", "build", "--strict"],
        ["uv", "run", "python", "scripts/check_notebooks.py"],
    ]
    for command in commands:
        _run(command)

    with tempfile.TemporaryDirectory(prefix="sql-notebook-kit-validation-") as directory:
        _run(
            [
                "uv",
                "run",
                "--group",
                "frontend",
                "jupyter",
                "nbconvert",
                "--to",
                "notebook",
                "--execute",
                "examples/quickstart.ipynb",
                "--output",
                "executed-quickstart.ipynb",
                "--output-dir",
                directory,
                "--ExecutePreprocessor.timeout=120",
            ]
        )
        assert (Path(directory) / "executed-quickstart.ipynb").is_file()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
