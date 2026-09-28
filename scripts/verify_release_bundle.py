#!/usr/bin/env python3
"""Verify that SHA256SUMS completely and safely binds a release bundle."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path, PurePosixPath

MANIFEST_LINE = re.compile(
    r"^(?P<digest>[0-9a-f]{64})  (?P<path>(?:python|assets)/[^\r\n]+)$"
)
EXPECTED_ROOT_ENTRIES = {"SHA256SUMS", "assets", "python"}


def verify_bundle(root: Path) -> list[str]:
    errors: list[str] = []
    manifest = root / "SHA256SUMS"
    if not root.is_dir():
        return [f"bundle directory does not exist: {root}"]
    if manifest.is_symlink() or not manifest.is_file():
        return ["bundle has no regular SHA256SUMS manifest"]

    root_entries = {path.name for path in root.iterdir()}
    if unexpected := root_entries - EXPECTED_ROOT_ENTRIES:
        errors.append("bundle root contains unlisted entries: " + ", ".join(sorted(unexpected)))
    if missing := EXPECTED_ROOT_ENTRIES - root_entries:
        errors.append("bundle root is missing entries: " + ", ".join(sorted(missing)))

    expected: dict[str, str] = {}
    lines = manifest.read_text(encoding="utf-8").splitlines()
    if not lines:
        errors.append("SHA256SUMS is empty")
    for number, line in enumerate(lines, 1):
        match = MANIFEST_LINE.fullmatch(line)
        if match is None:
            errors.append(f"SHA256SUMS line {number} is malformed")
            continue
        relative = PurePosixPath(match.group("path"))
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"SHA256SUMS line {number} has an unsafe path")
            continue
        name = relative.as_posix()
        if name in expected:
            errors.append(f"SHA256SUMS lists {name} more than once")
            continue
        expected[name] = match.group("digest")

    discovered: set[str] = set()
    for directory_name in ("python", "assets"):
        directory = root / directory_name
        if not directory.is_dir() or directory.is_symlink():
            continue
        for path in directory.rglob("*"):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                errors.append(f"bundle contains a symbolic link: {relative}")
            elif path.is_file():
                discovered.add(relative)

    if unlisted := discovered - expected.keys():
        errors.append(
            "bundle contains files absent from SHA256SUMS: "
            + ", ".join(sorted(unlisted))
        )
    if absent := expected.keys() - discovered:
        errors.append("SHA256SUMS lists files absent from the bundle: " + ", ".join(sorted(absent)))

    for name in sorted(discovered & expected.keys()):
        digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if digest != expected[name]:
            errors.append(f"SHA-256 mismatch for {name}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    errors = verify_bundle(args.bundle)
    for error in errors:
        print(f"release bundle: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
