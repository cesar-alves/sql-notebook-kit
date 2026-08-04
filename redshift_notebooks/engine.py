"""Connection-agnostic SQLAlchemy engine builder for %%sql notebook cells.

Wraps any zero-arg DBAPI connection factory into a SQLAlchemy Engine via the
``creator=`` hook, so callers never need to build a connection string (or hand
credentials to SQLAlchemy at all) — the factory already knows how to
authenticate. This is what lets jupysql's ``%sql``/``%%sql`` magics run
against a connection obtained through arbitrary auth (SSO, IAM, a local
socket, ...), not just plain user/password DSNs.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import sqlalchemy
from sqlalchemy.exc import NoSuchModuleError
from sqlalchemy.pool import QueuePool

from redshift_notebooks.errors import ConfigurationError, MissingOptionalDependencyError

ConnectionFactory = Callable[[], Any]

DEFAULT_DIALECT = "redshift+redshift_connector"


def make_engine(
    connection_factory: ConnectionFactory,
    dialect: str = DEFAULT_DIALECT,
    *,
    pool_timeout: float = 30.0,
) -> sqlalchemy.engine.Engine:
    """Build a SQLAlchemy Engine around an existing DBAPI connection factory.

    ``connection_factory`` is called lazily and again after invalidation. The
    one-connection queue serializes checkouts instead of handing the same DBAPI
    connection to concurrent callers, while retaining a notebook's "log in
    once, reuse for the session" behavior.
    """
    try:
        return sqlalchemy.create_engine(
            f"{dialect}://",
            creator=connection_factory,
            poolclass=QueuePool,
            pool_size=1,
            max_overflow=0,
            pool_timeout=pool_timeout,
            pool_pre_ping=True,
            hide_parameters=True,
        )
    except (ImportError, NoSuchModuleError) as exc:
        if dialect == DEFAULT_DIALECT:
            raise MissingOptionalDependencyError(
                "the Redshift dialect requires the optional driver; install "
                "'redshift-notebooks[redshift]'"
            ) from exc
        raise


def register(engine: sqlalchemy.engine.Engine, alias: str | None = None) -> None:
    """Load the jupysql IPython extension and make ``engine`` the active connection.

    Equivalent to running ``%load_ext sql`` followed by ``%sql engine`` (or
    ``%sql --alias <alias> engine``) by hand in a notebook cell.
    """
    from IPython import get_ipython

    ipython = get_ipython()
    if ipython is None:
        raise RuntimeError("register() must be called from within an IPython/Jupyter session")
    if alias is not None and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", alias):
        raise ConfigurationError("alias contains characters that are unsafe in an IPython magic")

    variable = f"_redshift_notebooks_engine_{id(engine):x}"
    ipython.push({variable: engine})
    ipython.extension_manager.load_extension("sql")
    line = "--alias " + alias + " " + variable if alias else variable
    ipython.run_line_magic("sql", line)
