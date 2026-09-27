"""Build generated package artifacts when they are not already staged."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

VSIX_PATH = Path("sql_notebook_kit/vscode/sql-notebook-kit-vscode.vsix")
JUPYTERLAB_PATH = Path("sql_notebook_kit/labextension")
JUPYTERLAB_STAGING_PATH = Path(".release_artifacts/jupyterlab")
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
    if os.environ.get("SQL_NOTEBOOK_KIT_REQUIRE_STAGED_FRONTENDS") == "1":
        raise RuntimeError(
            "the release build requires the staged VS Code companion and will not "
            "invoke a frontend toolchain"
        )

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


def stage_jupyterlab_shared_data(root: Path) -> None:
    """Stage one wheel-only copy of the JupyterLab shared-data payload."""
    source = root / JUPYTERLAB_PATH
    target = root / JUPYTERLAB_STAGING_PATH
    if not source.is_dir():
        raise RuntimeError(f"the staged JupyterLab extension is missing: `{source}`")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


class CustomBuildHook(BuildHookInterface):
    """Ensure generated artifacts exist for every Python build target."""

    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        ensure_staged_vsix(Path(self.root))
        stage_jupyterlab_shared_data(Path(self.root))
