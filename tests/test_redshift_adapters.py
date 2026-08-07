import pytest

from sql_notebook_kit.adapters import redshift
from sql_notebook_kit.errors import ConfigurationError


def test_browser_azure_sso_maps_documented_driver_options(monkeypatch):
    captured = {}
    monkeypatch.setattr(redshift, "_connect", lambda **kwargs: captured.update(kwargs) or object())

    redshift.browser_azure_sso(
        host="<cluster-host>",
        database="<database-name>",
        cluster_identifier="<cluster-name>",
        idp_tenant="<tenant-id>",
        client_id="<client-id>",
    )

    assert captured["iam"] is True
    assert captured["credentials_provider"] == "BrowserAzureCredentialsProvider"
    assert captured["listen_port"] == 7890


def test_identity_center_sso_maps_documented_driver_options(monkeypatch):
    captured = {}
    monkeypatch.setattr(redshift, "_connect", lambda **kwargs: captured.update(kwargs) or object())

    redshift.identity_center_sso(
        host="<cluster-host>",
        database="<database-name>",
        idc_region="<aws-region>",
        issuer_url="<identity-center-issuer-url>",
    )

    assert captured["credentials_provider"] == "BrowserIdcAuthPlugin"
    assert captured["idc_client_display_name"] == "sql-notebook-kit"


def test_sso_timeout_has_a_safe_minimum():
    with pytest.raises(ConfigurationError, match="at least 10"):
        redshift.browser_azure_sso(
            host="<cluster-host>",
            database="<database-name>",
            cluster_identifier="<cluster-name>",
            idp_tenant="<tenant-id>",
            client_id="<client-id>",
            idp_response_timeout=5,
        )
