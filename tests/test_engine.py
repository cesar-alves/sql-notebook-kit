import sqlite3

import pandas as pd
import pytest

from redshift_notebooks.engine import make_engine, register
from redshift_notebooks.results import NotebookResult
from redshift_notebooks.session import create_session


def _sqlite_factory(calls):
    def factory():
        calls.append(1)
        return sqlite3.connect(":memory:")

    return factory


def test_make_engine_wraps_arbitrary_connection_factory():
    calls = []
    engine = make_engine(_sqlite_factory(calls), dialect="sqlite")

    with engine.begin() as conn:
        conn.exec_driver_sql("create table t (x int)")
        conn.exec_driver_sql("insert into t values (1), (2)")

    with engine.connect() as conn:
        df = pd.read_sql_query("select * from t order by x", conn)
    assert list(df["x"]) == [1, 2]
    engine.dispose()


def test_single_connection_queue_reuses_a_connection():
    # The one-connection pool calls the factory once and serializes reuse.
    calls = []
    engine = make_engine(_sqlite_factory(calls), dialect="sqlite")

    with engine.begin() as conn:
        conn.exec_driver_sql("create table t (x int)")
    with engine.connect() as conn:
        pd.read_sql_query("select * from t", conn)
        pd.read_sql_query("select * from t", conn)

    assert len(calls) == 1
    engine.dispose()


def test_register_requires_an_ipython_session():
    engine = make_engine(_sqlite_factory([]), dialect="sqlite")
    with pytest.raises(RuntimeError):
        register(engine)
    engine.dispose()


def test_register_wires_up_sql_magic_end_to_end():
    ipython_testing = pytest.importorskip("IPython.testing.globalipapp")
    shell = ipython_testing.get_ipython()

    engine = make_engine(_sqlite_factory([]), dialect="sqlite")
    register(engine, alias="test_conn")

    shell.run_cell("%%sql\ncreate table t (x int)")
    shell.run_cell("%%sql\ninsert into t values (1), (2)")
    result = shell.run_cell("%sql select * from t order by x")

    assert list(result.result.DataFrame()["x"]) == [1, 2]
    shell.run_line_magic("sql", "--close test_conn")


def test_session_wraps_sql_cell_results_with_a_bounded_dataframe():
    ipython_testing = pytest.importorskip("IPython.testing.globalipapp")
    shell = ipython_testing.get_ipython()

    calls = []

    def factory():
        calls.append(1)
        return sqlite3.connect(":memory:")

    session = create_session(factory=factory, dialect="sqlite")
    session.register(alias="bounded", visualization=True, max_rows=2)
    session.register(alias="bounded", visualization=True, max_rows=2)
    assert len(calls) == 1
    execution = shell.run_cell(
        "bounded_result = get_ipython().run_cell_magic("
        "'sql', '', 'select 1 as x union all select 2 union all select 3 order by x')"
    )

    assert execution.error_in_exec is None
    bounded_result = shell.user_ns["bounded_result"]
    assert isinstance(bounded_result, NotebookResult)
    assert bounded_result.dataframe["x"].tolist() == [1, 2]
    assert bounded_result.truncated is True
    session.reconnect()
    assert len(calls) == 2
    session.dispose()
