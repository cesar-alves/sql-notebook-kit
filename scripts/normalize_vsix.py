#!/usr/bin/env python3
"""Rewrite a VSIX as a deterministic ZIP archive."""

from __future__ import annotations

import argparse
import os
import zipfile
from pathlib import Path

FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def normalize(path: Path) -> None:
    with zipfile.ZipFile(path) as source:
        entries = [(info.filename, source.read(info)) for info in source.infolist()]

    temporary = path.with_suffix(path.suffix + ".normalized")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as output:
        for name, payload in sorted(entries):
            info = zipfile.ZipInfo(name, FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (0o40755 if name.endswith("/") else 0o100644) << 16
            output.writestr(info, payload)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if not args.path.is_file() or args.path.suffix != ".vsix":
        parser.error("path must be an existing .vsix file")
    normalize(args.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
