"""Build-time checks for generated package artifacts."""

from __future__ import annotations

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

VSIX_PATH = Path("sql_notebook_kit/vscode/sql-notebook-kit-vscode.vsix")


def require_staged_vsix(root: Path) -> None:
    """Require the generated VS Code companion before packaging."""
    if not (root / VSIX_PATH).is_file():
        raise RuntimeError(
            "the staged VS Code companion is missing; run "
            "`pnpm install --frozen-lockfile`, `pnpm build`, and "
            "`pnpm package:vscode` before building the Python package"
        )


class CustomBuildHook(BuildHookInterface):
    """Validate generated artifacts for every Python distribution target."""

    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        if version != "editable":
            require_staged_vsix(Path(self.root))
