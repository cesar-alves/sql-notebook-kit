"""Notebook session lifecycle for factory-backed SQLAlchemy engines."""

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.engine import Engine

from redshift_notebooks.connectors import FactoryReference, FactorySpec
from redshift_notebooks.engine import make_engine
from redshift_notebooks.errors import (
    ConfigurationError,
    LazyQueryError,
    MissingOptionalDependencyError,
)

TransformSessionFactory = Callable[[], Any]
_TRANSFORM_OWNERS: dict[int, int] = {}

if TYPE_CHECKING:
    from redshift_notebooks.lazy import LazyQuery


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
    _transform_session_factory: TransformSessionFactory | None = field(
        default=None, repr=False
    )
    _transform_session: Any = field(default=None, init=False, repr=False)
    _transform_generation: int = field(default=0, init=False, repr=False)

    @classmethod
    def from_spec(
        cls,
        spec: FactorySpec,
        *,
        pool_timeout: float = 30.0,
        transform_session_factory: TransformSessionFactory | None = None,
    ) -> NotebookSession:
        """Create a lazy session from a validated factory specification."""
        engine = make_engine(spec.bind(), spec.dialect, pool_timeout=pool_timeout)
        return cls(
            spec=spec,
            engine=engine,
            _transform_session_factory=transform_session_factory,
        )

    @property
    def transformations_enabled(self) -> bool:
        """Return whether this session can create lazy transformation queries."""
        return self._transform_session_factory is not None

    def sql(self, query: str) -> LazyQuery:
        """Create a lazy relation query without opening the transform connection."""
        from redshift_notebooks.lazy import LazyQuery, validate_relation_query

        if self._transform_session_factory is None:
            raise ConfigurationError(
                "lazy transformations are not configured; pass transform_session_factory"
            )
        reason = validate_relation_query(query)
        if reason is not None:
            raise ConfigurationError(reason)
        return LazyQuery(self, query, self._transform_generation)

    def _get_transform_session(self) -> Any:
        if self._transform_session is not None:
            return self._transform_session
        active_owners = set(_TRANSFORM_OWNERS.values())
        if active_owners and id(self) not in active_owners:
            raise ConfigurationError(
                "a transform session is already owned by another NotebookSession; "
                "dispose it before opening another transform channel"
            )
        factory = self._transform_session_factory
        if factory is None:
            raise ConfigurationError("lazy transformations are not configured")
        try:
            transform_session = factory()
        except ImportError as exc:
            raise MissingOptionalDependencyError(
                "lazy transformations require 'redshift-notebooks[transform]'"
            ) from exc
        except Exception as exc:
            raise LazyQueryError(
                f"the transform session could not be created ({type(exc).__name__})"
            ) from exc
        if not callable(getattr(transform_session, "sql", None)) or not callable(
            getattr(transform_session, "stop", None)
        ):
            raise ConfigurationError(
                "transform_session_factory must return a SQLFrame-compatible session "
                "with sql() and stop()"
            )
        owner = _TRANSFORM_OWNERS.get(id(transform_session))
        if owner is not None and owner != id(self):
            raise ConfigurationError(
                "transform_session_factory returned a transform session already owned "
                "by another NotebookSession"
            )
        _TRANSFORM_OWNERS[id(transform_session)] = id(self)
        self._transform_session = transform_session
        return transform_session

    def _create_transform_dataframe(self, query: str) -> object:
        try:
            return self._get_transform_session().sql(query)
        except (ConfigurationError, LazyQueryError, MissingOptionalDependencyError):
            raise
        except Exception as exc:
            raise LazyQueryError(
                f"the lazy query could not be constructed ({type(exc).__name__})"
            ) from exc

    def _close_transform_session(self) -> None:
        transform_session = self._transform_session
        self._transform_session = None
        self._transform_generation += 1
        if transform_session is None:
            return
        _TRANSFORM_OWNERS.pop(id(transform_session), None)
        try:
            transform_session.stop()
        except Exception as exc:
            warnings.warn(
                f"could not close transform session ({type(exc).__name__})",
                stacklevel=3,
            )

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
        self._close_transform_session()
        self.engine.dispose()
        if login:
            self.login()
        if was_registered:
            self.register(login=False, **registration)
        return self

    def dispose(self) -> None:
        """Close pooled physical connections owned by this session."""
        self._close_registered_connection()
        self._close_transform_session()
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
    transform_session_factory: TransformSessionFactory | None = None,
) -> NotebookSession:
    """Create a lazy notebook session from explicit inputs or a named profile.

    Explicit factory inputs and ``profile`` are mutually exclusive. Factory
    keyword values are never included in diagnostics or object representations.
    """
    if profile is not None:
        if (
            factory is not None
            or dialect is not None
            or factory_kwargs is not None
            or transform_session_factory is not None
        ):
            raise ConfigurationError("profile cannot be combined with explicit factory inputs")
        from redshift_notebooks.adapters.config import load_profile

        spec = load_profile(profile, secret_resolver=secret_resolver)
    else:
        if factory is None or dialect is None:
            raise ConfigurationError("factory and dialect are required when profile is not used")
        spec = FactorySpec(factory=factory, dialect=dialect, kwargs=factory_kwargs or {}, name=name)
    return NotebookSession.from_spec(
        spec,
        pool_timeout=pool_timeout,
        transform_session_factory=transform_session_factory,
    )
