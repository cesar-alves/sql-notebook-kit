# sql-notebook-kit

> **Alpha software:** 0.1.0 is an API-unstable alpha. Correctness, credential
> safety, and packaging are release requirements, but advertised Python APIs
> and notebook behavior may change before 1.0. Breaking changes are documented
> in the changelog and follow the [versioning policy](docs/versioning.md).

`sql-notebook-kit` brings portable SQL cells, bounded local results, lazy
warehouse transformations, and editable charts to JupyterLab and VS Code.
Built-in adapters cover DuckDB, Amazon Redshift, Databricks SQL, and BigQuery;
custom synchronous DBAPI factories remain available as a best-effort escape hatch.

The package never needs a password-bearing connection URL. Authentication runs
inside the supplied factory only when a physical connection is required.

## Install

```bash
uv pip install 'sql-notebook-kit[duckdb,viz]==0.1.0'
```

Use the resulting environment as the notebook kernel.
The base package installs `ipykernel` and `jupyter-client`, so a clean pip or uv
environment has the Python kernel runtime required by Jupyter and VS Code. The
`viz` extra remains required for Plotly and ipywidgets visualizations.

For VS Code, install the companion bundled in the same Python package and
reload the window. When using an editable source checkout, compile and stage
the VSIX first if it is missing or the frontend sources have changed:

```bash
pnpm install --frozen-lockfile
pnpm build
pnpm package:vscode
```

Published wheels already contain the compiled VSIX. Install it into the active
VS Code extension host with:

```bash
sql-notebook-kit vscode install
sql-notebook-kit vscode status
```

The installer detects `code`, `code-insiders`, and `codium`; use `--editor` or
`--cli /path/to/editor-cli` to override it. Run the command in the matching SSH,
WSL, or dev-container terminal for remote windows. Browser-only `vscode.dev` is
not supported, and the Microsoft Jupyter extension is required.

## DuckDB quickstart

Set `DUCK_DB_SOURCE` to an existing DuckDB database, install the DuckDB and
visualization extras in your notebook environment, and open the read-only
[DuckDB sample notebook](examples/duckdb.ipynb):

```bash
uv pip install 'sql-notebook-kit[duckdb,viz]==0.1.0'
export DUCK_DB_SOURCE=/absolute/path/to/analytics.duckdb
jupyter lab examples/duckdb.ipynb
```

The sample validates the connection, lists database tables, and exercises both
SQL cells and bounded lazy collection without modifying the source database.
For direct setup in another notebook, use the same environment variable:

```python
import os

from sql_notebook_kit import create_session

session = create_session(
    backend="duckdb",
    connection_kwargs={
        "database": os.environ["DUCK_DB_SOURCE"],
        "read_only": True,
    },
)
session.register(visualization=True)
```

DuckDB is the credential-free certified backend and exercises eager SQL,
SQLFrame transformations, bounded collection, and visualization on every pull
request. Calling `session.sql("select ...")` or using the automatic `_df`
handle remains lazy until an action is requested.

## Redshift and custom factories

```python
from sql_notebook_kit import create_session
from <company-package>.<connection-module> import <sso-factory>

session = create_session(
    backend="redshift",
    connection_kwargs={
        "factory": <sso-factory>,
        "factory_kwargs": {
            "db_user": "<user-email>",
            "preferred_role": "arn:aws:iam::<aws-account-id>:role/<role-name>",
        },
    },
)
session.register(login=True, visualization=True)
```

`login=True` starts SSO during registration. Use `login=False` to defer it to
the first query.

```sql
%sql
select current_user, current_database()
```

Use `%sql select current_user` for a one-line query. A standalone `%sql` first
line, as above, marks the rest of the cell as multiline SQL. Existing `%%sql`
cells remain fully supported. All three forms use the same bounded-result and
failed-transaction recovery behavior.

SELECT results render as a workspace with the bounded **Table**, multiple named
visualizations, and a **+** tab action when the `viz` extra is
installed. The twelve supported types include table, Cartesian charts, bubble,
box, pie, histogram, heatmap, combo, and counter. Applied configurations persist
in originating-cell metadata when the bundled JupyterLab 4 companion or the
wheel-bundled VS Code companion is available; otherwise the workspace clearly uses
session-only mode. The visualization extra includes the notebook MIME support
required by Plotly and requires pandas 3.0.5 or newer within the pandas 3
release series.

## Lazy SQL-to-Python transformations

Built-in adapters automatically configure a separately owned SQLFrame session.
Custom engines can provide their own transform-session factory:

```python
session = create_session(
    factory=<dbapi-factory>,
    dialect="<sqlalchemy-dialect>",
    transform_session_factory=<sqlframe-session-factory>,
)
session.register()
```

After a single `SELECT`, `_df` is a safe `LazyQuery` wrapper. Use
`_df.apply(...)` for SQLFrame transformations, `compile()` to inspect SQL, and
bounded `collect()` or `visualize()` actions. Acting on `_df` reruns the source
query through the separate transformation connection; transactions, temporary
tables, and session variables are not shared with `%sql`. See the
[lazy transformation guide](docs/transformations.md) for eligibility,
lifecycle, cost, and DuckDB setup details.

## Named profile

Set `SQL_NOTEBOOK_KIT_CONFIG` to a TOML file containing:

```toml
[profiles.analytics]
backend = "duckdb"

[profiles.analytics.connection_kwargs]
database = "analytics.duckdb"
```

Then register it:

```python
from sql_notebook_kit import create_session

session = create_session(profile="analytics")
session.register(login=True)
```

Passwords, tokens, client secrets, and AWS keys are rejected in TOML. See the
[factory contract](docs/factory-contract.md), [SSO guide](docs/sso.md), and
[visualization guide](docs/visualization.md) for the complete specification.

## Lifecycle

```python
session.login()       # eagerly validate or start authentication
session.reconnect()   # release JupySQL, discard the connection, authenticate again
session.dispose()     # close JupySQL and pooled resources
```

Failed SQL statements are never automatically replayed. Capability-aware
adapters roll back only when their backend supports meaningful recovery. A
concise sanitized database message is shown first, with SQL and technical
details collapsed below it.

See the [backend guide](docs/backends.md), [compatibility matrix](docs/compatibility.md),
and [migration guide](docs/migration.md) for backend-specific configuration,
support levels, and the intentional clean break from the old package identity.

The base install supplies the notebook kernel and eager SQL path. Optional extras
are deliberately scoped:

- `duckdb`: the certified DuckDB adapter, lazy transformations, and pandas;
- `viz`: bounded pandas/Plotly/ipywidgets visualizations;
- `transform`: SQLFrame transformations for a custom supported connection;
- `redshift`, `databricks`, and `bigquery`: preview cloud adapters; and
- `all`: every backend and visualization dependency, intended for compatibility
  testing rather than ordinary environments because it increases dependency and
  vulnerability surface area.

SQL Notebook Kit adds no telemetry. Connection and bounded result data remain in
the kernel process, while versioned visualization configuration may be written to
notebook cell metadata. SQL and credentials are sent only to the database connection
that the user configures. See the [security model](docs/security-model.md) for trust
boundaries and residual risks.

## Development

Editable installation is for contributors:

```bash
uv sync --all-groups
uv pip install -e '.[duckdb,viz]'
uv run pytest
uv run ruff check .
uv run mypy sql_notebook_kit
uv run --group docs mkdocs build --strict
pnpm check && pnpm test
pnpm build && pnpm package:vscode
uv build
```

The staged VSIX is generated and ignored by Git. When it is absent, Python
distribution and editable builds run the three pnpm commands above from this
package directory automatically. Git and path installs therefore require
Node.js and pnpm, while published wheels and source distributions reuse their
bundled VSIX and install without a frontend toolchain.

To iterate on the visualization controls without rebuilding or reinstalling the
VS Code extension, launch the interactive design lab and open the printed local
URL:

```bash
scripts/run_visualization_lab.sh
```

The lab runs the production ipywidgets workspace against deterministic sample
data and a simulated VS Code theme and metadata bridge. See the
[visualization guide](docs/visualization.md#visual-design-lab) for its scenarios
and QA workflow.

Licensed under the [MIT License](LICENSE).
