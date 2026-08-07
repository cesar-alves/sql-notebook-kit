import builtins
import sqlite3

import pandas as pd
import pytest

from sql_notebook_kit.engine import make_engine, register
from sql_notebook_kit.errors import SQLExecutionError
from sql_notebook_kit.notebook import (
    _is_database_execution_error,
    _rewrite_standalone_percent_sql,
    _sql_error_summary,
    _visualization_available,
)
from sql_notebook_kit.results import NotebookResult
from sql_notebook_kit.session import create_session


def _sqlite_factory(calls):
    def factory():
        calls.append(1)
        return sqlite3.connect(":memory:")

    return factory


class _PoisoningCursor:
    def __init__(self, owner, cursor):
        self._owner = owner
        self._cursor = cursor

    def execute(self, sql, *args, **kwargs):
        if self._owner.poisoned:
            raise sqlite3.OperationalError(
                "current transaction is aborted, commands ignored until end of transaction block"
            )
        try:
            return self._cursor.execute(sql, *args, **kwargs)
        except sqlite3.Error:
            self._owner.poisoned = True
            raise

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _PoisoningConnection:
    def __init__(self, *, fail_recovery=False):
        self._connection = sqlite3.connect(":memory:")
        self.fail_recovery = fail_recovery
        self.poisoned = False
        self.rollback_calls = 0

    def cursor(self, *args, **kwargs):
        return _PoisoningCursor(self, self._connection.cursor(*args, **kwargs))

    def rollback(self):
        self.rollback_calls += 1
        if self.poisoned and self.fail_recovery:
            raise sqlite3.OperationalError("rollback failed")
        self.poisoned = False
        return self._connection.rollback()

    def __getattr__(self, name):
        return getattr(self._connection, name)


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


def test_visualization_availability_requires_nbformat(monkeypatch):
    original_import = builtins.__import__

    def import_without_nbformat(name, *args, **kwargs):
        if name == "nbformat":
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_nbformat)
    assert _visualization_available() is False


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


def test_session_wraps_line_magic_results_and_standalone_percent_sql_cells():
    ipython_testing = pytest.importorskip("IPython.testing.globalipapp")
    shell = ipython_testing.get_ipython()
    session = create_session(factory=lambda: sqlite3.connect(":memory:"), dialect="sqlite")
    session.register(alias="both_magics", visualization=True, max_rows=1)

    line = shell.run_cell("%sql select 1 as x union all select 2 order by x")
    multiline = shell.run_cell("%sql\nselect 3 as x union all select 4 order by x")

    assert isinstance(line.result, NotebookResult)
    assert line.result.dataframe["x"].tolist() == [1]
    assert line.result.truncated is True
    assert isinstance(multiline.result, NotebookResult)
    assert multiline.result.dataframe["x"].tolist() == [3]
    assert multiline.result.truncated is True
    session.dispose()


def test_standalone_percent_sql_transform_is_narrow_and_idempotent():
    transformed = _rewrite_standalone_percent_sql(["%sql\n", "select 1\n"])
    assert transformed == ["%%sql\n", "select 1\n"]
    assert _rewrite_standalone_percent_sql(transformed) == transformed
    assert _rewrite_standalone_percent_sql(["%sql select 1\n", "value = 2\n"]) == [
        "%sql select 1\n",
        "value = 2\n",
    ]


@pytest.mark.parametrize("visualization", [False, True])
def test_failed_sql_cell_rolls_back_before_the_next_cell(visualization):
    ipython_testing = pytest.importorskip("IPython.testing.globalipapp")
    shell = ipython_testing.get_ipython()
    connection = _PoisoningConnection()
    session = create_session(factory=lambda: connection, dialect="sqlite")
    alias = f"recovery_{visualization}"
    session.register(alias=alias, visualization=visualization, max_rows=1)
    rollback_calls_before_error = connection.rollback_calls

    with pytest.raises(SQLExecutionError, match="missing_table"):
        shell.run_cell_magic("sql", "", "select * from missing_table")

    assert connection.rollback_calls == rollback_calls_before_error + 1
    assert connection.poisoned is False
    result = shell.run_cell_magic(
        "sql", "", "select 1 as value union all select 2 order by value"
    )
    frame = result.dataframe if isinstance(result, NotebookResult) else result.DataFrame()
    assert frame["value"].tolist() == ([1] if visualization else [1, 2])
    session.dispose()


def test_non_database_errors_do_not_trigger_sql_recovery():
    assert _is_database_execution_error(ValueError("not a database error")) is False


def test_redshift_error_summary_uses_driver_message_and_sqlstate():
    driver_error = RuntimeError({"M": "column does not exist", "C": "42703", "P": "8"})
    wrapped = __import__("sqlalchemy").exc.DBAPIError.instance(
        "select missing", {}, driver_error, RuntimeError
    )
    assert _sql_error_summary(wrapped) == "column does not exist (SQLSTATE 42703)"


def test_rollback_failure_warns_without_replacing_the_sql_error():
    ipython_testing = pytest.importorskip("IPython.testing.globalipapp")
    shell = ipython_testing.get_ipython()
    connection = _PoisoningConnection(fail_recovery=True)
    session = create_session(factory=lambda: connection, dialect="sqlite")
    session.register(alias="failed_recovery", visualization=False)

    with (
        pytest.warns(UserWarning, match=r"could not roll back.*session\.reconnect"),
        pytest.raises(SQLExecutionError, match="missing_table"),
    ):
        shell.run_cell_magic("sql", "", "select * from missing_table")

    connection.fail_recovery = False
    session.dispose()
