# redshift-notebooks

`redshift-notebooks` turns a synchronous DBAPI connection factory into a
managed SQLAlchemy/JupySQL notebook session. The factory may perform browser
SSO, acquire temporary credentials, or use any other authentication flow.

## Minimal setup

```python
from redshift_notebooks import create_session
from <company-package>.<connection-module> import <sso-factory>

session = create_session(
    factory=<sso-factory>,
    dialect="redshift+redshift_connector",
    factory_kwargs={"db_user": "<user-email>"},
)
session.register(login=True)
```

The factory is not invoked during import or session construction. With
`login=True`, it is invoked immediately before notebook registration. With
`login=False`, it is invoked when JupySQL first checks out a connection.

Read the [factory contract](factory-contract.md) before integrating a custom
SSO implementation.
