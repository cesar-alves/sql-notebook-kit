"""Public exceptions raised by :mod:`sql_notebook_kit`.

Exception messages intentionally avoid rendering factory keyword arguments. A
factory may include sensitive values even when the package configuration policy
would normally reject them from TOML.
"""


class SQLNotebookKitError(Exception):
    """Base class for all package-owned errors."""


class ConfigurationError(SQLNotebookKitError, ValueError):
    """A profile, factory reference, or runtime option is invalid."""


class FactoryImportError(SQLNotebookKitError, ImportError):
    """A dotted factory reference could not be imported or resolved."""


class AuthenticationError(SQLNotebookKitError):
    """A connection factory could not authenticate its user."""


class NotebookConnectionError(SQLNotebookKitError):
    """A factory failed to return a usable DBAPI connection."""


class SQLExecutionError(SQLNotebookKitError):
    """A managed SQL magic failed during database execution.

    ``statement`` is retained for the expandable notebook diagnostic while
    ``str(error)`` stays concise. Bound parameter values are deliberately not
    stored on this exception.
    """

    def __init__(self, message: str, *, statement: str | None = None) -> None:
        self.statement = statement
        super().__init__(message)


class MissingOptionalDependencyError(SQLNotebookKitError, ImportError):
    """An optional package extra is required for the requested feature."""


class LazyQueryError(SQLNotebookKitError):
    """A lazy transformation could not be constructed or executed safely."""


class StaleLazyQueryError(LazyQueryError):
    """A lazy query belongs to a transform session that has been reconnected."""


class VisualizationError(SQLNotebookKitError):
    """Base class for visualization failures."""


class VisualizationConfigError(VisualizationError, ValueError):
    """A visualization configuration is invalid.

    ``path`` identifies the public configuration field without including data
    values or other potentially sensitive context.
    """

    def __init__(self, message: str, *, path: str | None = None) -> None:
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


class VisualizationRenderError(VisualizationError):
    """A validated visualization could not be rendered."""


class VisualizationPersistenceError(VisualizationError):
    """Visualization metadata could not be loaded or saved."""
