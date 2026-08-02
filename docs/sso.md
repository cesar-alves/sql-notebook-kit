# SSO integration

An existing company SSO function is the preferred integration path. Pass it
directly during development and use a dotted profile reference for repeatable
notebook configuration.

## Wrapper for an existing factory

```python
def notebook_connection_factory(
    *,
    db_user: str,
    preferred_role: str,
):
    from <company-package>.<connection-module> import <sso-factory>

    return <sso-factory>(
        db_user=db_user,
        preferred_role=preferred_role,
    )
```

The import is inside the function only when the external package itself has
import-time side effects. Prefer fixing those side effects in the owning
package.

## Browser-based Microsoft Entra ID

The optional reference factory maps documented inputs to
`BrowserAzureCredentialsProvider`:

```python
from redshift_notebooks import create_session
from redshift_notebooks.adapters import browser_azure_sso

session = create_session(
    factory=browser_azure_sso,
    dialect="redshift+redshift_connector",
    factory_kwargs={
        "host": "<cluster-host>",
        "database": "<database-name>",
        "cluster_identifier": "<cluster-name>",
        "idp_tenant": "<tenant-id>",
        "client_id": "<client-id>",
        "listen_port": 7890,
        "idp_response_timeout": 120,
    },
)
session.register(login=True)
```

## AWS IAM Identity Center

```python
from redshift_notebooks import create_session
from redshift_notebooks.adapters import identity_center_sso

session = create_session(
    factory=identity_center_sso,
    dialect="redshift+redshift_connector",
    factory_kwargs={
        "host": "<cluster-host>",
        "database": "<database-name>",
        "idc_region": "<aws-region>",
        "issuer_url": "<identity-center-issuer-url>",
        "listen_port": 7890,
        "idp_response_timeout": 120,
    },
)
session.register(login=True)
```

## Secrets

TOML profiles reject `password`, `token`, `client_secret`, session tokens, and
AWS access keys. Declare required secret field names and resolve their values
from the environment:

```toml
[profiles.analytics]
factory = "<company-package>.<connection-module>:<sso-factory>"
dialect = "redshift+redshift_connector"
secret_fields = ["token"]
```

Set `REDSHIFT_NOTEBOOKS_SECRET_TOKEN` in the kernel environment. Alternatively,
pass `secret_resolver=` to `create_session`. The resolver receives the field
name and returns its value; the package never prints that value.

## Browser callback requirements

- The callback port must be free on the notebook kernel host.
- A local or remote kernel must be able to receive the identity-provider
  redirect expected by the driver.
- Required VPN, DNS, proxy, and firewall access must exist before login.
- A headless kernel needs a provider-specific device/token flow or a custom
  factory; browser factories cannot make an unreachable browser callback work.
