"""Database adapter contracts and built-in implementations."""

from sql_notebook_kit.adapters.base import (
    BackendAdapter,
    BackendCapabilities,
    BackendName,
    CustomFactoryAdapter,
    SupportLevel,
)
from sql_notebook_kit.adapters.builtins import create_builtin_adapter
from sql_notebook_kit.adapters.redshift import browser_azure_sso, identity_center_sso

__all__ = [
    "BackendAdapter",
    "BackendCapabilities",
    "BackendName",
    "CustomFactoryAdapter",
    "SupportLevel",
    "browser_azure_sso",
    "create_builtin_adapter",
    "identity_center_sso",
]
