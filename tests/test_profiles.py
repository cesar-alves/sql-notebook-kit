import sys
import types

import pytest

from redshift_notebooks.adapters.config import load_profile
from redshift_notebooks.errors import ConfigurationError


def _write_profile(tmp_path, body):
    path = tmp_path / "config.toml"
    path.write_text(body)
    return path


def test_profile_loads_factory_without_importing_or_authenticating(monkeypatch, tmp_path):
    path = _write_profile(
        tmp_path,
        """
[profiles.analytics]
factory = "not_installed_until_later:connect"
dialect = "sqlite"

[profiles.analytics.factory_kwargs]
db_user = "<user-email>"
timeout = 30
""",
    )
    monkeypatch.setenv("REDSHIFT_NOTEBOOKS_CONFIG", str(path))
    spec = load_profile("analytics")

    assert spec.diagnostic_name == "analytics"
    assert spec.kwargs == {"db_user": "<user-email>", "timeout": 30}


def test_profile_rejects_secret_values_in_toml(monkeypatch, tmp_path):
    path = _write_profile(
        tmp_path,
        """
[profiles.analytics]
factory = "package:connect"
dialect = "sqlite"

[profiles.analytics.factory_kwargs]
api_token = "not-allowed"
""",
    )
    monkeypatch.setenv("REDSHIFT_NOTEBOOKS_CONFIG", str(path))

    with pytest.raises(ConfigurationError, match="secret field"):
        load_profile("analytics")


def test_profile_rejects_secret_values_from_parameter_namespace(monkeypatch, tmp_path):
    path = _write_profile(
        tmp_path,
        """
[profiles.analytics]
factory = "package:connect"
dialect = "sqlite"
""",
    )
    monkeypatch.setenv("REDSHIFT_NOTEBOOKS_CONFIG", str(path))
    monkeypatch.setenv("REDSHIFT_NOTEBOOKS_PARAM_API_TOKEN", "not-allowed")

    with pytest.raises(ConfigurationError, match="must use REDSHIFT_NOTEBOOKS_SECRET"):
        load_profile("analytics")


def test_profile_resolves_declared_secret_and_typed_environment_override(monkeypatch, tmp_path):
    path = _write_profile(
        tmp_path,
        """
[profiles.analytics]
factory = "fake_profile_factory:connect"
dialect = "sqlite"
secret_fields = ["token"]

[profiles.analytics.factory_kwargs]
timeout = 30
""",
    )
    monkeypatch.setenv("REDSHIFT_NOTEBOOKS_CONFIG", str(path))
    monkeypatch.setenv("REDSHIFT_NOTEBOOKS_PARAM_TIMEOUT", "45")
    monkeypatch.setenv("REDSHIFT_NOTEBOOKS_SECRET_TOKEN", "hidden")
    module = types.ModuleType("fake_profile_factory")
    module.connect = lambda **_kwargs: object()
    monkeypatch.setitem(sys.modules, "fake_profile_factory", module)

    spec = load_profile("analytics")

    assert spec.kwargs == {"timeout": 45, "token": "hidden"}
    assert "hidden" not in repr(spec)


def test_missing_declared_secret_is_actionable(monkeypatch, tmp_path):
    path = _write_profile(
        tmp_path,
        """
[profiles.analytics]
factory = "package:connect"
dialect = "sqlite"
secret_fields = ["token"]
""",
    )
    monkeypatch.setenv("REDSHIFT_NOTEBOOKS_CONFIG", str(path))
    monkeypatch.delenv("REDSHIFT_NOTEBOOKS_SECRET_TOKEN", raising=False)

    with pytest.raises(ConfigurationError, match="could not be resolved"):
        load_profile("analytics")
