"""Backend adapter contracts for eager and lazy notebook execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Protocol, runtime_checkable

from sql_notebook_kit.connectors import DBAPIConnection, FactorySpec

BackendName = Literal["redshift", "duckdb", "databricks", "bigquery"]
SupportLevel = Literal["certified", "preview", "best_effort"]
TransformSessionFactory = Callable[[], Any]


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    """Stable behavior advertised by a configured backend."""

    backend: str
    support_level: SupportLevel
    transactions: bool
    rollback_after_error: bool
    lazy_transformations: bool
    nested_result_types: bool
    sql_highlighting_dialect: str


@runtime_checkable
class BackendAdapter(Protocol):
    """Internal contract implemented by built-in and custom backends."""

    name: str
    sqlalchemy_dialect: str
    capabilities: BackendCapabilities

    @property
    def factory_spec(self) -> FactorySpec: ...
    def connection_factory(self) -> DBAPIConnection: ...
    def create_transform_session(self) -> object: ...
    def summarize_database_error(self, error: BaseException) -> str: ...
    def close(self) -> None: ...


def generic_error_summary(error: BaseException) -> str:
    """Return one sanitized line from a driver error."""
    payload = error.args[0] if getattr(error, "args", ()) else None
    if isinstance(payload, dict):
        message = payload.get("M") or payload.get("message") or payload.get("Message")
        code = payload.get("C") or payload.get("code") or payload.get("sqlstate")
        if message:
            summary = str(message).strip()
            return f"{summary} (SQLSTATE {code})" if code else summary
    text = str(error).strip()
    return text.splitlines()[0] if text else "The SQL statement could not be executed."


@dataclass(slots=True, repr=False)
class CustomFactoryAdapter:
    """Best-effort adapter for the public custom DBAPI factory path."""

    spec: FactorySpec
    transform_session_factory: TransformSessionFactory | None = field(default=None, repr=False)
    capabilities: BackendCapabilities = field(init=False)
    name: str = field(init=False)
    sqlalchemy_dialect: str = field(init=False)

    def __post_init__(self) -> None:
        self.name = self.spec.name or "custom"
        self.sqlalchemy_dialect = self.spec.dialect
        self.capabilities = BackendCapabilities(
            self.name, "best_effort", True, True,
            self.transform_session_factory is not None, False, "sql"
        )

    @property
    def factory_spec(self) -> FactorySpec:
        return self.spec

    def connection_factory(self) -> DBAPIConnection:
        return self.spec.bind()()

    def create_transform_session(self) -> object:
        if self.transform_session_factory is None:
            raise RuntimeError("lazy transformations are not configured")
        return self.transform_session_factory()

    def summarize_database_error(self, error: BaseException) -> str:
        return generic_error_summary(error)

    def close(self) -> None:
        return None


@dataclass(slots=True, repr=False)
class BuiltinAdapter:
    """Configured built-in adapter with secret-safe bound connection values."""

    name: str
    sqlalchemy_dialect: str
    capabilities: BackendCapabilities
    _connection_creator: Callable[[], DBAPIConnection] = field(repr=False)
    _transform_creator: TransformSessionFactory | None = field(default=None, repr=False)
    _error_summarizer: Callable[[BaseException], str] = field(
        default=generic_error_summary, repr=False
    )
    _spec: FactorySpec = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._spec = FactorySpec(
            factory=self._connection_creator, dialect=self.sqlalchemy_dialect, name=self.name
        )

    @property
    def factory_spec(self) -> FactorySpec:
        return self._spec

    def connection_factory(self) -> DBAPIConnection:
        return self._connection_creator()

    def create_transform_session(self) -> object:
        if self._transform_creator is None:
            raise RuntimeError(f"lazy transformations are unavailable for {self.name}")
        return self._transform_creator()

    def summarize_database_error(self, error: BaseException) -> str:
        return self._error_summarizer(error)

    def close(self) -> None:
        return None


def frozen_values(values: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Copy caller-owned connection values without exposing them in representations."""
    return MappingProxyType(dict(values or {}))
