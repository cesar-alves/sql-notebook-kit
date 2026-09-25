from __future__ import annotations

import re
import sys
import types

import pytest

from sql_notebook_kit import BackendCapabilities, SQLNotebookKitError, create_session
from sql_notebook_kit.adapters import create_builtin_adapter
from sql_notebook_kit.adapters.builtins import _open_transform_session
from sql_notebook_kit.errors import ConfigurationError, MissingOptionalDependencyError


def test_public_capability_type_is_immutable():
    value = BackendCapabilities("duckdb", "certified", True, True, True, True, "duckdb")
    with pytest.raises(AttributeError):
        value.backend = "other"  # type: ignore[misc]


def test_duckdb_adapter_is_connection_free_until_factory_call(monkeypatch):
    calls: list[dict[str, object]] = []
    module = types.ModuleType("duckdb")
    module.connect = lambda **kwargs: calls.append(kwargs) or object()
    wrapper_module = types.ModuleType("duckdb_engine")
    wrapper_module.ConnectionWrapper = lambda connection: connection
    monkeypatch.setitem(sys.modules, "duckdb", module)
    monkeypatch.setitem(sys.modules, "duckdb_engine", wrapper_module)

    adapter = create_builtin_adapter("duckdb", {"database": "analytics.duckdb"})

    assert calls == []
    assert adapter.capabilities.support_level == "certified"
    adapter.connection_factory()
    assert calls == [{"database": "analytics.duckdb", "read_only": False, "config": {}}]


@pytest.mark.parametrize("backend", ["redshift", "databricks", "bigquery"])
def test_cloud_adapters_start_in_preview_without_connecting(backend):
    kwargs = {
        "redshift": {},
        "databricks": {"server_hostname": "<host>", "http_path": "<path>"},
        "bigquery": {"project_id": "<project>"},
    }[backend]
    adapter = create_builtin_adapter(backend, kwargs)
    assert adapter.capabilities.support_level == "preview"


@pytest.mark.parametrize(
    ("backend", "kwargs", "module", "extra"),
    [
        ("duckdb", {}, "duckdb_engine", "[duckdb]"),
        ("redshift", {}, "redshift_connector", "[redshift]"),
        (
            "databricks",
            {"server_hostname": "<host>", "http_path": "<path>"},
            "databricks",
            "[databricks]",
        ),
        ("bigquery", {"project_id": "<project>"}, "google.cloud", "[bigquery]"),
    ],
)
def test_every_builtin_has_actionable_optional_dependency_failure(
    monkeypatch, backend, kwargs, module, extra
):
    monkeypatch.setitem(sys.modules, module, None)
    adapter = create_builtin_adapter(backend, kwargs)
    with pytest.raises(MissingOptionalDependencyError, match=re.escape(extra)):
        adapter.connection_factory()


def test_builtin_adapter_repr_never_exposes_connection_values():
    secret = "usable-secret-value"
    adapter = create_builtin_adapter(
        "databricks",
        {"server_hostname": "<host>", "http_path": "<path>", "access_token": secret},
    )
    assert secret not in repr(adapter)
    assert secret not in repr(adapter.factory_spec)


def test_failed_transform_construction_closes_the_new_connection():
    class Connection:
        closed = False

        def close(self):
            self.closed = True

    connection = Connection()

    class BrokenSession:
        def __init__(self, **_kwargs):
            raise RuntimeError("construction failed")

    with pytest.raises(RuntimeError, match="construction failed"):
        _open_transform_session(BrokenSession, lambda: connection)
    assert connection.closed


def test_databricks_rejects_jobs_compute():
    with pytest.raises(ConfigurationError, match="jobs compute"):
        create_builtin_adapter(
            "databricks",
            {"server_hostname": "<host>", "http_path": "<path>", "compute_type": "jobs"},
        )


def test_session_input_paths_are_mutually_exclusive():
    with pytest.raises(ConfigurationError, match="cannot be combined"):
        create_session(backend="duckdb", factory=lambda: object(), dialect="sqlite")
    with pytest.raises(ConfigurationError, match="connection_kwargs requires"):
        create_session(
            factory=lambda: object(), dialect="sqlite", connection_kwargs={"database": ":memory:"}
        )
    with pytest.raises(ConfigurationError, match="choose backend"):
        create_session()


def test_custom_adapter_is_best_effort():
    session = create_session(factory=lambda: object(), dialect="sqlite")
    assert session.adapter.capabilities.support_level == "best_effort"
    assert session.adapter.capabilities.backend == "custom"


def test_neutral_error_base_is_public():
    assert issubclass(ConfigurationError, SQLNotebookKitError)


def test_duckdb_builtin_eager_and_lazy_channels_are_separate(tmp_path):
    database = tmp_path / "analytics.duckdb"
    session = create_session(
        backend="duckdb", connection_kwargs={"database": str(database)}
    )
    with session.engine.begin() as connection:
        connection.exec_driver_sql("create table sales(region varchar, amount integer)")
        connection.exec_driver_sql("insert into sales values ('west', 4), ('east', 7)")

    result = session.sql("select region, amount from sales order by amount").collect(max_rows=1)

    assert result.dataframe.to_dict("records") == [{"region": "west", "amount": 4}]
    assert result.truncated is True
    assert session._transform_session is not None
    session.dispose()
