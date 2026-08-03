from pathlib import Path
from subprocess import CompletedProcess

from redshift_notebooks import cli


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
