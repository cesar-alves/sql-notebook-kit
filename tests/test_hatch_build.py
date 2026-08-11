import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parents[1]


def load_hatch_build(monkeypatch):
    interface = ModuleType("hatchling.builders.hooks.plugin.interface")
    interface.BuildHookInterface = object
    modules = {
        "hatchling": ModuleType("hatchling"),
        "hatchling.builders": ModuleType("hatchling.builders"),
        "hatchling.builders.hooks": ModuleType("hatchling.builders.hooks"),
        "hatchling.builders.hooks.plugin": ModuleType("hatchling.builders.hooks.plugin"),
        "hatchling.builders.hooks.plugin.interface": interface,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location("tested_hatch_build", ROOT / "hatch_build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_vsix_skips_frontend_build(monkeypatch, tmp_path):
    hook = load_hatch_build(monkeypatch)
    staged_vsix = tmp_path / hook.VSIX_PATH
    staged_vsix.parent.mkdir(parents=True)
    staged_vsix.touch()
    monkeypatch.setattr(hook.subprocess, "run", lambda *args, **kwargs: pytest.fail())

    hook.ensure_staged_vsix(tmp_path)


def test_missing_vsix_builds_from_package_root(monkeypatch, tmp_path):
    hook = load_hatch_build(monkeypatch)
    calls = []

    def run(command, *, cwd, check):
        calls.append((command, cwd, check))
        if command == hook.PNPM_COMMANDS[-1]:
            staged_vsix = tmp_path / hook.VSIX_PATH
            staged_vsix.parent.mkdir(parents=True)
            staged_vsix.touch()

    monkeypatch.setattr(hook.subprocess, "run", run)

    hook.ensure_staged_vsix(tmp_path)

    assert calls == [(command, tmp_path, True) for command in hook.PNPM_COMMANDS]


def test_missing_pnpm_has_source_install_guidance(monkeypatch, tmp_path):
    hook = load_hatch_build(monkeypatch)

    def missing_pnpm(*args, **kwargs):
        raise FileNotFoundError("pnpm")

    monkeypatch.setattr(hook.subprocess, "run", missing_pnpm)

    with pytest.raises(RuntimeError, match="Git or path source"):
        hook.ensure_staged_vsix(tmp_path)


def test_failed_frontend_command_reports_command_and_root(monkeypatch, tmp_path):
    hook = load_hatch_build(monkeypatch)
    failed_command = hook.PNPM_COMMANDS[1]

    def fail_on_build(command, *, cwd, check):
        if command == failed_command:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(hook.subprocess, "run", fail_on_build)

    with pytest.raises(RuntimeError, match=r"pnpm build.*" + str(tmp_path)):
        hook.ensure_staged_vsix(tmp_path)


def test_build_must_stage_vsix(monkeypatch, tmp_path):
    hook = load_hatch_build(monkeypatch)
    monkeypatch.setattr(hook.subprocess, "run", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="completed without staging"):
        hook.ensure_staged_vsix(tmp_path)
