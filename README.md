# redshift-notebooks

`redshift-notebooks` brings SQL-cell interaction and bounded, editable charts
to Redshift-backed Jupyter and VS Code notebooks. It adapts any synchronous
factory that returns a DBAPI connection to SQLAlchemy and JupySQL, including
factories that perform browser SSO before opening a connection.

The package never needs a password-bearing connection URL. Authentication runs
inside the supplied factory only when a physical connection is required.

## Install

```bash
uv pip install -e '.[redshift,viz]'
```

Use the resulting environment as the notebook kernel.

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
redshift-notebooks vscode install
redshift-notebooks vscode status
```

The installer detects `code`, `code-insiders`, and `codium`; use `--editor` or
`--cli /path/to/editor-cli` to override it. Run the command in the matching SSH,
WSL, or dev-container terminal for remote windows. Browser-only `vscode.dev` is
not supported, and the Microsoft Jupyter extension is required.

## Existing SSO factory

```python
from redshift_notebooks import create_session
from <company-package>.<connection-module> import <sso-factory>

session = create_session(
    factory=<sso-factory>,
    dialect="redshift+redshift_connector",
    factory_kwargs={
        "db_user": "<user-email>",
        "preferred_role": "arn:aws:iam::<aws-account-id>:role/<role-name>",
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

Configure a separately owned SQLFrame session to expose each eligible SQL
result as `_df`:

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

Set `REDSHIFT_NOTEBOOKS_CONFIG` to a TOML file containing:

```toml
[profiles.analytics]
factory = "<company-package>.<connection-module>:<sso-factory>"
dialect = "redshift+redshift_connector"

[profiles.analytics.factory_kwargs]
db_user = "<user-email>"
preferred_role = "arn:aws:iam::<aws-account-id>:role/<role-name>"
```

Then register it:

```python
from redshift_notebooks import create_session

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

Failed SQL statements are never automatically replayed. This avoids repeating
writes after an ambiguous network failure. When a managed SQL cell reaches
the database and fails, its active transaction is rolled back so later cells
can continue. The concise Redshift message is shown first, with the SQL and a
sanitized traceback under **Technical details**. This also ends any explicit
transaction opened across cells.

## Compatibility APIs

The original `make_engine`, `register`, and
`redshift_notebooks.adapters.config.get_configured_engine` APIs remain
available. New code should prefer `create_session`, which owns the complete
authentication and notebook lifecycle.

## Development

```bash
uv run pytest
uv run ruff check .
uv run mypy redshift_notebooks
uv run --group docs mkdocs build --strict
pnpm check && pnpm test
pnpm build && pnpm package:vscode
uv build
```

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
