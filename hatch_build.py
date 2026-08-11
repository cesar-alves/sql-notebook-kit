"""Build generated package artifacts when they are not already staged."""

from __future__ import annotations

import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

VSIX_PATH = Path("sql_notebook_kit/vscode/sql-notebook-kit-vscode.vsix")
PNPM_COMMANDS = (
    ("pnpm", "install", "--frozen-lockfile"),
    ("pnpm", "build"),
    ("pnpm", "package:vscode"),
)


def ensure_staged_vsix(root: Path) -> None:
    """Build the VS Code companion from the package root when necessary."""
    staged_vsix = root / VSIX_PATH
    if staged_vsix.is_file():
        return

    try:
        for command in PNPM_COMMANDS:
            subprocess.run(command, cwd=root, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "pnpm is required to build the VS Code companion from a Git or path "
            "source; install Node.js and pnpm, or install sql-notebook-kit from "
            "a published wheel or source distribution"
        ) from exc
    except subprocess.CalledProcessError as exc:
        command = " ".join(str(part) for part in exc.cmd)
        raise RuntimeError(
            f"failed to build the VS Code companion while running `{command}` "
            f"from `{root}`"
        ) from exc

    if not staged_vsix.is_file():
        raise RuntimeError(
            "the VS Code companion build completed without staging "
            f"`{VSIX_PATH}`"
        )


class CustomBuildHook(BuildHookInterface):
    """Ensure generated artifacts exist for every Python build target."""

    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        ensure_staged_vsix(Path(self.root))
