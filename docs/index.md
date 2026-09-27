# sql-notebook-kit

> **Alpha software:** 0.1.0 is an API-unstable alpha. Advertised behavior may change before
> 1.0, with breaking changes documented under the project versioning policy.

`sql-notebook-kit` provides portable SQL cells, bounded results, lazy SQLFrame
transformations, and editable visualizations across JupyterLab and VS Code.
Use a built-in backend or provide a synchronous DBAPI factory.

## Install

```bash
uv pip install 'sql-notebook-kit[duckdb,viz]==0.1.0'
```

## Minimal setup

```python
from sql_notebook_kit import create_session
session = create_session(
    backend="duckdb",
    connection_kwargs={"database": "analytics.duckdb"},
)
session.register()
```

No physical connection opens during import or session construction. Built-in
Redshift, DuckDB, Databricks, and BigQuery adapters share the same eager and
lazy notebook contracts, with capability differences recorded explicitly.

Read the [backend guide](backends.md), [compatibility matrix](compatibility.md),
and [factory contract](factory-contract.md) for integration details. DuckDB is the
only certified 0.1.0 backend. Redshift, Databricks, and BigQuery are preview backends;
custom synchronous DBAPI factories are best effort. Browser-only `vscode.dev` is not
supported.
