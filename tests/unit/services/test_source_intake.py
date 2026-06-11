"""Upload byte-cap tests for the source-intake glue (QF-08)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import SourceTooLargeError
from weaver.services import source_intake
from weaver.services.source_intake import resolve_intake_source


def test_resolve_intake_source_rejects_oversized_upload(tmp_path: Path, monkeypatch) -> None:
    # Shrink the cap so the test does not allocate hundreds of MiB.
    monkeypatch.setattr(source_intake, "MAX_UPLOAD_BYTES", 8)

    with pytest.raises(SourceTooLargeError, match="over the"):
        resolve_intake_source(tmp_path, uploaded=("novel.txt", b"x" * 9))


def test_resolve_intake_source_accepts_upload_under_cap(tmp_path: Path) -> None:
    stored = resolve_intake_source(tmp_path, uploaded=("novel.txt", b"hello"))

    assert stored.is_file()
    assert stored.suffix == ".txt"
