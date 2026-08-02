"""Reference SSO factories for the optional Amazon Redshift Python driver.

All authentication is deferred until a factory is called. Applications may use
these functions directly or treat them as guidelines for company-owned SSO
factories.
"""

from __future__ import annotations

from typing import Any

from redshift_notebooks.errors import ConfigurationError, MissingOptionalDependencyError


def _connect(**kwargs: Any) -> Any:
    try:
        import redshift_connector
    except ImportError as exc:
        raise MissingOptionalDependencyError(
            "Redshift SSO requires 'redshift-notebooks[redshift]'"
        ) from exc
    return redshift_connector.connect(**kwargs)


def browser_azure_sso(
    *,
    host: str,
    database: str,
    cluster_identifier: str,
    idp_tenant: str,
    client_id: str,
    port: int = 5439,
    listen_port: int = 7890,
    idp_response_timeout: int = 120,
    **driver_options: Any,
) -> Any:
    """Open a Redshift connection with browser-based Microsoft Entra ID SSO."""
    if idp_response_timeout < 10:
        raise ConfigurationError("idp_response_timeout must be at least 10 seconds")
    return _connect(
        iam=True,
        credentials_provider="BrowserAzureCredentialsProvider",
        host=host,
        database=database,
        cluster_identifier=cluster_identifier,
        idp_tenant=idp_tenant,
        client_id=client_id,
        port=port,
        listen_port=listen_port,
        idp_response_timeout=idp_response_timeout,
        **driver_options,
    )


def identity_center_sso(
    *,
    host: str,
    database: str,
    idc_region: str,
    issuer_url: str,
    port: int = 5439,
    listen_port: int = 7890,
    idp_response_timeout: int = 120,
    idc_client_display_name: str = "redshift-notebooks",
    **driver_options: Any,
) -> Any:
    """Open a Redshift connection with AWS IAM Identity Center browser SSO."""
    if idp_response_timeout < 10:
        raise ConfigurationError("idp_response_timeout must be at least 10 seconds")
    return _connect(
        credentials_provider="BrowserIdcAuthPlugin",
        host=host,
        database=database,
        idc_region=idc_region,
        issuer_url=issuer_url,
        port=port,
        listen_port=listen_port,
        idp_response_timeout=idp_response_timeout,
        idc_client_display_name=idc_client_display_name,
        **driver_options,
    )
