"""Factory-backed SQL cells and bounded visualization for Jupyter notebooks."""

from sql_notebook_kit.adapters import BackendCapabilities, BackendName, SupportLevel
from sql_notebook_kit.connectors import DBAPIConnection, FactorySpec
from sql_notebook_kit.engine import make_engine, register
from sql_notebook_kit.errors import (
    AuthenticationError,
    ConfigurationError,
    FactoryImportError,
    LazyQueryError,
    MissingOptionalDependencyError,
    NotebookConnectionError,
    SQLExecutionError,
    SQLNotebookKitError,
    StaleLazyQueryError,
    VisualizationConfigError,
    VisualizationError,
    VisualizationPersistenceError,
    VisualizationRenderError,
)
from sql_notebook_kit.lazy import LazyQuery
from sql_notebook_kit.results import NotebookResult
from sql_notebook_kit.session import NotebookSession, create_session

__all__ = [
    "AuthenticationError",
    "BackendCapabilities",
    "BackendName",
    "ConfigurationError",
    "DBAPIConnection",
    "FactoryImportError",
    "FactorySpec",
    "LazyQuery",
    "LazyQueryError",
    "MissingOptionalDependencyError",
    "NotebookConnectionError",
    "NotebookResult",
    "NotebookSession",
    "SQLNotebookKitError",
    "SQLExecutionError",
    "StaleLazyQueryError",
    "SupportLevel",
    "VisualizationConfigError",
    "VisualizationError",
    "VisualizationPersistenceError",
    "VisualizationRenderError",
    "create_session",
    "make_engine",
    "register",
]
