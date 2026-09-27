from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess

import pytest

from sql_notebook_kit import cli


def test_vscode_install_uses_selected_cli_without_a_shell(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli, "_editor_command", lambda editor, override: "/usr/bin/code")
    monkeypatch.setattr(cli, "_vsix", lambda: Path("/package/companion.vsix"))
    monkeypatch.setattr(
        cli,
        "_run",
        lambda command: calls.append(command) or CompletedProcess(command, 0, "installed", ""),
    )

    assert cli.main(["vscode", "install"]) == 0
    assert calls == [[
        "/usr/bin/code", "--install-extension", "/package/companion.vsix", "--force"
    ]]
    assert "Reload the VS Code window" in capsys.readouterr().out


def test_vscode_status_reports_missing_extension(monkeypatch):
    monkeypatch.setattr(cli, "_editor_command", lambda editor, override: "code")
    monkeypatch.setattr(
        cli, "_run", lambda command: CompletedProcess(command, 0, "publisher.other@1.0\n", "")
    )
    assert cli.main(["vscode", "status"]) == 1


def test_vscode_status_compares_the_bundled_version(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_editor_command", lambda editor, override: "code")
    monkeypatch.setattr(cli, "_vsix", lambda: Path("/package/companion.vsix"))
    monkeypatch.setattr(
        cli,
        "_run",
        lambda command: CompletedProcess(
            command, 0, f"{cli.EXTENSION_ID}@0.1.0\n", ""
        ),
    )
    assert cli.main(["vscode", "status"]) == 0
    assert "Installed and current" in capsys.readouterr().out


def test_editor_discovery_reports_a_missing_executable(monkeypatch, capsys):
    monkeypatch.setattr(cli.shutil, "which", lambda _command: None)
    assert cli.main(["vscode", "status", "--editor", "code"]) == 2
    assert "no supported VS Code CLI" in capsys.readouterr().err


def test_explicit_cli_path_with_spaces_is_one_subprocess_argument(monkeypatch, tmp_path):
    editor = tmp_path / "editor cli"
    editor.write_text("")
    calls = []
    monkeypatch.setattr(cli, "_vsix", lambda: Path("/package/companion.vsix"))
    monkeypatch.setattr(
        cli,
        "_run",
        lambda command: calls.append(command) or CompletedProcess(command, 0, "installed", ""),
    )
    assert cli.main(["vscode", "install", "--cli", str(editor)]) == 0
    assert calls[0][0] == str(editor)


def test_subprocess_failure_does_not_echo_sensitive_stderr(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_editor_command", lambda _editor, _override: "code")
    monkeypatch.setattr(
        cli,
        "_run",
        lambda command: (_ for _ in ()).throw(
            CalledProcessError(9, command, stderr="token=usable-secret")
        ),
    )
    assert cli.main(["vscode", "status"]) == 2
    error = capsys.readouterr().err
    assert "exit status 9" in error
    assert "usable-secret" not in error


def test_vscode_path_rejects_a_malformed_vsix(monkeypatch, tmp_path, capsys):
    malformed = tmp_path / "companion.vsix"
    malformed.write_text("not a zip")

    class Resource:
        def joinpath(self, *_parts):
            return malformed

    class Context:
        def __enter__(self):
            return malformed

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(cli, "files", lambda _package: Resource())
    monkeypatch.setattr(cli, "as_file", lambda _resource: Context())
    assert cli.main(["vscode", "path"]) == 2
    assert "malformed" in capsys.readouterr().err


def test_unknown_editor_choice_is_rejected_by_argparse():
    with pytest.raises(SystemExit):
        cli.main(["vscode", "status", "--editor", "unknown"])
