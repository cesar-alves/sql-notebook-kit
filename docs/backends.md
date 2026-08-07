# Backends

SQL Notebook Kit provides typed built-in adapters and a best-effort custom
factory path. Session construction validates configuration without opening a
physical connection. Eager JupySQL and lazy SQLFrame execution use separate
connections and do not share transactions, temporary tables, or session variables.

## DuckDB

```python
session = create_session(
    backend="duckdb",
    connection_kwargs={"database": "analytics.duckdb", "read_only": False},
)
```

Use `:memory:` for an isolated in-memory database. SQL Notebook Kit never
installs or enables DuckDB extensions implicitly.

## Amazon Redshift

Use direct `redshift_connector.connect()` keyword arguments or bind a
company-owned synchronous SSO factory:

```python
session = create_session(
    backend="redshift",
    connection_kwargs={
        "factory": company_sso_factory,
        "factory_kwargs": {"db_user": "<user-email>"},
    },
)
```

Install `sql-notebook-kit[redshift]`. Redshift is the flagship cloud adapter,
but remains preview until its live release smoke gate passes.

## Databricks

```python
session = create_session(
    backend="databricks",
    connection_kwargs={
        "server_hostname": "<workspace-host>",
        "http_path": "<warehouse-http-path>",
        "auth_type": "databricks-oauth",
        "compute_type": "sql_warehouse",
    },
)
```

Install `sql-notebook-kit[databricks]`. Supported compute types are
`sql_warehouse` and `all_purpose`; jobs compute is rejected. Tokens and other
credentials must come from the secret channel rather than TOML.

## BigQuery

```python
session = create_session(
    backend="bigquery",
    connection_kwargs={
        "project_id": "<project-id>",
        "dataset_id": "<dataset-id>",
        "location": "EU",
    },
)
```

Install `sql-notebook-kit[bigquery]`. Application Default Credentials are
preferred; injected credential objects are accepted in code but never serialized.
BigQuery rollback is not advertised and a row limit does not guarantee fewer bytes scanned.

## Custom factory

Use `create_session(factory=..., dialect=...)` for a synchronous DBAPI creator.
Every invocation must return a distinct open connection. Lazy transformations
require an explicit SQLFrame-compatible `transform_session_factory`.
