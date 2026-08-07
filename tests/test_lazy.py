import sqlite3

import pandas as pd
import pytest

from sql_notebook_kit import LazyQuery, create_session
from sql_notebook_kit.errors import (
    ConfigurationError,
    LazyQueryError,
    SQLExecutionError,
    StaleLazyQueryError,
)
from sql_notebook_kit.lazy import validate_relation_query
from sql_notebook_kit.results import NotebookResult


class _FakeDataFrame:
    def __init__(self, session, frame=None):
        self.session = session
        self.frame = frame if frame is not None else pd.DataFrame({"value": [1, 2, 3]})
        self.limit_value = None
        self.optimize = None

    def sql(self, *, optimize=False):
        self.optimize = optimize
        return "SELECT value FROM source"

    def limit(self, value):
        limited = _FakeDataFrame(self.session, self.frame.head(value))
        limited.limit_value = value
        self.session.last_limited = limited
        return limited

    def toPandas(self):
        return self.frame.copy()


class _FakeTransformSession:
    def __init__(self):
        self.sql_calls = []
        self.stop_calls = 0
        self.last_limited = None

    def sql(self, query):
        self.sql_calls.append(query)
        return _FakeDataFrame(self)

    def stop(self):
        self.stop_calls += 1


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("select 1", None),
        ("select ':literal' as value", None),
        ("select value::integer from values_table", None),
        ("with values_cte as (select 1 as value) select * from values_cte", None),
        ("select 1; select 2", "only one SQL statement"),
        ("create table values_table (value int)", "only relation-producing SELECT"),
        ("insert into values_table values (1)", "only relation-producing SELECT"),
        ("select * from values_table where value > :minimum", "unresolved bind parameters"),
    ],
)
def test_relation_query_validation(query, reason):
    result = validate_relation_query(query)
    if reason is None:
        assert result is None
    else:
        assert reason in result


def test_lazy_query_is_source_only_bounded_and_sanitized():
    transform = _FakeTransformSession()
    factory_calls = []

    def transform_factory():
        factory_calls.append(1)
        return transform

    session = create_session(
        factory=lambda: sqlite3.connect(":memory:"),
        dialect="sqlite",
        transform_session_factory=transform_factory,
    )
    query = session.sql("select secret_column from private_table")

    assert isinstance(query, LazyQuery)
    assert factory_calls == []
    assert "secret_column" not in repr(query)
    assert query.compile() == "SELECT value FROM source"
    assert factory_calls == [1]
    assert transform.sql_calls == ["select secret_column from private_table"]

    transformed = query.apply(lambda frame: _FakeDataFrame(frame.session))
    assert transformed is not query
    result = transformed.collect(max_rows=2)
    assert result.dataframe["value"].tolist() == [1, 2]
    assert result.truncated is True
    assert transform.last_limited.limit_value == 3
    session.dispose()
    assert transform.stop_calls == 1


def test_lazy_query_rejects_wrong_return_and_cross_session_dataframe():
    first_transform = _FakeTransformSession()
    second_transform = _FakeTransformSession()
    session = create_session(
        factory=lambda: sqlite3.connect(":memory:"),
        dialect="sqlite",
        transform_session_factory=lambda: first_transform,
    )
    query = session.sql("select 1")

    with pytest.raises(LazyQueryError, match="must return"):
        query.apply(lambda _frame: object())
    with pytest.raises(LazyQueryError, match="different transform session"):
        query.apply(lambda _frame: _FakeDataFrame(second_transform))
    session.dispose()


def test_lazy_query_limits_and_transform_factory_failures_are_actionable():
    session = create_session(
        factory=lambda: sqlite3.connect(":memory:"),
        dialect="sqlite",
        transform_session_factory=lambda: (_ for _ in ()).throw(
            RuntimeError("sensitive factory detail")
        ),
    )
    query = session.sql("select 1")

    with pytest.raises(ConfigurationError, match="max_rows must be positive"):
        query.collect(max_rows=0)
    with pytest.raises(ConfigurationError, match="allow_large_results"):
        query.collect(max_rows=100_001)
    with pytest.raises(LazyQueryError, match="RuntimeError") as captured:
        query.compile()
    assert "sensitive factory detail" not in str(captured.value)
    session.dispose()


def test_dispose_is_idempotent_for_the_transform_channel():
    transform = _FakeTransformSession()
    session = create_session(
        factory=lambda: sqlite3.connect(":memory:"),
        dialect="sqlite",
        transform_session_factory=lambda: transform,
    )
    session.sql("select 1").compile()

    session.dispose()
    session.dispose()

    assert transform.stop_calls == 1


def test_reconnect_invalidates_existing_lazy_handles():
    transform = _FakeTransformSession()
    session = create_session(
        factory=lambda: sqlite3.connect(":memory:"),
        dialect="sqlite",
        transform_session_factory=lambda: transform,
    )
    query = session.sql("select 1")
    query.compile()

    session.reconnect(login=False)

    assert transform.stop_calls == 1
    with pytest.raises(StaleLazyQueryError, match="rerun its SQL cell"):
        query.compile()
    session.dispose()


def test_transform_session_cannot_be_shared_between_notebook_sessions():
    shared = _FakeTransformSession()
    second_factory_calls = []
    first = create_session(
        factory=lambda: sqlite3.connect(":memory:"),
        dialect="sqlite",
        transform_session_factory=lambda: shared,
    )
    second = create_session(
        factory=lambda: sqlite3.connect(":memory:"),
        dialect="sqlite",
        transform_session_factory=lambda: (second_factory_calls.append(1), shared)[1],
    )
    first.sql("select 1").compile()

    with pytest.raises(ConfigurationError, match="already owned"):
        second.sql("select 1").compile()
    assert second_factory_calls == []

    first.dispose()
    second.dispose()


def test_sql_cells_assign_df_without_opening_transform_session():
    ipython_testing = pytest.importorskip("IPython.testing.globalipapp")
    shell = ipython_testing.get_ipython()
    shell.user_ns.pop("_df", None)
    transform = _FakeTransformSession()
    transform_calls = []

    def transform_factory():
        transform_calls.append(1)
        return transform

    session = create_session(
        factory=lambda: sqlite3.connect(":memory:"),
        dialect="sqlite",
        transform_session_factory=transform_factory,
    )
    session.register(alias="lazy_assignment", visualization=False, max_rows=2)
    shell.run_cell("%%sql\ncreate table lazy_values (value int)")
    shell.run_cell("%%sql\ninsert into lazy_values values (1), (2), (3)")

    multiline = shell.run_cell("%sql\nselect * from lazy_values order by value")

    assert isinstance(multiline.result, NotebookResult)
    assert multiline.result.truncated is True
    assert isinstance(shell.user_ns["_df"], LazyQuery)
    assert transform_calls == []
    assert "Available as _df" in multiline.result.lazy_notice
    first_df = shell.user_ns["_df"]

    line = shell.run_cell("%sql select value + 1 as value from lazy_values")
    assert isinstance(line.result, NotebookResult)
    assert shell.user_ns["_df"] is not first_df

    before_empty = shell.user_ns["_df"]
    empty = shell.run_cell("%sql select * from lazy_values where 1 = 0")
    assert empty.result.dataframe.empty
    assert shell.user_ns["_df"] is not before_empty
    assert "Available as _df" in empty.result.lazy_notice

    shell.user_ns["minimum"] = 1
    shell.run_line_magic("config", "SqlMagic.named_parameters='enabled'")
    current_df = shell.user_ns["_df"]
    parameterized = shell.run_cell("%sql select * from lazy_values where value > :minimum")
    assert shell.user_ns["_df"] is current_df
    assert "unresolved bind parameters" in parameterized.result.lazy_notice

    multiple = shell.run_cell("%sql select 1 as value; select 2 as value")
    assert shell.user_ns["_df"] is current_df
    assert "only one SQL statement" in multiple.result.lazy_notice

    with pytest.raises(SQLExecutionError):
        shell.run_cell_magic("sql", "", "select * from missing_lazy_table")
    assert shell.user_ns["_df"] is current_df
    session.dispose()


def test_templated_sql_result_preserves_previous_df():
    ipython_testing = pytest.importorskip("IPython.testing.globalipapp")
    shell = ipython_testing.get_ipython()
    transform = _FakeTransformSession()
    session = create_session(
        factory=lambda: sqlite3.connect(":memory:"),
        dialect="sqlite",
        transform_session_factory=lambda: transform,
    )
    session.register(alias="lazy_template", visualization=False)
    shell.run_cell("%sql select 1 as value")
    previous = shell.user_ns["_df"]
    shell.user_ns["selected_value"] = 2

    result = shell.run_cell_magic("sql", "", "select {{ selected_value }} as value")

    assert shell.user_ns["_df"] is previous
    assert "templated SQL" in result.lazy_notice
    session.dispose()


def test_lazy_disclosure_is_escaped_and_rendered_in_the_workspace():
    from sql_notebook_kit.visualize.workspace import (
        WORKSPACE_CSS,
        VisualizationWorkspace,
    )

    result = NotebookResult(
        pd.DataFrame({"value": [1]}),
        raw=None,
        lazy_notice="Available as <_df> & safe",
    )
    html = result._repr_html_()
    workspace = VisualizationWorkspace(result)

    assert "Available as &lt;_df&gt; &amp; safe" in html
    assert "Available as &lt;_df&gt; &amp; safe" in workspace.lazy_notice.value
    assert "<em>" in workspace.lazy_notice.value
    assert ".snk-lazy-notice" in WORKSPACE_CSS
    assert "font-size: 0.8rem" in WORKSPACE_CSS


def test_duckdb_lazy_transformations_use_a_separate_file_backed_connection(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    duckdb_engine = pytest.importorskip("duckdb_engine")
    sqlframe_duckdb = pytest.importorskip("sqlframe.duckdb")
    functions = pytest.importorskip("sqlframe.duckdb.functions")
    database = tmp_path / "lazy.duckdb"
    setup = duckdb.connect(str(database))
    setup.execute("create table sales(region varchar, amount integer)")
    setup.execute("insert into sales values ('north', 10), ('north', 20), ('south', 5)")
    setup.close()
    eager_connections = []
    transform_connections = []

    def eager_factory():
        connection = duckdb.connect(str(database))
        eager_connections.append(connection)
        return duckdb_engine.ConnectionWrapper(connection)

    def transform_factory():
        connection = duckdb.connect(str(database))
        transform_connections.append(connection)
        return sqlframe_duckdb.DuckDBSession(conn=connection)

    session = create_session(
        factory=eager_factory,
        dialect="duckdb",
        transform_session_factory=transform_factory,
    )
    with session.engine.connect() as connection:
        assert connection.exec_driver_sql("select count(*) from sales").scalar_one() == 3
    query = session.sql("select region, amount from sales")
    summary = query.apply(
        lambda frame: frame.where(functions.col("amount") > 0)
        .groupBy("region")
        .agg(functions.sum("amount").alias("revenue"))
        .orderBy(functions.col("revenue").desc())
    )

    assert len(eager_connections) == 1
    compiled = summary.compile()
    assert "SUM" in compiled.upper()
    result = summary.collect(max_rows=1)
    assert result.dataframe["region"].tolist() == ["north"]
    assert result.dataframe["revenue"].tolist() == [30]
    assert result.truncated is True
    assert len(transform_connections) == 1
    assert transform_connections[0] is not eager_connections[0]
    session.dispose()


def test_separate_in_memory_duckdb_connections_do_not_share_tables():
    duckdb = pytest.importorskip("duckdb")
    duckdb_engine = pytest.importorskip("duckdb_engine")
    sqlframe_duckdb = pytest.importorskip("sqlframe.duckdb")
    session = create_session(
        factory=lambda: duckdb_engine.ConnectionWrapper(duckdb.connect(":memory:")),
        dialect="duckdb",
        transform_session_factory=lambda: sqlframe_duckdb.DuckDBSession(
            conn=duckdb.connect(":memory:")
        ),
    )
    with session.engine.begin() as connection:
        connection.exec_driver_sql("create table eager_only(value integer)")
        connection.exec_driver_sql("insert into eager_only values (1)")

    with pytest.raises(LazyQueryError):
        session.sql("select * from eager_only").collect()
    session.dispose()
