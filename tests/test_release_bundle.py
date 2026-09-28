from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.verify_release_bundle import verify_bundle


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "release"
    (root / "python").mkdir(parents=True)
    (root / "assets").mkdir()
    files = {
        "python/example-0.1.0-py3-none-any.whl": b"wheel",
        "python/example-0.1.0.tar.gz": b"sdist",
        "assets/example.cdx.json": b"{}",
    }
    lines = []
    for name, content in files.items():
        (root / name).write_bytes(content)
        lines.append(f"{hashlib.sha256(content).hexdigest()}  {name}\n")
    (root / "SHA256SUMS").write_text("".join(lines))
    return root


def test_complete_release_bundle_passes(tmp_path: Path):
    assert verify_bundle(_bundle(tmp_path)) == []


def test_release_bundle_rejects_unlisted_file(tmp_path: Path):
    root = _bundle(tmp_path)
    (root / "assets" / "unlisted.vsix").write_bytes(b"not bound")

    assert any("absent from SHA256SUMS" in error for error in verify_bundle(root))


def test_release_bundle_rejects_missing_and_changed_files(tmp_path: Path):
    root = _bundle(tmp_path)
    (root / "python" / "example-0.1.0.tar.gz").unlink()
    (root / "python" / "example-0.1.0-py3-none-any.whl").write_bytes(b"changed")

    errors = verify_bundle(root)
    assert any("absent from the bundle" in error for error in errors)
    assert any("SHA-256 mismatch" in error for error in errors)


def test_release_bundle_rejects_malformed_manifest_and_extra_root_entry(tmp_path: Path):
    root = _bundle(tmp_path)
    with (root / "SHA256SUMS").open("a") as manifest:
        manifest.write("not-a-hash  assets/other.txt\n")
    (root / "operator-notes.txt").write_text("not a release asset")

    errors = verify_bundle(root)
    assert any("line 4 is malformed" in error for error in errors)
    assert any("root contains unlisted entries" in error for error in errors)
