#!/usr/bin/env python3
"""Build a wheel from the exact sdist while forbidding frontend toolchain fallback."""

from __future__ import annotations

import argparse
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

from check_artifacts import check_wheel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdist", type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with tarfile.open(args.sdist, "r:gz") as archive:
            archive.extractall(root, filter="data")
        sources = [path for path in root.iterdir() if path.is_dir()]
        if len(sources) != 1:
            raise RuntimeError("sdist must contain exactly one source root")
        environment = dict(os.environ)
        environment["SQL_NOTEBOOK_KIT_REQUIRE_STAGED_FRONTENDS"] = "1"
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(args.output)],
            cwd=sources[0],
            env=environment,
            check=True,
        )

    wheels = list(args.output.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("source build did not produce exactly one wheel")
    errors = check_wheel(wheels[0], expected_version=args.expected_version)
    if errors:
        raise RuntimeError("wheel from sdist failed policy: " + "; ".join(errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
