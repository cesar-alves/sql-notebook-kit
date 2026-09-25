#!/usr/bin/env python3
"""Install, smoke, and uninstall an exact wheel in a disposable environment."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[a-z]+[0-9]+)?")


def _venv_commands(root: Path) -> tuple[Path, Path]:
    scripts = root / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    command = scripts / ("sql-notebook-kit.exe" if os.name == "nt" else "sql-notebook-kit")
    return python, command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        parser.error("wheel must be an existing .whl file")
    if not VERSION_PATTERN.fullmatch(args.expected_version):
        parser.error("expected version must be a normalized release version")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        environment_root = root / "environment"
        venv.EnvBuilder(with_pip=True).create(environment_root)
        python, command = _venv_commands(environment_root)
        restricted_environment = dict(os.environ)
        for name in ("PYTHONHOME", "PYTHONPATH", "UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV"):
            restricted_environment.pop(name, None)
        restricted_environment["PATH"] = str(python.parent)
        requirement = f"sql-notebook-kit[duckdb,viz] @ {wheel.as_uri()}"
        # Both user-controlled values were constrained above; each remains one argv
        # element, and subprocess never invokes a shell.
        subprocess.run(
            [str(python), "-m", "pip", "install", requirement, "jupyterlab>=4,<5"],  # nosemgrep
            check=True,
            env=restricted_environment,
        )
        jupyter_extension = (
            environment_root
            / "share"
            / "jupyter"
            / "labextensions"
            / "@sql-notebook-kit"
            / "jupyterlab"
        )
        assert jupyter_extension.is_dir()
        smoke_directory = root / "smoke"
        smoke_directory.mkdir()
        subprocess.run(
            [  # nosemgrep
                str(python),
                str(ROOT / "scripts" / "installed_smoke.py"),
                "--expected-version",
                args.expected_version,
            ],
            cwd=smoke_directory,
            check=True,
            env=restricted_environment,
        )

        if os.name != "nt":
            state = root / "editor-state.json"
            fake_editor = root / "editor cli with spaces"
            fake_editor.write_text(
                "#!/usr/bin/env python3\n"
                "import json, pathlib, sys, zipfile\n"
                f"state = pathlib.Path({str(state)!r})\n"
                "if '--install-extension' in sys.argv:\n"
                "    value = pathlib.Path(sys.argv[sys.argv.index('--install-extension') + 1])\n"
                "    with zipfile.ZipFile(value) as archive:\n"
                "        archive.getinfo('extension/package.json')\n"
                "    state.write_text(json.dumps({'installed': True}))\n"
                "    print('installed')\n"
                "elif '--list-extensions' in sys.argv and state.exists():\n"
                f"    print('sql-notebook-kit.sql-notebook-kit-vscode@{args.expected_version}')\n"
            )
            fake_editor.chmod(fake_editor.stat().st_mode | stat.S_IXUSR)
            subprocess.run(
                [str(command), "vscode", "install", "--cli", str(fake_editor)], check=True
            )
            subprocess.run(
                [str(command), "vscode", "status", "--cli", str(fake_editor)], check=True
            )

        sentinel = environment_root / "user-data-must-survive.txt"
        sentinel.write_text(json.dumps({"owned_by": "user"}))
        subprocess.run(
            [str(python), "-m", "pip", "uninstall", "--yes", "sql-notebook-kit"],
            check=True,
            env=restricted_environment,
        )
        assert sentinel.is_file()
        assert not command.exists()
        probe = subprocess.run(
            [str(python), "-c", "import sql_notebook_kit"],
            capture_output=True,
            check=False,
            cwd=smoke_directory,
            env=restricted_environment,
        )
        assert probe.returncode != 0
        assert not jupyter_extension.exists()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
