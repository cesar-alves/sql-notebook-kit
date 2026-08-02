import sqlite3

import pandas as pd
import pytest

from redshift_notebooks.engine import make_engine, register


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


def test_static_pool_reuses_a_single_connection():
    # StaticPool should call the factory once and reuse that connection across
    # queries, matching the "log in once, reuse for the session" notebook model.
    calls = []
    engine = make_engine(_sqlite_factory(calls), dialect="sqlite")

    with engine.begin() as conn:
        conn.exec_driver_sql("create table t (x int)")
    with engine.connect() as conn:
        pd.read_sql_query("select * from t", conn)
        pd.read_sql_query("select * from t", conn)

    assert len(calls) == 1


def test_register_requires_an_ipython_session():
    engine = make_engine(_sqlite_factory([]), dialect="sqlite")
    with pytest.raises(RuntimeError):
        register(engine)


def test_register_wires_up_sql_magic_end_to_end():
    ipython_testing = pytest.importorskip("IPython.testing.globalipapp")
    shell = ipython_testing.get_ipython()

    engine = make_engine(_sqlite_factory([]), dialect="sqlite")
    register(engine, alias="test_conn")

    shell.run_cell("%%sql\ncreate table t (x int)")
    shell.run_cell("%%sql\ninsert into t values (1), (2)")
    result = shell.run_cell("%sql select * from t order by x")

    assert list(result.result.DataFrame()["x"]) == [1, 2]
