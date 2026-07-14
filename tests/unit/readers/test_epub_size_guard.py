"""Zip-bomb ceiling tests for the EPUB reader (v0.7.3 M2, audit N4)."""

from __future__ import annotations

from pathlib import Path

import pytest

import weaver.readers.epub as epub_reader
from weaver.errors import EpubReadError
from weaver.readers.epub import parse_epub_structure, read_epub

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def test_read_epub_rejects_archive_over_uncompressed_ceiling(monkeypatch) -> None:
    # The fixture's declared uncompressed total exceeds a tiny patched ceiling —
    # the guard must reject it before any parse.
    monkeypatch.setattr(epub_reader, "MAX_UNCOMPRESSED_BYTES", 1024)

    with pytest.raises(EpubReadError) as exc_info:
        read_epub(FIXTURE_EPUB)

    assert "safety ceiling" in str(exc_info.value)


def test_parse_epub_structure_rejects_archive_over_uncompressed_ceiling(monkeypatch) -> None:
    monkeypatch.setattr(epub_reader, "MAX_UNCOMPRESSED_BYTES", 1024)

    with pytest.raises(EpubReadError):
        parse_epub_structure(FIXTURE_EPUB)


def test_real_fixture_passes_under_real_ceiling() -> None:
    document = read_epub(FIXTURE_EPUB)
    assert document.chapters


def test_non_zip_file_falls_through_to_parser_error(tmp_path: Path) -> None:
    # The size guard must not mask the parser's own invalid-EPUB error.
    bogus = tmp_path / "not_an_epub.epub"
    bogus.write_bytes(b"this is not a zip archive")

    with pytest.raises(EpubReadError) as exc_info:
        read_epub(bogus)

    assert "safety ceiling" not in str(exc_info.value)
