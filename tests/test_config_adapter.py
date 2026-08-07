import sys
import types

import pytest

from sql_notebook_kit.adapters import config


def _install_fake_module(monkeypatch, recorded_calls):
    def fake_get_connection(db_user, preferred_role=None):
        recorded_calls.append((db_user, preferred_role))
        return object()

    fake_module = types.ModuleType("fake_conn_pkg")
    fake_module.get_connection = fake_get_connection
    monkeypatch.setitem(sys.modules, "fake_conn_pkg", fake_module)


def _capture_connection_factory(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        config,
        "make_engine",
        lambda connection_factory, dialect=None: captured.setdefault("factory", connection_factory),
    )
    return captured


def test_raises_helpful_error_when_factory_module_missing():
    with pytest.raises(ImportError, match="no_such_module_xyz"):
        config.get_configured_engine(factory="no_such_module_xyz:get_connection")


def test_explicit_factory_wins_over_env_and_config(monkeypatch, tmp_path):
    monkeypatch.setenv("SQL_NOTEBOOK_KIT_FACTORY", "env_pkg:get_connection")
    config_path = tmp_path / "config.toml"
    config_path.write_text('[connection]\nfactory = "file_pkg:get_connection"\n')
    monkeypatch.setenv("SQL_NOTEBOOK_KIT_CONFIG", str(config_path))

    calls = []
    _install_fake_module(monkeypatch, calls)
    captured = _capture_connection_factory(monkeypatch)

    config.get_configured_engine(
        factory="fake_conn_pkg:get_connection", kwargs={"db_user": "arg-user"}
    )
    captured["factory"]()

    assert calls == [("arg-user", None)]


def test_env_var_wins_over_config_file(monkeypatch, tmp_path):
    calls = []
    _install_fake_module(monkeypatch, calls)
    captured = _capture_connection_factory(monkeypatch)
    monkeypatch.setenv("SQL_NOTEBOOK_KIT_FACTORY", "fake_conn_pkg:get_connection")
    config_path = tmp_path / "config.toml"
    config_path.write_text('[connection]\nfactory = "file_pkg:get_connection"\n')
    monkeypatch.setenv("SQL_NOTEBOOK_KIT_CONFIG", str(config_path))

    config.get_configured_engine(kwargs={"db_user": "env-user"})
    captured["factory"]()

    assert calls == [("env-user", None)]


def test_config_file_used_when_no_arg_or_env(monkeypatch, tmp_path):
    calls = []
    _install_fake_module(monkeypatch, calls)
    captured = _capture_connection_factory(monkeypatch)
    monkeypatch.delenv("SQL_NOTEBOOK_KIT_FACTORY", raising=False)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[connection]\n"
        'factory = "fake_conn_pkg:get_connection"\n'
        "\n"
        "[connection.kwargs]\n"
        'db_user = "file-user"\n'
        'preferred_role = "analyst"\n'
    )
    monkeypatch.setenv("SQL_NOTEBOOK_KIT_CONFIG", str(config_path))

    config.get_configured_engine()
    captured["factory"]()

    assert calls == [("file-user", "analyst")]


def test_kwarg_env_var_overrides_config_file_kwarg(monkeypatch, tmp_path):
    calls = []
    _install_fake_module(monkeypatch, calls)
    captured = _capture_connection_factory(monkeypatch)
    monkeypatch.delenv("SQL_NOTEBOOK_KIT_FACTORY", raising=False)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[connection]\n"
        'factory = "fake_conn_pkg:get_connection"\n'
        "\n"
        "[connection.kwargs]\n"
        'db_user = "file-user"\n'
    )
    monkeypatch.setenv("SQL_NOTEBOOK_KIT_CONFIG", str(config_path))
    monkeypatch.setenv("SQL_NOTEBOOK_KIT_KWARG_DB_USER", "env-user")

    config.get_configured_engine()
    captured["factory"]()

    assert calls == [("env-user", None)]


def test_raises_value_error_when_factory_cannot_be_resolved(monkeypatch, tmp_path):
    monkeypatch.delenv("SQL_NOTEBOOK_KIT_FACTORY", raising=False)
    monkeypatch.setenv("SQL_NOTEBOOK_KIT_CONFIG", str(tmp_path / "missing.toml"))

    with pytest.raises(ValueError, match="factory"):
        config.get_configured_engine()
