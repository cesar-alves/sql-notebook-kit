"""Lazy constructors for SQL Notebook Kit's built-in database adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sql_notebook_kit.adapters.base import (
    BackendCapabilities,
    BackendName,
    BuiltinAdapter,
    frozen_values,
)
from sql_notebook_kit.connectors import DBAPIConnection, FactorySpec
from sql_notebook_kit.errors import ConfigurationError, MissingOptionalDependencyError


def _required(values: Mapping[str, Any], *names: str) -> None:
    missing = [name for name in names if not values.get(name)]
    if missing:
        raise ConfigurationError("missing required connection option(s): " + ", ".join(missing))


def _open_transform_session(session_type: Any, creator: Any, **kwargs: Any) -> object:
    """Close a new transform connection if SQLFrame construction fails."""
    connection = creator()
    try:
        return session_type(conn=connection, **kwargs)
    except BaseException:
        connection.close()
        raise


def _redshift_adapter(values: Mapping[str, Any]) -> BuiltinAdapter:
    custom_factory = values.get("factory")
    custom_kwargs = values.get("factory_kwargs", {})
    if custom_factory is None and "factory_kwargs" in values:
        raise ConfigurationError("Redshift factory_kwargs requires factory")
    if custom_factory is not None:
        if not isinstance(custom_kwargs, Mapping):
            raise ConfigurationError("Redshift factory_kwargs must be a mapping")
        creator = FactorySpec(
            factory=custom_factory,
            dialect="redshift+redshift_connector",
            kwargs=custom_kwargs,
            name="redshift",
        ).bind()
    else:
        options = dict(values)

        def creator() -> DBAPIConnection:
            try:
                import redshift_connector
            except ImportError as exc:
                raise MissingOptionalDependencyError(
                    "Redshift requires 'sql-notebook-kit[redshift]'"
                ) from exc
            return redshift_connector.connect(**options)

    def transform() -> object:
        try:
            from sqlframe.redshift import RedshiftSession
        except ImportError as exc:
            raise MissingOptionalDependencyError(
                "Redshift transformations require 'sql-notebook-kit[redshift]'"
            ) from exc
        return _open_transform_session(RedshiftSession, creator)

    return BuiltinAdapter(
        "redshift",
        "redshift+redshift_connector",
        BackendCapabilities("redshift", "preview", True, True, True, True, "redshift"),
        creator,
        transform,
    )


def _duckdb_adapter(values: Mapping[str, Any]) -> BuiltinAdapter:
    allowed = {"database", "read_only", "config"}
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ConfigurationError("unsupported DuckDB option(s): " + ", ".join(unknown))
    database = values.get("database", ":memory:")
    read_only = values.get("read_only", False)
    config = values.get("config", {})
    if not isinstance(database, str) or not database:
        raise ConfigurationError("DuckDB database must be a non-empty string")
    if not isinstance(read_only, bool) or not isinstance(config, Mapping):
        raise ConfigurationError("DuckDB read_only/config options have invalid types")

    def raw_creator() -> DBAPIConnection:
        try:
            import duckdb
        except ImportError as exc:
            raise MissingOptionalDependencyError(
                "DuckDB requires 'sql-notebook-kit[duckdb]'"
            ) from exc
        return duckdb.connect(database=database, read_only=read_only, config=dict(config))

    def creator() -> DBAPIConnection:
        try:
            from duckdb_engine import ConnectionWrapper
        except ImportError as exc:
            raise MissingOptionalDependencyError(
                "DuckDB requires 'sql-notebook-kit[duckdb]'"
            ) from exc
        return ConnectionWrapper(raw_creator())

    def transform() -> object:
        try:
            from sqlframe.duckdb import DuckDBSession
        except ImportError as exc:
            raise MissingOptionalDependencyError(
                "DuckDB transformations require 'sql-notebook-kit[duckdb]'"
            ) from exc
        return _open_transform_session(DuckDBSession, raw_creator)

    return BuiltinAdapter(
        "duckdb",
        "duckdb",
        BackendCapabilities("duckdb", "certified", True, True, True, True, "duckdb"),
        creator,
        transform,
    )


def _databricks_adapter(values: Mapping[str, Any]) -> BuiltinAdapter:
    options = dict(values)
    compute_type = options.pop("compute_type", "sql_warehouse")
    if compute_type == "jobs":
        raise ConfigurationError("Databricks jobs compute is not supported")
    if compute_type not in {"sql_warehouse", "all_purpose"}:
        raise ConfigurationError("Databricks compute_type must be sql_warehouse or all_purpose")
    _required(options, "server_hostname", "http_path")

    def creator() -> DBAPIConnection:
        try:
            from databricks import sql
        except ImportError as exc:
            raise MissingOptionalDependencyError(
                "Databricks requires 'sql-notebook-kit[databricks]'"
            ) from exc
        return sql.connect(**options)

    def transform() -> object:
        try:
            from sqlframe.databricks import DatabricksSession
        except ImportError as exc:
            raise MissingOptionalDependencyError(
                "Databricks transformations require 'sql-notebook-kit[databricks]'"
            ) from exc
        return _open_transform_session(DatabricksSession, creator)

    return BuiltinAdapter(
        "databricks",
        "databricks",
        BackendCapabilities("databricks", "preview", False, False, True, True, "databricks"),
        creator,
        transform,
    )


def _bigquery_adapter(values: Mapping[str, Any]) -> BuiltinAdapter:
    options = dict(values)
    project = options.pop("project_id", None)
    dataset = options.pop("dataset_id", None)
    location = options.pop("location", None)
    credentials = options.pop("credentials", None)
    if options:
        raise ConfigurationError("unsupported BigQuery option(s): " + ", ".join(sorted(options)))

    def creator() -> DBAPIConnection:
        try:
            from google.cloud import bigquery
            from google.cloud.bigquery.dbapi import connect
        except ImportError as exc:
            raise MissingOptionalDependencyError(
                "BigQuery requires 'sql-notebook-kit[bigquery]'"
            ) from exc
        client = bigquery.Client(project=project, location=location, credentials=credentials)
        return connect(client=client)

    def transform() -> object:
        try:
            from sqlframe.bigquery import BigQuerySession
        except ImportError as exc:
            raise MissingOptionalDependencyError(
                "BigQuery transformations require 'sql-notebook-kit[bigquery]'"
            ) from exc
        default_dataset = f"{project}.{dataset}" if project and dataset else dataset
        return _open_transform_session(
            BigQuerySession, creator, default_dataset=default_dataset
        )

    return BuiltinAdapter(
        "bigquery",
        "bigquery",
        BackendCapabilities("bigquery", "preview", False, False, True, True, "bigquery"),
        creator,
        transform,
    )


def create_builtin_adapter(
    backend: BackendName, connection_kwargs: Mapping[str, Any] | None = None
) -> BuiltinAdapter:
    """Validate configuration and construct a connection-free built-in adapter."""
    values = frozen_values(connection_kwargs)
    constructors = {
        "redshift": _redshift_adapter,
        "duckdb": _duckdb_adapter,
        "databricks": _databricks_adapter,
        "bigquery": _bigquery_adapter,
    }
    try:
        constructor = constructors[backend]
    except KeyError as exc:
        raise ConfigurationError(f"unsupported backend: {backend!r}") from exc
    return constructor(values)
