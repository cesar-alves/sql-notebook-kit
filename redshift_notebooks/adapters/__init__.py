"""Built-in configuration and Redshift SSO adapters."""

from redshift_notebooks.adapters.redshift import browser_azure_sso, identity_center_sso

__all__ = ["browser_azure_sso", "identity_center_sso"]
