"""Command-line utilities shipped with sql-notebook-kit."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Sequence
from importlib.metadata import version
from importlib.resources import as_file, files
from pathlib import Path

EXTENSION_ID = "sql-notebook-kit.sql-notebook-kit-vscode"
EDITOR_COMMANDS = {
    "code": "code",
    "code-insiders": "code-insiders",
    "codium": "codium",
}


def _vsix() -> Path:
    resource = files("sql_notebook_kit").joinpath(
        "vscode", "sql-notebook-kit-vscode.vsix"
    )
    with as_file(resource) as path:
        if not path.is_file():
            raise RuntimeError(
                "the installed Python package does not contain the VS Code companion"
            )
        return Path(path)


def _editor_command(editor: str, override: str | None) -> str:
    if override:
        command = shutil.which(override) if not Path(override).is_file() else override
        if command:
            return command
        raise RuntimeError(f"VS Code CLI {override!r} was not found")
    candidates = EDITOR_COMMANDS.values() if editor == "auto" else (EDITOR_COMMANDS[editor],)
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError(
        "no supported VS Code CLI was found; add code, code-insiders, or codium "
        "to PATH, or pass --cli"
    )


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sql-notebook-kit")
    commands = parser.add_subparsers(dest="command", required=True)
    vscode = commands.add_parser("vscode", help="manage the bundled VS Code companion")
    actions = vscode.add_subparsers(dest="action", required=True)
    for action in ("install", "status"):
        item = actions.add_parser(action)
        item.add_argument(
            "--editor", choices=("auto", *EDITOR_COMMANDS), default="auto"
        )
        item.add_argument("--cli", help="path or command name for a compatible VS Code CLI")
    actions.add_parser("path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "path":
            print(_vsix())
            return 0
        editor = _editor_command(args.editor, args.cli)
        if args.action == "install":
            result = _run([editor, "--install-extension", str(_vsix()), "--force"])
            print(result.stdout.strip() or f"Installed {EXTENSION_ID} with {editor}.")
            print("Reload the VS Code window before using notebook visualizations.")
            return 0
        result = _run([editor, "--list-extensions", "--show-versions"])
        match = next(
            (line for line in result.stdout.splitlines() if line.lower().startswith(EXTENSION_ID)),
            None,
        )
        if match:
            expected = f"{EXTENSION_ID}@{version('sql-notebook-kit')}"
            if match.lower() == expected.lower():
                print(f"Installed and current: {match}")
                print(f"Bundled VSIX: {_vsix()}")
                return 0
            print(f"Version mismatch: installed {match}; bundled {expected}")
            return 1
        print(f"Not installed for {editor}: {EXTENSION_ID}")
        return 1
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        print(f"sql-notebook-kit: {detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
