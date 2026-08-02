"""Public exceptions raised by :mod:`redshift_notebooks`.

Exception messages intentionally avoid rendering factory keyword arguments. A
factory may include sensitive values even when the package configuration policy
would normally reject them from TOML.
"""


class RedshiftNotebooksError(Exception):
    """Base class for all package-owned errors."""


class ConfigurationError(RedshiftNotebooksError, ValueError):
    """A profile, factory reference, or runtime option is invalid."""


class FactoryImportError(RedshiftNotebooksError, ImportError):
    """A dotted factory reference could not be imported or resolved."""


class AuthenticationError(RedshiftNotebooksError):
    """A connection factory could not authenticate its user."""


class NotebookConnectionError(RedshiftNotebooksError):
    """A factory failed to return a usable DBAPI connection."""


class MissingOptionalDependencyError(RedshiftNotebooksError, ImportError):
    """An optional package extra is required for the requested feature."""
