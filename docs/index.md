# sql-notebook-kit

`sql-notebook-kit` provides portable SQL cells, bounded results, lazy SQLFrame
transformations, and editable visualizations across JupyterLab and VS Code.
Use a built-in backend or provide a synchronous DBAPI factory.

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
and [factory contract](factory-contract.md) for integration details.
