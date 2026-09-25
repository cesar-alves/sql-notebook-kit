#!/usr/bin/env python3
"""Smoke-test an installed wheel without importing the source checkout."""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()

    package = importlib.import_module("sql_notebook_kit")
    assert version("sql-notebook-kit") == args.expected_version
    for module in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        importlib.import_module(module.name)
    importlib.import_module("sql_notebook_kit.visualize")

    subprocess.run([sys.executable, "-m", "sql_notebook_kit.cli", "--help"], check=True)
    subprocess.run(
        [sys.executable, "-m", "sql_notebook_kit.cli", "vscode", "path"], check=True
    )
    jupyter_name = "jupyter.exe" if sys.platform == "win32" else "jupyter"
    jupyter = Path(sys.executable).with_name(jupyter_name)
    discovered = subprocess.run(
        [str(jupyter), "labextension", "list"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert discovered.returncode == 0, discovered.stdout + discovered.stderr
    assert "@sql-notebook-kit/jupyterlab" in discovered.stdout + discovered.stderr

    from IPython.core.interactiveshell import InteractiveShell

    from sql_notebook_kit import create_session
    from sql_notebook_kit.results import NotebookResult

    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "smoke.duckdb"
        shell = InteractiveShell.instance()
        session = create_session(
            backend="duckdb",
            connection_kwargs={"database": str(database)},
        )
        session.register(visualization=True, max_rows=2)
        try:
            query = "select range as i from range(5)"
            eager = shell.run_cell(f"%sql {query}")
            assert eager.error_in_exec is None
            assert isinstance(eager.result, NotebookResult)
            assert len(eager.result.dataframe) == 2
            assert eager.result.truncated

            lazy = session.sql(query).collect(max_rows=2)
            assert len(lazy.dataframe) == 2
            assert lazy.truncated
        finally:
            session.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
