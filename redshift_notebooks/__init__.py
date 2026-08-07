"""Factory-backed SQL cells and bounded visualization for Jupyter notebooks."""

from redshift_notebooks.connectors import DBAPIConnection, FactorySpec
from redshift_notebooks.engine import make_engine, register
from redshift_notebooks.errors import (
    AuthenticationError,
    ConfigurationError,
    FactoryImportError,
    LazyQueryError,
    MissingOptionalDependencyError,
    NotebookConnectionError,
    RedshiftNotebooksError,
    SQLExecutionError,
    StaleLazyQueryError,
    VisualizationConfigError,
    VisualizationError,
    VisualizationPersistenceError,
    VisualizationRenderError,
)
from redshift_notebooks.lazy import LazyQuery
from redshift_notebooks.session import NotebookSession, create_session

__all__ = [
    "AuthenticationError",
    "ConfigurationError",
    "DBAPIConnection",
    "FactoryImportError",
    "FactorySpec",
    "LazyQuery",
    "LazyQueryError",
    "MissingOptionalDependencyError",
    "NotebookConnectionError",
    "NotebookSession",
    "RedshiftNotebooksError",
    "SQLExecutionError",
    "StaleLazyQueryError",
    "VisualizationConfigError",
    "VisualizationError",
    "VisualizationPersistenceError",
    "VisualizationRenderError",
    "create_session",
    "make_engine",
    "register",
]
