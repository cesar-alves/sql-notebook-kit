from scripts.check_release_notes import needs_release_note


def test_runtime_frontend_and_public_docs_require_release_notes():
    assert needs_release_note(["sql_notebook_kit/session.py"])
    assert needs_release_note(["frontend/vscode/src/extension.ts"])
    assert needs_release_note(["docs/compatibility.md"])
    assert needs_release_note(["README.md"])
    assert needs_release_note(["pyproject.toml"])


def test_internal_maintenance_does_not_require_release_notes():
    assert not needs_release_note(["tests/test_session.py", ".github/dependabot.yml"])
