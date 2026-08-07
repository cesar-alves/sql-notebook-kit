# Lazy SQL-to-Python transformations

An eligible managed SQL result is also exposed as `_df` when the session has a
`transform_session_factory`. `_df` is a `LazyQuery`, not the bounded pandas
DataFrame shown in the output and not SQLFrame's native DataFrame.

```python
from redshift_notebooks import create_session

session = create_session(
    factory=<eager-dbapi-factory>,
    dialect="<sqlalchemy-dialect>",
    transform_session_factory=<sqlframe-session-factory>,
)
session.register()
```

The transform factory must synchronously return a new SQLFrame-compatible
session with `sql()` and `stop()` methods. It is not called during session
construction, registration, or SQL-cell execution. The first access to
`_df.native`, `apply()`, `compile()`, `collect()`, or `visualize()` creates the
separate transform connection.

## From SQL to Python

Run one relation-producing statement:

```sql
%sql
select region, amount from analytics.sales
```

The result footer reports that `_df` is available and that acting on it reruns
the query through the transform connection. Transform it with SQLFrame:

```python
from sqlframe.base import functions as F

summary = _df.apply(
    lambda frame: (
        frame.where(F.col("amount") > 0)
        .groupBy("region")
        .agg(F.sum("amount").alias("revenue"))
        .orderBy(F.col("revenue").desc())
    )
)

summary.compile()
result = summary.collect(max_rows=1_000)
result.visualize()
```

`compile()` does not execute the generated relation query. `collect()` and
`visualize()` add an outer `LIMIT max_rows + 1`; the extra row detects
truncation and is discarded. A limit controls transferred rows, not the bytes
scanned or compute required by inner filters, joins, aggregations, and sorts.
Limits above 100,000 require `allow_large_results=True`.

Each eligible SQL result replaces `_df`. Assign it to another Python name
before running a later SQL cell when the older plan must remain available.
DDL, DML, failed statements, multiple statements, templated SQL, and queries
with unresolved bind parameters leave the previous `_df` unchanged. The result
footer explains why a successful relation was not assigned.

## Connection isolation

The eager JupySQL/SQLAlchemy channel and lazy SQLFrame channel use distinct
physical connections. Persistent tables are normally visible to both, but
uncommitted writes, temporary tables, session variables, and connection-local
settings are not guaranteed to cross the boundary. Acting on `_df` executes
the source `SELECT` again; it never transforms the bounded local preview.

`session.reconnect()` and `session.dispose()` stop the transform session and
invalidate existing `LazyQuery` objects. Rerun the originating SQL cell before
using `_df` again. SQLFrame 4.3 supplies a process-level session singleton, so
the package permits one active transform channel per Python process and rejects
a second live owner before invoking its factory.

## DuckDB reference setup

Install `redshift-notebooks[duckdb]` and use a file-backed database so the two
connections can see the same persistent catalog:

```python
import duckdb
from duckdb_engine import ConnectionWrapper
from sqlframe.duckdb import DuckDBSession

database = "analytics.duckdb"

session = create_session(
    factory=lambda: ConnectionWrapper(duckdb.connect(database)),
    dialect="duckdb",
    transform_session_factory=lambda: DuckDBSession(
        conn=duckdb.connect(database)
    ),
)
```

Two independent `:memory:` DuckDB connections do not share their tables.
