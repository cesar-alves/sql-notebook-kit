# Connection factory contract

This page is the normative compatibility contract for custom connection
factories. **MUST**, **MUST NOT**, and **SHOULD** describe requirements for a
factory that is safe to use with `redshift-notebooks`.

## Callable signature

A factory MUST be synchronous and callable with the keyword arguments supplied
to `create_session` or a named profile:

```python
def <sso-factory>(
    *,
    db_user: str,
    preferred_role: str,
) -> <dbapi-connection>:
    ...
```

Every invocation MUST return a new, open DBAPI 2.0 connection. It MUST NOT
cache or return the same physical connection. SQLAlchemy owns pooling,
rollback, invalidation, and closure.

The returned object MUST provide compatible `cursor()`, `commit()`,
`rollback()`, and `close()` methods. A cursor used by the SQLAlchemy dialect
must implement the corresponding DBAPI cursor behavior.

## Authentication timing

Importing or resolving a factory MUST NOT authenticate, start a callback
server, or open a browser. Authentication begins only when the callable is
invoked by `session.login()`, `session.register(login=True)`, or the first
lazy connection checkout.

The default pool serializes factory invocation. A factory used with custom
pooling SHOULD document whether its credential cache and browser callback
listener are thread-safe.

## Reconnection and ownership

`session.reconnect()` releases JupySQL's long-lived checkout, disposes the
physical connection, and invokes the factory again. The factory MUST obtain
fresh credentials or restart SSO when its previous credentials are no longer
valid.

The package does not inspect provider tokens or replay failed statements. A
failed statement may have reached Redshift, so automatic replay could duplicate
a write.

## Failure behavior

A factory MUST raise an exception on configuration, authentication, or network
failure. It MUST NOT return `None` or a partially initialized connection.

Factories SHOULD raise:

| Error | Meaning |
| --- | --- |
| `ConfigurationError` | Required factory inputs are absent or invalid. |
| `AuthenticationError` | SSO was rejected, cancelled, or timed out. |
| `NotebookConnectionError` | Authentication succeeded but no usable DBAPI connection was created. |

Provider exceptions may propagate with their original traceback. Messages MUST
NOT contain passwords, tokens, SAML assertions, client secrets, temporary AWS
credentials, or complete connection arguments.

## Reusable contract test

The live helper invokes the factory twice. For browser SSO, keep the test
explicitly opt-in:

```python
import os
import pytest

from <company-package>.<connection-module> import <sso-factory>
from redshift_notebooks.testing import run_factory_contract


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_SSO_TESTS") != "1",
    reason="live SSO is opt-in",
)
def test_sso_factory_contract():
    report = run_factory_contract(
        <sso-factory>,
        kwargs={
            "db_user": "<user-email>",
            "preferred_role": "arn:aws:iam::<aws-account-id>:role/<role-name>",
        },
    )
    assert report.distinct_connections
    assert report.probe_executed
```

The helper validates distinct connections, DBAPI shape, `select 1`, rollback,
cursor closure, and connection closure.
