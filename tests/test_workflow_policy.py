import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
USES = re.compile(r"\buses:\s*[^@\s]+@([^\s#]+)")


def test_all_third_party_actions_are_pinned_to_full_commit_shas():
    failures = []
    for path in WORKFLOWS:
        for line_number, line in enumerate(path.read_text().splitlines(), 1):
            if (match := USES.search(line)) and re.fullmatch(
                r"[0-9a-f]{40}", match.group(1)
            ) is None:
                failures.append(f"{path.name}:{line_number}: {match.group(1)}")
    assert not failures, "mutable workflow actions: " + ", ".join(failures)


def test_gitleaks_container_is_pinned_by_digest_and_scans_history():
    expected = (
        "ghcr.io/gitleaks/gitleaks@sha256:"
        "507de9682470025fb3e7f57fe4c4ca8263d81369e027b6538b8a252a9c0371d4"
    )
    for name in ("ci.yml", "security.yml"):
        workflow = (ROOT / ".github" / "workflows" / name).read_text()
        assert expected in workflow
        assert "git --no-banner --redact /repo" in workflow
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "Prove Gitleaks rejects a synthetic test secret" in ci
    assert "Gitleaks accepted the synthetic secret fixture" in ci


def test_security_jobs_validate_cyclonedx_sboms():
    for name in ("ci.yml", "security.yml"):
        workflow = (ROOT / ".github" / "workflows" / name).read_text()
        assert "check-jsonschema==0.38.0" in workflow
        assert "bom-1.6.schema.json" in workflow
        assert "python.cdx.json javascript.cdx.json" in workflow


def test_pull_request_ci_does_not_duplicate_feature_push_runs():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    trigger = workflow.split("permissions:", 1)[0]
    assert "pull_request:" in trigger
    assert re.search(r"^\s+push:", trigger, re.M) is None
    assert "cancel-in-progress: true" in workflow
    assert "ci:merge-ready" in workflow


def test_production_is_manual_only_and_reuses_source_run_artifacts():
    workflow = (ROOT / ".github" / "workflows" / "release-production.yml").read_text()
    trigger = workflow.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger
    assert re.search(r"^\s+(?:push|release):", trigger, re.M) is None
    assert "source_run_id" in workflow
    assert "gh run download" in workflow
    assert "uv build" not in workflow
    assert "sha256sum --check" in workflow
    assert 'git checkout --detach "$commit"' in workflow


def test_no_workflow_changes_repository_visibility():
    text = "\n".join(path.read_text().lower() for path in WORKFLOWS)
    assert "--visibility" not in text
    assert "visibility:" not in text


def test_tag_workflow_cannot_publish_to_production_pypi():
    workflow = (ROOT / ".github" / "workflows" / "release-rehearsal.yml").read_text()
    assert "repository-url: https://test.pypi.org/legacy/" in workflow
    assert "environment:\n      name: testpypi" in workflow
    assert "environment:\n      name: pypi" not in workflow


def test_production_deploys_versioned_docs_only_after_publish():
    workflow = (ROOT / ".github" / "workflows" / "release-production.yml").read_text()
    assert "needs: [verify-bundle, publish]" in workflow
    assert "mike deploy --push --update-aliases" in workflow
    assert "actions/deploy-pages@" in workflow
    assert "/${VERSION}/" in workflow


def test_merge_ready_docs_job_checks_links():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "lycheeverse/lychee-action@" in workflow
    assert "--offline" in workflow
    assert "failIfEmpty: true" in workflow


def test_frontend_artifact_jobs_rebuild_before_drift_check():
    for name in ("ci.yml", "release-rehearsal.yml"):
        workflow = (ROOT / ".github" / "workflows" / name).read_text()
        assert "pnpm build:artifacts" in workflow
    assert (
        "git diff --exit-code -- sql_notebook_kit/labextension sql_notebook_kit/vscode"
        in (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    )


def test_compact_ci_enforces_release_notes_with_a_named_exemption():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "scripts/check_release_notes.py" in workflow
    assert "release-note:exempt" in workflow
    assert "github.event.pull_request.base.sha" in workflow


def test_platform_smokes_install_the_shipped_visualization_stack():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "lets-plot" not in workflow
    assert "ipywidgets nbformat plotly jupyterlab" in workflow
    assert "'sqlframe[duckdb]'" in workflow
