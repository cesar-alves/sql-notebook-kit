# redshift_notebooks

SQL-cell notebooks for Redshift: run `%%sql` cells directly against Redshift
from a Jupyter/VS Code notebook and get the result rendered as a table, closer
to the [Databricks notebook](https://docs.databricks.com/aws/en/visualizations/)
experience than the current `conn.execute(query).fetch_dataframe()`-per-cell
pattern.

Built on [jupysql](https://github.com/ploomber/jupysql) (`%sql`/`%%sql` IPython
magics) + a SQLAlchemy `Engine`. The core is **connection-agnostic** — it wraps
*any* zero-arg callable that returns a DBAPI connection, not just Redshift or
any single SSO flow — so it's structured to be open-sourceable independently of
project-specific auth. This package is a **standalone, temporary setup** at
`main/src/redshift_notebooks`: it is not wired into the root `uv` workspace, so
install it into its own environment (see below) rather than expecting `uv sync`
at the repo root to pick it up.

## Why not just pass a connection string?

Some connection setups don't reduce to a `user:password@host` string at all —
for example, a Redshift connection (`your_dbt_pkg.redshift.get_connection`)
authenticates via a multi-step Azure AD SSO → SAML → AWS STS →
`GetClusterCredentials` flow and returns a live `redshift_connector.Connection`
object directly. jupysql, however, is built around a SQLAlchemy `Engine`. The
bridge is SQLAlchemy's `creator=` hook: instead of building a connection from a
URL, `create_engine` calls an arbitrary factory function to obtain the DBAPI
connection, so whatever auth dance a project needs runs exactly as it would
standalone, just wrapped so jupysql can drive it.

## Install

Standalone package — not installed by the repo's root `uv sync`:

```bash
cd main/src/redshift_notebooks
uv venv
uv pip install -e .
```

Point your notebook's kernel at this `.venv` (VS Code kernel picker,
top-right).

## Quickstart

```python
import redshift_notebooks
from redshift_notebooks.adapters.config import get_configured_engine

engine = get_configured_engine()
redshift_notebooks.register(engine)  # %load_ext sql + %sql engine, done once
```

```sql
%%sql
select current_user, current_database()
```

See [`examples/quickstart.ipynb`](examples/quickstart.ipynb) for a runnable
end-to-end version, including converting a result back to a pandas DataFrame
with `.DataFrame()`.

## Configuring a connection

`redshift_notebooks.adapters.config` is the only adapter shipped in this
library, and it's project-agnostic: it builds an Engine from *any* connection
factory, named entirely through config — the library never hard-imports a
particular project's connection package.

`get_configured_engine(factory=None, kwargs=None, table="connection", dialect=...)`
resolves `factory`/`kwargs` in this order — first match wins:

| Priority | Mechanism |
|---|---|
| 1 | Explicit function argument (`factory`, `kwargs`) |
| 2 | Environment variable (`REDSHIFT_NOTEBOOKS_FACTORY`; `REDSHIFT_NOTEBOOKS_KWARG_<NAME>` overrides individual `kwargs` entries) |
| 3 | `[connection]` table in a TOML config file (default `~/.config/redshift_notebooks/config.toml`, override the path with `REDSHIFT_NOTEBOOKS_CONFIG`) |

`factory` must resolve to a dotted `"module.path:callable_name"` string
identifying a callable that returns a DBAPI connection — it's imported lazily,
only when `get_configured_engine()` is called, so the caller's connection
package (e.g. `your-dbt-pkg`) only needs to be installed by whoever uses that
adapter, not by `redshift_notebooks` itself. `kwargs` is a dict of keyword
arguments passed to that callable.

Example config file, using an Azure-AD-SSO Redshift connection as the
factory:
```toml
[connection]
factory = "your_dbt_pkg.redshift:get_connection"

[connection.kwargs]
db_user = "your.name@example.com"
preferred_role = "arn:aws:iam::<account>:role/<role-name>"
```

This lets you call `get_configured_engine()` with no arguments once you've set
up a config file, instead of hardcoding connection details in every notebook.

## Bring your own connection

The core (`redshift_notebooks.engine.make_engine`) doesn't know about any
particular project or Redshift specifically — it just needs a callable that returns a DBAPI
connection:

```python
from redshift_notebooks.engine import make_engine

engine = make_engine(lambda: my_own_connect_function(), dialect="redshift+redshift_connector")
```

`dialect` defaults to `redshift+redshift_connector` (via
[`sqlalchemy-redshift`](https://github.com/sqlalchemy-redshift/sqlalchemy-redshift))
but works with any SQLAlchemy dialect string — plug in a different auth
mechanism (static IAM credentials, a different Redshift driver, even a
different warehouse entirely) without touching the rest of the library. This
is the seam that makes the library connection-agnostic, and lets it be
extracted and published independently of any single project's auth adapter.

## Roadmap: visualization module (not implemented)

Databricks notebooks auto-render `%%sql` results with a chart-builder UI
attached to the output — pick a chart type, x/y columns, aggregation, and it
renders inline, no code required (see
[Databricks visualizations docs](https://docs.databricks.com/aws/en/visualizations/)).
jupysql itself has no equivalent built-in (it focuses on query execution and
table rendering), and no existing plot-rendering module for this was found
elsewhere in the repo.

A rough design sketch for a future `redshift_notebooks.visualize` module,
**not built in this pass**:

- A `display(df)` (or `%sqlplot`-style magic) that renders a
  [Plotly Express](https://plotly.com/python/plotly-express/) figure from the
  last `%%sql` result or an arbitrary DataFrame.
- An [`ipywidgets`](https://ipywidgets.readthedocs.io/)-driven picker
  (dropdowns for chart type — bar/line/scatter/pie — and x/y/color columns)
  so the chart type can be changed interactively without re-running the query,
  mirroring Databricks' inline chart-builder.
- Auto-invoke after every `%%sql` cell (via an IPython post-run-cell hook) so
  a chart appears automatically under the table, opt-in/opt-out via a
  `redshift_notebooks.visualize.enable()/disable()` toggle rather than always-on.
- Sensible defaults for column-type inference (datetime → line chart x-axis,
  low-cardinality string → bar/pie categories, etc.) so most query results get
  a reasonable chart with zero configuration, same as Databricks' "auto"
  visualization type.

This would live in a new `redshift_notebooks/visualize.py` + an optional
`[project.optional-dependencies] viz = ["plotly", "ipywidgets"]` extra, kept
separate from the core so the base install stays lightweight for anyone who
only wants `%%sql` cells.
