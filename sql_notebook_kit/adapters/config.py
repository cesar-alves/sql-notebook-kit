"""Generic, config-driven adapter for named profiles and the legacy 0.1 API.

Every project-specific connection detail (which callable builds the DBAPI
connection, and what arguments it needs) lives in caller-supplied config, not
in this library — so ``sql_notebook_kit`` never hard-imports any particular
project's connection package.

New code should use :func:`load_profile` through
``sql_notebook_kit.create_session(profile=...)``. Profiles live under
``[profiles.<name>]`` and resolve non-secret environment overrides and declared
secret fields without importing the factory.

The legacy :func:`get_configured_engine` API resolves in this order:

1. Explicit function argument (``factory``, ``kwargs``)
2. Environment variable (``SQL_NOTEBOOK_KIT_FACTORY`` for ``factory``;
   ``SQL_NOTEBOOK_KIT_KWARG_<NAME>`` overrides individual ``kwargs`` entries)
3. A TOML table (default ``[connection]``) in a config file (default
   ``~/.config/sql_notebook_kit/config.toml``, override the path with
   ``SQL_NOTEBOOK_KIT_CONFIG``): a ``factory`` key plus a nested
   ``[connection.kwargs]`` table
4. Error, for ``factory`` only (``kwargs`` defaults to ``{}``)
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from sqlalchemy.engine import Engine

from sql_notebook_kit.adapters.base import BackendName
from sql_notebook_kit.connectors import ConnectionFactory, FactoryReference, load_factory
from sql_notebook_kit.engine import DEFAULT_DIALECT, make_engine
from sql_notebook_kit.errors import ConfigurationError

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "sql_notebook_kit" / "config.toml"
DEFAULT_TABLE = "connection"
SecretResolver = Callable[[str], str | None]
FORBIDDEN_SECRET_FIELDS = frozenset(
    {
        "access_key_id",
        "aws_access_key_id",
        "aws_secret_access_key",
        "client_secret",
        "password",
        "secret_access_key_id",
        "session_token",
        "token",
        "web_identity_token",
    }
)


@dataclass(frozen=True, slots=True)
class ProfileConfig:
    """Validated, secret-resolved inputs for one session profile."""

    name: str
    backend: BackendName | None = None
    connection_kwargs: Mapping[str, Any] = field(default_factory=dict, repr=False)
    factory: FactoryReference | None = field(default=None, repr=False)
    dialect: str | None = None
    factory_kwargs: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def diagnostic_name(self) -> str:
        return self.name

    @property
    def kwargs(self) -> Mapping[str, Any]:
        """Return the active value mapping for internal compatibility."""
        return self.connection_kwargs if self.backend is not None else self.factory_kwargs


def _is_secret_field(field: str) -> bool:
    normalized = field.lower()
    fragments = ("password", "token", "secret", "assertion", "access_key")
    return normalized in FORBIDDEN_SECRET_FIELDS or any(
        fragment in normalized for fragment in fragments
    )


def _load_config_table(table: str) -> dict:
    config_path = Path(os.environ.get("SQL_NOTEBOOK_KIT_CONFIG", DEFAULT_CONFIG_PATH))
    if not config_path.is_file():
        return {}
    with config_path.open("rb") as f:
        return tomllib.load(f).get(table, {})


def _resolve_factory(factory: str | None, config_table: dict, table: str) -> str:
    if factory is not None:
        return factory
    if "SQL_NOTEBOOK_KIT_FACTORY" in os.environ:
        return os.environ["SQL_NOTEBOOK_KIT_FACTORY"]
    if "factory" in config_table:
        return config_table["factory"]
    raise ValueError(
        "factory is required: pass it explicitly, set SQL_NOTEBOOK_KIT_FACTORY, "
        f"or add a 'factory' key to the [{table}] table of "
        f"{os.environ.get('SQL_NOTEBOOK_KIT_CONFIG', DEFAULT_CONFIG_PATH)}. "
        "It must be a dotted 'module.path:callable_name' string identifying a "
        "callable that returns a DBAPI connection."
    )


def _resolve_kwargs(kwargs: dict | None, config_table: dict) -> dict:
    resolved = dict(config_table.get("kwargs", {}))
    for key in list(resolved):
        env_var = f"SQL_NOTEBOOK_KIT_KWARG_{key.upper()}"
        if env_var in os.environ:
            resolved[key] = os.environ[env_var]
    if kwargs is not None:
        resolved.update(kwargs)
    return resolved


def _load_factory(factory: str) -> ConnectionFactory:
    # Compatibility helper retained for users importing this private function
    # from the 0.1.0 proof of concept.
    return load_factory(factory)


def _parse_environment_value(value: str) -> Any:
    """Parse JSON scalars/containers while retaining ordinary strings."""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _default_secret_resolver(field: str) -> str | None:
    return os.environ.get(f"SQL_NOTEBOOK_KIT_SECRET_{field.upper()}")


def _reject_toml_secrets(kwargs: Mapping[str, Any], profile: str) -> None:
    forbidden = sorted(key for key in kwargs if _is_secret_field(key))
    if forbidden:
        fields = ", ".join(forbidden)
        raise ConfigurationError(
            f"profile {profile!r} contains secret field(s) in TOML: {fields}; "
            "use SQL_NOTEBOOK_KIT_SECRET_<FIELD> or a SecretResolver"
        )


def load_profile(
    profile: str | None = None,
    *,
    secret_resolver: SecretResolver | None = None,
) -> ProfileConfig:
    """Load a named backend or factory profile without opening a connection.

    Profile selection uses the explicit name first, then
    ``SQL_NOTEBOOK_KIT_PROFILE``. Non-secret environment overrides use
    ``SQL_NOTEBOOK_KIT_PARAM_<FIELD>``. Secret values use the corresponding
    ``SQL_NOTEBOOK_KIT_SECRET_<FIELD>`` variable or ``secret_resolver``.
    """
    selected = profile or os.environ.get("SQL_NOTEBOOK_KIT_PROFILE")
    if not selected:
        raise ConfigurationError(
            "profile is required: pass a profile name or set SQL_NOTEBOOK_KIT_PROFILE"
        )
    config_path = Path(os.environ.get("SQL_NOTEBOOK_KIT_CONFIG", DEFAULT_CONFIG_PATH))
    if not config_path.is_file():
        raise ConfigurationError(f"configuration file does not exist: {config_path}")
    with config_path.open("rb") as config_file:
        document = tomllib.load(config_file)
    profiles = document.get("profiles", {})
    if selected not in profiles or not isinstance(profiles[selected], dict):
        raise ConfigurationError(f"profile {selected!r} was not found in {config_path}")
    table = dict(profiles[selected])
    backend = table.get("backend")
    factory = table.get("factory")
    dialect = table.get("dialect")
    if backend is not None and (factory is not None or dialect is not None):
        raise ConfigurationError(
            f"profile {selected!r} must declare either backend or factory plus dialect"
        )
    if backend is None and (not isinstance(factory, str) or not isinstance(dialect, str)):
        raise ConfigurationError(
            f"profile {selected!r} must define backend or string factory and dialect values"
        )
    valid_backends = {"redshift", "duckdb", "databricks", "bigquery"}
    if backend is not None and backend not in valid_backends:
        raise ConfigurationError(f"profile {selected!r} has unsupported backend {backend!r}")
    kwargs_key = "connection_kwargs" if backend is not None else "factory_kwargs"
    raw_kwargs = table.get(kwargs_key, {})
    if not isinstance(raw_kwargs, dict):
        raise ConfigurationError(f"profile {selected!r}.{kwargs_key} must be a TOML table")
    _reject_toml_secrets(raw_kwargs, selected)
    kwargs = dict(raw_kwargs)
    parameter_prefix = "SQL_NOTEBOOK_KIT_PARAM_"
    for env_name, value in os.environ.items():
        if env_name.startswith(parameter_prefix):
            key = env_name.removeprefix(parameter_prefix).lower()
            if _is_secret_field(key):
                raise ConfigurationError(
                    f"secret field {key!r} must use SQL_NOTEBOOK_KIT_SECRET_<FIELD>, "
                    "not SQL_NOTEBOOK_KIT_PARAM_<FIELD>"
                )
            kwargs[key] = _parse_environment_value(value)

    fields = table.get("secret_fields", [])
    if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
        raise ConfigurationError(f"profile {selected!r}.secret_fields must be a list of names")
    invalid_fields = [
        field for field in fields if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field)
    ]
    if invalid_fields:
        raise ConfigurationError(f"profile {selected!r}.secret_fields contains invalid field names")
    resolve_secret = secret_resolver or _default_secret_resolver
    for secret_field in fields:
        secret_value = resolve_secret(secret_field)
        if secret_value is None:
            raise ConfigurationError(
                f"secret {secret_field!r} required by profile {selected!r} could not be resolved"
            )
        kwargs[secret_field] = secret_value
    if backend is not None:
        return ProfileConfig(
            name=selected,
            backend=cast(BackendName, backend),
            connection_kwargs=kwargs,
        )
    return ProfileConfig(
        name=selected,
        factory=factory,
        dialect=dialect,
        factory_kwargs=kwargs,
    )


def get_configured_engine(
    factory: str | None = None,
    kwargs: dict | None = None,
    *,
    table: str = DEFAULT_TABLE,
    dialect: str = DEFAULT_DIALECT,
) -> Engine:
    """Build a SQLAlchemy Engine from a config-resolved connection factory.

    See module docstring for how ``factory``/``kwargs`` are resolved when not
    passed explicitly.
    """
    config_table = _load_config_table(table)
    factory = _resolve_factory(factory, config_table, table)
    resolved_kwargs = _resolve_kwargs(kwargs, config_table)

    factory_fn = _load_factory(factory)
    return make_engine(lambda: factory_fn(**resolved_kwargs), dialect=dialect)
