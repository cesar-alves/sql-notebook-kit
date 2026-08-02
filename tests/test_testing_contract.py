import sqlite3

import pytest

from redshift_notebooks.errors import NotebookConnectionError
from redshift_notebooks.testing import run_factory_contract


def test_contract_runner_validates_live_factory():
    report = run_factory_contract(lambda: sqlite3.connect(":memory:"))
    assert report.distinct_connections
    assert report.probe_executed


def test_contract_runner_rejects_cached_connections():
    connection = sqlite3.connect(":memory:")
    with pytest.raises(NotebookConnectionError, match="same physical connection"):
        run_factory_contract(lambda: connection)
