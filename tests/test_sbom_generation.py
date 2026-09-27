from pathlib import Path

from scripts.license_report_to_sbom import build_sbom, validate_shape


def test_python_sbom_is_sanitized_and_binds_artifact_hash(tmp_path: Path):
    artifact = tmp_path / "package.whl"
    artifact.write_bytes(b"release bytes")
    report = [
        {
            "Name": "Example_Package",
            "Version": "1.2.3",
            "License": "MIT",
            "Location": "/home/private/environment",
        }
    ]
    sbom = build_sbom(report, ecosystem="pypi", project_version="0.1.0", artifacts=[artifact])
    validate_shape(sbom)
    rendered = str(sbom)
    assert "/home/private" not in rendered
    assert "pkg:pypi/example-package@1.2.3" in rendered
    assert "artifact:package.whl" in rendered


def test_pnpm_sbom_flattens_license_groups_without_install_paths():
    report = {
        "MIT": [
            {
                "name": "@scope/example",
                "versions": ["2.0.0"],
                "paths": ["/home/private/node_modules/example"],
            }
        ]
    }
    sbom = build_sbom(report, ecosystem="npm", project_version="0.1.0", artifacts=[])
    validate_shape(sbom)
    rendered = str(sbom)
    assert "/home/private" not in rendered
    assert "pkg:npm/%40scope/example@2.0.0" in rendered


def test_pnpm_sbom_uses_reviewed_license_override():
    report = {"Unknown": [{"name": "missing-metadata", "versions": ["1.0.0"]}]}
    sbom = build_sbom(
        report,
        ecosystem="npm",
        project_version="0.1.0",
        artifacts=[],
        overrides={"missing-metadata": "MIT"},
    )
    assert sbom["components"][0]["licenses"] == [{"license": {"name": "MIT"}}]
