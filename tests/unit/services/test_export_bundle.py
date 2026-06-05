"""Export bundle ZIP writer (Phase D)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from weaver.errors import ExportError
from weaver.services.export_bundle import bundle_filename, write_export_bundle


def test_bundle_filename_is_deterministic() -> None:
    assert bundle_filename("docx") == "bundle-docx.zip"
    assert bundle_filename("epub") == "bundle-epub.zip"


def test_write_bundle_stores_artifacts_by_basename(tmp_path: Path) -> None:
    a = tmp_path / "out" / "docx" / "volume-01-id1.docx"
    b = tmp_path / "out" / "docx" / "volume-02-id2.docx"
    a.parent.mkdir(parents=True)
    a.write_bytes(b"AAA")
    b.write_bytes(b"BBB")
    out = tmp_path / "out" / "docx" / "bundle-docx.zip"

    result = write_export_bundle(output_path=out, artifact_paths=[a, b])

    assert result == out
    assert out.exists()
    with zipfile.ZipFile(out) as archive:
        assert sorted(archive.namelist()) == ["volume-01-id1.docx", "volume-02-id2.docx"]
        assert archive.read("volume-01-id1.docx") == b"AAA"


def test_write_bundle_creates_parent_dir(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    out = tmp_path / "nested" / "deeper" / "bundle-txt.zip"
    write_export_bundle(output_path=out, artifact_paths=[src])
    assert out.exists()


def test_write_bundle_missing_artifact_raises(tmp_path: Path) -> None:
    out = tmp_path / "bundle.zip"
    with pytest.raises(ExportError, match="Failed to write export bundle"):
        write_export_bundle(output_path=out, artifact_paths=[tmp_path / "missing.docx"])
