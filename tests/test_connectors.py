import sqlite3

import pytest

from sql_notebook_kit.connectors import FactorySpec, load_factory
from sql_notebook_kit.errors import (
    ConfigurationError,
    FactoryImportError,
    NotebookConnectionError,
)
from sql_notebook_kit.session import create_session


def test_factory_spec_binds_kwargs_without_exposing_values():
    calls = []

    def factory(secret):
        calls.append(secret)
        return sqlite3.connect(":memory:")

    spec = FactorySpec(factory=factory, dialect="sqlite", kwargs={"secret": "hidden"})
    connection = spec.bind()()
    connection.close()

    assert calls == ["hidden"]
    assert "hidden" not in repr(spec)


def test_factory_spec_rejects_urls_and_bad_references():
    with pytest.raises(ConfigurationError, match="connection URL"):
        FactorySpec(factory=lambda: None, dialect="sqlite://")
    with pytest.raises(ConfigurationError, match="module.path"):
        FactorySpec(factory="not_a_reference", dialect="sqlite")


def test_factory_spec_rejects_none_connection():
    spec = FactorySpec(factory=lambda: None, dialect="sqlite")
    with pytest.raises(NotebookConnectionError, match="returned None"):
        spec.bind()()


def test_factory_spec_rejects_incompatible_connection_shape():
    spec = FactorySpec(factory=object, dialect="sqlite")
    with pytest.raises(NotebookConnectionError, match="missing DBAPI methods"):
        spec.bind()()


def test_load_factory_supports_nested_attributes():
    assert load_factory("sqlite3:connect") is sqlite3.connect


def test_load_factory_reports_missing_modules_and_attributes():
    with pytest.raises(FactoryImportError, match="install the package"):
        load_factory("missing_factory_module:connect")
    with pytest.raises(FactoryImportError, match="does not resolve"):
        load_factory("sqlite3:missing")


def test_session_is_lazy_and_reconnect_invokes_a_fresh_factory():
    calls = []

    def factory():
        calls.append(1)
        return sqlite3.connect(":memory:")

    session = create_session(factory=factory, dialect="sqlite")
    assert calls == []

    session.login()
    assert len(calls) == 1
    session.reconnect()
    assert len(calls) == 2
    session.dispose()


def test_profile_and_explicit_factory_are_mutually_exclusive():
    with pytest.raises(ConfigurationError, match="cannot be combined"):
        create_session(profile="analytics", factory=lambda: None, dialect="sqlite")
