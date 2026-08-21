from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
NOTEBOOK_PATH = ROOT / "examples" / "duckdb.ipynb"


def _notebook() -> dict:
    return json.loads(NOTEBOOK_PATH.read_text())


def _tagged_source(tag: str) -> str:
    for cell in _notebook()["cells"]:
        if tag in cell.get("metadata", {}).get("tags", []):
            return "".join(cell["source"])
    raise AssertionError(f"notebook cell with tag {tag!r} was not found")


def test_duckdb_sample_is_clean_and_uses_the_environment_source():
    notebook = _notebook()
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    setup = _tagged_source("duckdb-setup")

    assert 'os.environ.get("DUCK_DB_SOURCE", "")' in setup
    assert 'backend="duckdb"' in setup
    assert '"read_only": True' in setup
    assert all(cell["execution_count"] is None for cell in code_cells)
    assert all(cell["outputs"] == [] for cell in code_cells)


@pytest.mark.parametrize("source", [None, "   "])
def test_duckdb_sample_requires_a_nonempty_source(monkeypatch, source):
    if source is None:
        monkeypatch.delenv("DUCK_DB_SOURCE", raising=False)
    else:
        monkeypatch.setenv("DUCK_DB_SOURCE", source)

    with pytest.raises(RuntimeError, match="DUCK_DB_SOURCE must point"):
        exec(_tagged_source("duckdb-setup"), {})


def test_duckdb_sample_runs_sql_and_lazy_queries(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    database = tmp_path / "sample.duckdb"
    setup_connection = duckdb.connect(str(database))
    setup_connection.execute("create table sample_items(item_id integer)")
    setup_connection.close()
    script = r'''
import json
import sys
from pathlib import Path

from IPython.testing.globalipapp import get_ipython
from sql_notebook_kit.results import NotebookResult

notebook = json.loads(Path(sys.argv[1]).read_text())

def tagged_source(tag):
    for cell in notebook["cells"]:
        if tag in cell.get("metadata", {}).get("tags", []):
            return "".join(cell["source"])
    raise AssertionError(f"notebook cell with tag {tag!r} was not found")

shell = get_ipython()
setup = shell.run_cell(tagged_source("duckdb-setup"))
assert setup.error_in_exec is None
session = shell.user_ns["session"]
try:
    identity = shell.run_cell(tagged_source("duckdb-sql-smoke"))
    catalog = shell.run_cell(tagged_source("duckdb-catalog-sql"))
    lazy = shell.run_cell(tagged_source("duckdb-lazy-smoke"))

    assert identity.error_in_exec is None
    assert isinstance(identity.result, NotebookResult)
    assert identity.result.dataframe.loc[0, "database_name"] == "sample"
    assert catalog.error_in_exec is None
    assert isinstance(catalog.result, NotebookResult)
    assert "sample_items" in catalog.result.dataframe["table_name"].tolist()
    assert lazy.error_in_exec is None
    assert "sample_items" in shell.user_ns["catalog_result"].dataframe["table_name"].tolist()
finally:
    session.dispose()
'''
    environment = dict(os.environ)
    environment["DUCK_DB_SOURCE"] = str(database)

    completed = subprocess.run(
        [sys.executable, "-c", script, str(NOTEBOOK_PATH)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
