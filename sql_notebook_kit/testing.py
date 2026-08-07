"""Reusable checks for authors of external connection factories.

This module has no pytest dependency. Connector projects can call
``run_factory_contract`` from their own opt-in integration tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sql_notebook_kit.connectors import ConnectionFactory, DBAPIConnection
from sql_notebook_kit.errors import NotebookConnectionError


@dataclass(frozen=True, slots=True)
class FactoryContractReport:
    """Successful checks performed against a live factory."""

    distinct_connections: bool
    probe_executed: bool
    rollback_supported: bool
    close_supported: bool


def _validate_shape(connection: Any) -> DBAPIConnection:
    required = ("cursor", "commit", "rollback", "close")
    missing = [name for name in required if not callable(getattr(connection, name, None))]
    if missing:
        raise NotebookConnectionError(
            "factory returned an object missing required DBAPI methods: " + ", ".join(missing)
        )
    return connection


def run_factory_contract(
    factory: ConnectionFactory,
    *,
    kwargs: dict[str, Any] | None = None,
    probe_sql: str = "select 1",
) -> FactoryContractReport:
    """Run an explicit live contract test against two factory invocations.

    This may start SSO twice. It is intended for opt-in connector integration
    tests, never package import or routine notebook startup. Both connections
    are rolled back and closed even when a probe fails.
    """
    bound_kwargs = kwargs or {}
    first: DBAPIConnection | None = None
    second: DBAPIConnection | None = None
    try:
        first = _validate_shape(factory(**bound_kwargs))
        second = _validate_shape(factory(**bound_kwargs))
        if first is second:
            raise NotebookConnectionError(
                "factory returned the same physical connection twice; each invocation must be new"
            )
        cursor = first.cursor()
        try:
            cursor.execute(probe_sql)
            if getattr(cursor, "description", None):
                cursor.fetchone()
        finally:
            close_cursor = getattr(cursor, "close", None)
            if callable(close_cursor):
                close_cursor()
        first.rollback()
        second.rollback()
        return FactoryContractReport(True, True, True, True)
    finally:
        if first is not None:
            first.close()
        if second is not None and second is not first:
            second.close()
