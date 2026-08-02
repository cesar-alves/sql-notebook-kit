"""Connection-agnostic SQLAlchemy engine builder for %%sql notebook cells.

Wraps any zero-arg DBAPI connection factory into a SQLAlchemy Engine via the
``creator=`` hook, so callers never need to build a connection string (or hand
credentials to SQLAlchemy at all) — the factory already knows how to
authenticate. This is what lets jupysql's ``%sql``/``%%sql`` magics run
against a connection obtained through arbitrary auth (SSO, IAM, a local
socket, ...), not just plain user/password DSNs.
"""

from __future__ import annotations

from typing import Any, Callable

import sqlalchemy
from sqlalchemy.pool import StaticPool

ConnectionFactory = Callable[[], Any]

DEFAULT_DIALECT = "redshift+redshift_connector"


def make_engine(
    connection_factory: ConnectionFactory,
    dialect: str = DEFAULT_DIALECT,
) -> sqlalchemy.engine.Engine:
    """Build a SQLAlchemy Engine around an existing DBAPI connection factory.

    ``connection_factory`` is called lazily, on first use, and again only if
    the pooled connection is found dead (``pool_pre_ping``) — matching a
    notebook's "log in once, reuse for the session" expectation instead of
    SQLAlchemy's default multi-connection pool.
    """
    return sqlalchemy.create_engine(
        f"{dialect}://",
        creator=connection_factory,
        poolclass=StaticPool,
        pool_pre_ping=True,
    )


def register(engine: sqlalchemy.engine.Engine, alias: str | None = None) -> None:
    """Load the jupysql IPython extension and make ``engine`` the active connection.

    Equivalent to running ``%load_ext sql`` followed by ``%sql engine`` (or
    ``%sql --alias <alias> engine``) by hand in a notebook cell.
    """
    from IPython import get_ipython

    ipython = get_ipython()
    if ipython is None:
        raise RuntimeError("register() must be called from within an IPython/Jupyter session")

    ipython.push({"_redshift_notebooks_engine": engine})
    ipython.run_line_magic("load_ext", "sql")
    line = "--alias " + alias + " _redshift_notebooks_engine" if alias else "_redshift_notebooks_engine"
    ipython.run_line_magic("sql", line)
