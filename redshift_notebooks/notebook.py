"""IPython/JupySQL integration isolated behind a stable package boundary."""

from __future__ import annotations

import re
import warnings
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import DBAPIError

from redshift_notebooks.errors import ConfigurationError
from redshift_notebooks.results import NotebookResult

_ALIAS_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


@dataclass(slots=True)
class _NotebookState:
    alias: str
    engine: Any
    max_rows: int
    allow_large_results: bool
    detach_results: bool


def _visualization_available() -> bool:
    try:
        import ipywidgets  # noqa: F401
        import pandas  # noqa: F401
        import plotly  # noqa: F401
    except ImportError:
        return False
    return True


def _detach_result(raw: Any, max_rows: int, *, cell_id: str | None = None) -> NotebookResult | Any:
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
    )


def _is_database_execution_error(exc: BaseException) -> bool:
    """Return whether an exception chain contains a SQLAlchemy DBAPI error."""
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, DBAPIError):
            return True
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return False


def _rollback_registered_connection(state: _NotebookState) -> None:
    """Roll back this session's long-lived JupySQL SQLAlchemy checkout."""
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
    ipython._redshift_notebooks_state = state

    def bounded_sql(line: str, cell: str) -> Any:
        active_state = ipython._redshift_notebooks_state
        jupysql_magic = ipython.find_cell_magic("jupysql")
        magic_owner = jupysql_magic.__self__
        old_autolimit = magic_owner.autolimit
        if active_state.detach_results:
            magic_owner.autolimit = active_state.max_rows + 1
        try:
            try:
                raw = ipython.run_cell_magic("jupysql", line, cell)
            except Exception as exc:
                if _is_database_execution_error(exc):
                    _rollback_registered_connection(active_state)
                raise
            if active_state.detach_results:
                parent: Any = getattr(ipython, "get_parent", lambda: {})() or {}
                metadata = parent.get("metadata", {}) if isinstance(parent, dict) else {}
                cell_id = metadata.get("cellId") or metadata.get("cell_id")
                return _detach_result(raw, active_state.max_rows, cell_id=cell_id)
            return raw
        finally:
            magic_owner.autolimit = old_autolimit

    ipython.register_magic_function(bounded_sql, magic_kind="cell", magic_name="sql")


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

    variable = f"_redshift_notebooks_engine_{id(session):x}"
    ipython.push({variable: session.engine})
    ipython.extension_manager.load_extension("sql")
    line = f"--alias {alias} {variable}" if alias else variable
    ipython.run_line_magic("sql", line)

    detach_results = visualization and _visualization_available()
    if visualization and not detach_results:
        warnings.warn(
            "visualization extras are not installed; SQL results will use "
            "JupySQL's table output. "
            "Install 'redshift-notebooks[viz]' to enable the chart builder.",
            stacklevel=2,
        )
    _install_session_sql_magic(
        ipython,
        _NotebookState(
            alias=alias or str(session.engine.url),
            engine=session.engine,
            max_rows=max_rows,
            allow_large_results=allow_large_results,
            detach_results=detach_results,
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
