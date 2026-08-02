"""Connection-factory contracts and resolution.

The primary integration surface is a synchronous callable. SQLAlchemy calls it
only when a new physical DBAPI connection is needed. Each invocation must
return a *new*, open DBAPI 2.0 connection; the factory must not cache one.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from redshift_notebooks.errors import (
    ConfigurationError,
    FactoryImportError,
    NotebookConnectionError,
)


@runtime_checkable
class DBAPIConnection(Protocol):
    """Minimum connection behavior required by the factory contract."""

    def cursor(self) -> Any:
        """Return a DBAPI cursor."""

    def commit(self) -> None:
        """Commit the current transaction."""

    def rollback(self) -> None:
        """Roll back the current transaction."""

    def close(self) -> None:
        """Close the physical connection."""


ConnectionFactory = Callable[..., DBAPIConnection]
FactoryReference = str | ConnectionFactory


@dataclass(frozen=True, slots=True)
class FactorySpec:
    """A resolved description of how to create physical DBAPI connections.

    Parameters
    ----------
    factory:
        A synchronous callable or ``"module.path:callable"`` reference.
        Importing the reference must not authenticate; authentication starts
        only when SQLAlchemy invokes the callable.
    dialect:
        SQLAlchemy dialect, for example
        ``"redshift+redshift_connector"``. It is deliberately explicit so a
        core-only installation does not pretend a Redshift driver is present.
    kwargs:
        Keyword arguments bound to every invocation. Values are never included
        in this object's representation.
    name:
        Optional non-sensitive label used in diagnostics.
    """

    factory: FactoryReference = field(repr=False)
    dialect: str
    kwargs: Mapping[str, Any] = field(default_factory=dict, repr=False)
    name: str | None = None

    def __post_init__(self) -> None:
        if not self.dialect or "://" in self.dialect:
            raise ConfigurationError(
                "dialect must be a SQLAlchemy dialect name, not a connection URL"
            )
        if isinstance(self.factory, str) and ":" not in self.factory:
            raise ConfigurationError(
                "factory references must use 'module.path:callable_name' syntax"
            )
        if not isinstance(self.factory, str) and not callable(self.factory):
            raise ConfigurationError("factory must be callable or a dotted reference")
        object.__setattr__(self, "kwargs", MappingProxyType(dict(self.kwargs)))

    @property
    def diagnostic_name(self) -> str:
        """Return a safe name that never contains bound argument values."""
        if self.name:
            return self.name
        if isinstance(self.factory, str):
            return self.factory
        return getattr(self.factory, "__qualname__", type(self.factory).__name__)

    def resolve(self) -> ConnectionFactory:
        """Resolve and validate the configured factory without invoking it."""
        factory = load_factory(self.factory) if isinstance(self.factory, str) else self.factory
        if not callable(factory):
            raise FactoryImportError(f"factory {self.diagnostic_name!r} is not callable")
        return factory

    def bind(self) -> Callable[[], DBAPIConnection]:
        """Return the zero-argument creator expected by SQLAlchemy."""
        factory = self.resolve()
        diagnostic_name = self.diagnostic_name
        kwargs = dict(self.kwargs)

        def creator() -> DBAPIConnection:
            try:
                connection = factory(**kwargs)
            except Exception:
                # Preserve provider-specific exception types and tracebacks. A
                # factory can opt into our typed AuthenticationError itself.
                raise
            if connection is None:
                raise NotebookConnectionError(
                    f"factory {diagnostic_name!r} returned None; expected an open DBAPI connection"
                )
            required = ("cursor", "commit", "rollback", "close")
            missing = [
                attribute
                for attribute in required
                if not callable(getattr(connection, attribute, None))
            ]
            if missing:
                close = getattr(connection, "close", None)
                if callable(close):
                    close()
                raise NotebookConnectionError(
                    f"factory {diagnostic_name!r} returned an incompatible connection; "
                    "missing DBAPI methods: " + ", ".join(missing)
                )
            return connection

        return creator


def load_factory(reference: str) -> ConnectionFactory:
    """Import ``reference`` without invoking it or starting authentication."""
    module_name, separator, attribute_path = reference.partition(":")
    if not separator or not module_name or not attribute_path:
        raise ConfigurationError(
            f"factory must use 'module.path:callable_name' syntax, got {reference!r}"
        )
    try:
        value: Any = importlib.import_module(module_name)
    except ImportError as exc:
        raise FactoryImportError(
            f"factory {reference!r} could not be imported; install the package providing "
            f"module {module_name!r}"
        ) from exc
    try:
        for part in attribute_path.split("."):
            value = getattr(value, part)
    except AttributeError as exc:
        raise FactoryImportError(
            f"factory {reference!r} does not resolve to an importable attribute"
        ) from exc
    if not callable(value):
        raise FactoryImportError(f"factory {reference!r} is not callable")
    return value
