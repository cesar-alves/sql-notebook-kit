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
%%sql
select current_user, current_database()
```

SELECT results render as a workspace with the bounded **Table**, multiple named
visualizations, and an **Add visualization** action when the `viz` extra is
installed. The twelve supported types include table, Cartesian charts, bubble,
box, pie, histogram, heatmap, combo, and counter. Applied configurations persist
in originating-cell metadata when the bundled JupyterLab 4 companion or the
separate VS Code companion is available; otherwise the workspace clearly uses
session-only mode. The visualization extra requires pandas 3.0.5 or newer
within the pandas 3 release series.

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
writes after an ambiguous network failure. When a managed `%%sql` cell reaches
the database and fails, its active transaction is rolled back so later cells
can continue. This also ends any explicit transaction opened across cells.

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
uv build
```

Licensed under the [MIT License](LICENSE).
