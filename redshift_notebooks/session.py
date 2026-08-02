"""Notebook session lifecycle for factory-backed SQLAlchemy engines."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.engine import Engine

from redshift_notebooks.connectors import FactoryReference, FactorySpec
from redshift_notebooks.engine import make_engine


@dataclass(slots=True)
class NotebookSession:
    """Own an engine and its SSO/DBAPI connection lifecycle.

    Constructing a session never invokes the factory. Call :meth:`login`, pass
    ``login=True`` to :meth:`register`, or execute the first query to start SSO.
    """

    spec: FactorySpec
    engine: Engine
    _registered: bool = False
    _jupysql_alias: str | None = None
    _registration: dict[str, Any] | None = None

    @classmethod
    def from_spec(cls, spec: FactorySpec, *, pool_timeout: float = 30.0) -> NotebookSession:
        """Create a lazy session from a validated factory specification."""
        engine = make_engine(spec.bind(), spec.dialect, pool_timeout=pool_timeout)
        return cls(spec=spec, engine=engine)

    def login(self) -> NotebookSession:
        """Invoke the factory now and validate the connection with a checkout."""
        if self._registered:
            # JupySQL keeps its SQLAlchemy checkout for the registration's
            # lifetime, so registration itself already proves login succeeded.
            return self
        with self.engine.connect():
            pass
        return self

    def register(
        self,
        *,
        alias: str | None = None,
        login: bool = False,
        visualization: bool = True,
        max_rows: int = 10_000,
        allow_large_results: bool = False,
    ) -> NotebookSession:
        """Register SQL magics and optional bounded visualization in IPython."""
        from redshift_notebooks.notebook import register_session

        requested_registration = {
            "alias": alias,
            "visualization": visualization,
            "max_rows": max_rows,
            "allow_large_results": allow_large_results,
        }
        if self._registered and self._registration == requested_registration:
            return self
        if self._registered:
            self._close_registered_connection()
        if login:
            self.login()
        effective_alias = alias or f"rn_{id(self):x}"
        register_session(
            self,
            alias=effective_alias,
            visualization=visualization,
            max_rows=max_rows,
            allow_large_results=allow_large_results,
        )
        self._registered = True
        self._jupysql_alias = effective_alias
        self._registration = requested_registration
        return self

    def reconnect(self, *, login: bool = True) -> NotebookSession:
        """Drop pooled connections and optionally start a fresh SSO flow."""
        was_registered = self._registered
        registration = dict(self._registration or {})
        self._close_registered_connection()
        self.engine.dispose()
        if login:
            self.login()
        if was_registered:
            self.register(login=False, **registration)
        return self

    def dispose(self) -> None:
        """Close pooled physical connections owned by this session."""
        self._close_registered_connection()
        self.engine.dispose()
        self._registered = False

    def _close_registered_connection(self) -> None:
        """Release JupySQL's long-lived engine checkout, if registered."""
        if not self._registered or not self._jupysql_alias:
            return
        from redshift_notebooks.notebook import close_registered_session

        close_registered_session(self._jupysql_alias)
        self._registered = False
        self._jupysql_alias = None

    def __enter__(self) -> NotebookSession:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.dispose()


def create_session(
    *,
    factory: FactoryReference | None = None,
    dialect: str | None = None,
    factory_kwargs: dict[str, Any] | None = None,
    profile: str | None = None,
    name: str | None = None,
    pool_timeout: float = 30.0,
    secret_resolver: Callable[[str], str | None] | None = None,
) -> NotebookSession:
    """Create a lazy notebook session from explicit inputs or a named profile.

    Explicit factory inputs and ``profile`` are mutually exclusive. Factory
    keyword values are never included in diagnostics or object representations.
    """
    if profile is not None:
        if factory is not None or dialect is not None or factory_kwargs is not None:
            from redshift_notebooks.errors import ConfigurationError

            raise ConfigurationError("profile cannot be combined with explicit factory inputs")
        from redshift_notebooks.adapters.config import load_profile

        spec = load_profile(profile, secret_resolver=secret_resolver)
    else:
        if factory is None or dialect is None:
            from redshift_notebooks.errors import ConfigurationError

            raise ConfigurationError("factory and dialect are required when profile is not used")
        spec = FactorySpec(factory=factory, dialect=dialect, kwargs=factory_kwargs or {}, name=name)
    return NotebookSession.from_spec(spec, pool_timeout=pool_timeout)
