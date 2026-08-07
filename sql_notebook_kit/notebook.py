"""IPython/JupySQL integration isolated behind a stable package boundary."""

from __future__ import annotations

import re
import warnings
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import DBAPIError

from sql_notebook_kit.errors import ConfigurationError, SQLExecutionError
from sql_notebook_kit.results import NotebookResult

_ALIAS_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


@dataclass(slots=True)
class _NotebookState:
    session: Any
    alias: str
    engine: Any
    max_rows: int
    allow_large_results: bool
    detach_results: bool
    visualization_enabled: bool


def _visualization_available() -> bool:
    try:
        import ipywidgets  # noqa: F401
        import nbformat  # noqa: F401
        import pandas  # noqa: F401
        import plotly  # noqa: F401
    except ImportError:
        return False
    return True


def _pandas_available() -> bool:
    try:
        import pandas  # noqa: F401
    except ImportError:
        return False
    return True


def _detach_result(
    raw: Any,
    max_rows: int,
    *,
    cell_id: str | None = None,
    visualization_metadata: dict[str, Any] | None = None,
    lazy_notice: str | None = None,
    visualization_enabled: bool = True,
) -> NotebookResult | Any:
    """Consume at most max_rows + 1 from a JupySQL 0.11 ResultSet."""
    if not all(hasattr(raw, attribute) for attribute in ("keys", "fetchmany", "DataFrame")):
        return raw
    try:
        keys = list(raw.keys)
    except Exception:
        return raw
    if not keys:
        return raw

    # JupySQL 0.11 initializes ResultSet with up to two rows. The dependency
    # range is pinned and this private-access adapter is covered by integration
    # tests so future JupySQL changes fail in one isolated location.
    existing = len(getattr(raw, "_results", []))
    raw.fetchmany(max(0, max_rows + 1 - existing))
    frame = raw.DataFrame()
    truncated = len(frame) > max_rows
    bounded = frame.iloc[:max_rows].copy()
    with suppress(Exception):
        raw.close()
    return NotebookResult(
        dataframe=bounded,
        raw=raw,
        truncated=truncated,
        max_rows=max_rows,
        cell_id=cell_id,
        visualization_metadata=visualization_metadata,
        lazy_notice=lazy_notice,
        visualization_enabled=visualization_enabled,
    )


def _sql_source(line: str, cell: str | None) -> str:
    """Extract the SQL portion of a managed magic invocation."""
    from sql.parse import split_args_and_sql

    _arguments, line_sql = split_args_and_sql(line)
    if cell is None:
        return line_sql or line
    return "\n".join(part for part in (line_sql, cell) if part)


def _lazy_query_for_result(
    state: _NotebookState,
    raw: Any,
    *,
    line: str,
    cell: str | None,
) -> tuple[Any | None, str | None]:
    """Build a source-only lazy handle and its disclosure for a relation result."""
    if not state.session.transformations_enabled:
        return None, None
    try:
        keys = list(raw.keys)
    except Exception:
        return None, None
    if not keys:
        return None, None

    source = _sql_source(line, cell)
    if "{{" in source or "{%" in source:
        return None, (
            "Not assigned to _df: templated SQL cannot be reconstructed safely. "
            "The previous _df, if any, is unchanged."
        )
    try:
        import sqlparse

        source_statements = [item for item in sqlparse.split(source) if item.strip()]
    except Exception:
        source_statements = []
    if len(source_statements) != 1:
        return None, (
            "Not assigned to _df: only one SQL statement can be transformed lazily. "
            "The previous _df, if any, is unchanged."
        )

    statement = getattr(raw, "_statement", None)
    if not isinstance(statement, str) or not statement.strip():
        return None, (
            "Not assigned to _df: the executed query could not be reconstructed. "
            "The previous _df, if any, is unchanged."
        )
    from sql_notebook_kit.lazy import validate_relation_query

    reason = validate_relation_query(statement)
    if reason is not None:
        return None, (
            f"Not assigned to _df: {reason}. The previous _df, if any, is unchanged."
        )
    lazy_query = state.session.sql(statement)
    return lazy_query, (
        "Available as _df for lazy Python transformations. Collecting it reruns "
        "this query on a separate connection."
    )


def _database_execution_error(exc: BaseException) -> DBAPIError | None:
    """Return the SQLAlchemy DBAPI error in an exception chain, if present."""
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, DBAPIError):
            return current
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return None


def _is_database_execution_error(exc: BaseException) -> bool:
    """Return whether an exception chain contains a SQLAlchemy DBAPI error."""
    return _database_execution_error(exc) is not None


def _sql_error_summary(exc: DBAPIError, state: _NotebookState | None = None) -> str:
    """Delegate sanitized database diagnostics to the active adapter."""
    if state is not None:
        return state.session.adapter.summarize_database_error(exc.orig)
    from sql_notebook_kit.adapters.base import generic_error_summary

    return generic_error_summary(exc.orig)


def _rewrite_standalone_percent_sql(lines: list[str]) -> list[str]:
    """Treat a standalone first-line ``%sql`` marker as multiline SQL."""
    if len(lines) > 1 and lines[0].strip() == "%sql":
        return [lines[0].replace("%sql", "%%sql", 1), *lines[1:]]
    return lines


def _rollback_registered_connection(state: _NotebookState) -> None:
    """Roll back this session's long-lived JupySQL SQLAlchemy checkout."""
    if not state.session.adapter.capabilities.rollback_after_error:
        return
    from sql.connection import ConnectionManager

    registered = ConnectionManager.connections.get(state.alias)
    connection = getattr(registered, "connection_sqlalchemy", None)
    if connection is None or getattr(connection, "engine", None) is not state.engine:
        return
    try:
        connection.rollback()
    except Exception as exc:
        warnings.warn(
            "could not roll back the failed SQL cell "
            f"({type(exc).__name__}); call session.reconnect() before running more SQL",
            stacklevel=3,
        )


def _install_session_sql_magic(ipython: Any, state: _NotebookState) -> None:
    ipython._sql_notebook_kit_state = state

    if not getattr(ipython, "_sql_notebook_kit_transformer_installed", False):
        ipython.input_transformers_cleanup.append(_rewrite_standalone_percent_sql)
        ipython._sql_notebook_kit_transformer_installed = True

    def execute(line: str, cell: str | None) -> Any:
        active_state = ipython._sql_notebook_kit_state
        jupysql_magic = (
            ipython.find_cell_magic("jupysql")
            if cell is not None
            else ipython.find_line_magic("jupysql")
        )
        magic_owner = jupysql_magic.__self__
        old_autolimit = magic_owner.autolimit
        if active_state.detach_results:
            magic_owner.autolimit = active_state.max_rows + 1
        try:
            try:
                raw = (
                    ipython.run_cell_magic("jupysql", line, cell)
                    if cell is not None
                    else ipython.run_line_magic("jupysql", line)
                )
            except Exception as exc:
                database_error = _database_execution_error(exc)
                if database_error is not None:
                    _rollback_registered_connection(active_state)
                    raise SQLExecutionError(
                        _sql_error_summary(database_error, active_state),
                        statement=database_error.statement,
                    ) from exc
                raise
            if active_state.detach_results:
                parent: Any = getattr(ipython, "get_parent", lambda: {})() or {}
                metadata = parent.get("metadata", {}) if isinstance(parent, dict) else {}
                cell_id = metadata.get("cellId") or metadata.get("cell_id")
                namespace = metadata.get("sql_notebook_kit")
                if not isinstance(namespace, dict) or "visualizations" not in namespace:
                    namespace = metadata.get("redshift_notebooks")
                visualization_metadata = (
                    namespace.get("visualizations") if isinstance(namespace, dict) else None
                )
                lazy_query, lazy_notice = _lazy_query_for_result(
                    active_state, raw, line=line, cell=cell
                )
                if lazy_query is not None:
                    ipython.push({"_df": lazy_query})
                return _detach_result(
                    raw,
                    active_state.max_rows,
                    cell_id=cell_id,
                    visualization_metadata=visualization_metadata,
                    lazy_notice=lazy_notice,
                    visualization_enabled=active_state.visualization_enabled,
                )
            return raw
        finally:
            magic_owner.autolimit = old_autolimit

    def bounded_cell_sql(line: str, cell: str) -> Any:
        return execute(line, cell)

    def bounded_line_sql(line: str) -> Any:
        return execute(line, None)

    ipython.register_magic_function(bounded_cell_sql, magic_kind="cell", magic_name="sql")
    ipython.register_magic_function(bounded_line_sql, magic_kind="line", magic_name="sql")


def register_session(
    session: Any,
    *,
    alias: str | None,
    visualization: bool,
    max_rows: int,
    allow_large_results: bool,
) -> None:
    """Register a session's engine and optional bounded cell-magic wrapper."""
    from IPython import get_ipython

    ipython = get_ipython()
    if ipython is None:
        raise RuntimeError("register() must be called from within an IPython/Jupyter session")
    if alias is not None and not _ALIAS_PATTERN.fullmatch(alias):
        raise ConfigurationError(
            "alias must start with a letter or underscore and contain only "
            "letters, digits, '-', '_'"
        )
    if max_rows < 1:
        raise ConfigurationError("max_rows must be positive")
    if max_rows > 100_000 and not allow_large_results:
        raise ConfigurationError("max_rows above 100000 requires allow_large_results=True")

    variable = f"_sql_notebook_kit_engine_{id(session):x}"
    ipython.push({variable: session.engine})
    ipython.extension_manager.load_extension("sql")
    line = f"--alias {alias} {variable}" if alias else variable
    ipython.run_line_magic("sql", line)

    visualization_enabled = visualization and _visualization_available()
    if visualization and not visualization_enabled:
        warnings.warn(
            "visualization extras are not installed; SQL results will use "
            "JupySQL's table output. "
            "Install 'sql-notebook-kit[viz]' to enable the chart builder.",
            stacklevel=2,
        )
    if session.transformations_enabled and not _pandas_available():
        from sql_notebook_kit.errors import MissingOptionalDependencyError

        raise MissingOptionalDependencyError(
            "lazy transformations require 'sql-notebook-kit[transform]'"
        )
    detach_results = visualization_enabled or session.transformations_enabled
    _install_session_sql_magic(
        ipython,
        _NotebookState(
            session=session,
            alias=alias or str(session.engine.url),
            engine=session.engine,
            max_rows=max_rows,
            allow_large_results=allow_large_results,
            detach_results=detach_results,
            visualization_enabled=visualization_enabled,
        ),
    )


def close_registered_session(alias: str) -> None:
    """Close the JupySQL connection identified by a validated session alias."""
    from IPython import get_ipython

    ipython = get_ipython()
    if ipython is None:
        return
    try:
        ipython.run_line_magic("sql", f"--close {alias}")
    except Exception as exc:
        warnings.warn(
            f"could not close JupySQL connection {alias!r}: {type(exc).__name__}",
            stacklevel=2,
        )
