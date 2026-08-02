"""Generic, config-driven adapter: build an Engine from any connection factory.

Every project-specific connection detail (which callable builds the DBAPI
connection, and what arguments it needs) lives in caller-supplied config, not
in this library — so ``redshift_notebooks`` never hard-imports any particular
project's connection package.

Configuration is resolved in this order, first match wins:

1. Explicit function argument (``factory``, ``kwargs``)
2. Environment variable (``REDSHIFT_NOTEBOOKS_FACTORY`` for ``factory``;
   ``REDSHIFT_NOTEBOOKS_KWARG_<NAME>`` overrides individual ``kwargs`` entries)
3. A TOML table (default ``[connection]``) in a config file (default
   ``~/.config/redshift_notebooks/config.toml``, override the path with
   ``REDSHIFT_NOTEBOOKS_CONFIG``): a ``factory`` key plus a nested
   ``[connection.kwargs]`` table
4. Error, for ``factory`` only (``kwargs`` defaults to ``{}``)
"""

from __future__ import annotations

import importlib
import os
import tomllib
from pathlib import Path

from redshift_notebooks.engine import DEFAULT_DIALECT, make_engine

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "redshift_notebooks" / "config.toml"
DEFAULT_TABLE = "connection"


def _load_config_table(table: str) -> dict:
    config_path = Path(os.environ.get("REDSHIFT_NOTEBOOKS_CONFIG", DEFAULT_CONFIG_PATH))
    if not config_path.is_file():
        return {}
    with config_path.open("rb") as f:
        return tomllib.load(f).get(table, {})


def _resolve_factory(factory: str | None, config_table: dict, table: str) -> str:
    if factory is not None:
        return factory
    if "REDSHIFT_NOTEBOOKS_FACTORY" in os.environ:
        return os.environ["REDSHIFT_NOTEBOOKS_FACTORY"]
    if "factory" in config_table:
        return config_table["factory"]
    raise ValueError(
        "factory is required: pass it explicitly, set REDSHIFT_NOTEBOOKS_FACTORY, "
        f"or add a 'factory' key to the [{table}] table of "
        f"{os.environ.get('REDSHIFT_NOTEBOOKS_CONFIG', DEFAULT_CONFIG_PATH)}. "
        "It must be a dotted 'module.path:callable_name' string identifying a "
        "callable that returns a DBAPI connection."
    )


def _resolve_kwargs(kwargs: dict | None, config_table: dict) -> dict:
    resolved = dict(config_table.get("kwargs", {}))
    for key in list(resolved):
        env_var = f"REDSHIFT_NOTEBOOKS_KWARG_{key.upper()}"
        if env_var in os.environ:
            resolved[key] = os.environ[env_var]
    if kwargs is not None:
        resolved.update(kwargs)
    return resolved


def _load_factory(factory: str):
    module_name, _, attr_name = factory.partition(":")
    if not attr_name:
        raise ValueError(
            f"factory must be a 'module.path:callable_name' string, got {factory!r}"
        )
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ImportError(
            f"factory {factory!r} could not be imported: no module named "
            f"{module_name!r}. Install the package that provides it."
        ) from exc
    return getattr(module, attr_name)


def get_configured_engine(
    factory: str | None = None,
    kwargs: dict | None = None,
    *,
    table: str = DEFAULT_TABLE,
    dialect: str = DEFAULT_DIALECT,
):
    """Build a SQLAlchemy Engine from a config-resolved connection factory.

    See module docstring for how ``factory``/``kwargs`` are resolved when not
    passed explicitly.
    """
    config_table = _load_config_table(table)
    factory = _resolve_factory(factory, config_table, table)
    resolved_kwargs = _resolve_kwargs(kwargs, config_table)

    factory_fn = _load_factory(factory)
    return make_engine(lambda: factory_fn(**resolved_kwargs), dialect=dialect)
