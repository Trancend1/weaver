"""read_source dispatch + cross-volume id-collision tests (Sprint 1b)."""

from __future__ import annotations

import pytest

from weaver.errors import WeaverError
from weaver.readers import detect_format, read_source
from weaver.readers.txt import read_txt


def test_detect_format_maps_known_suffixes(tmp_path) -> None:
    assert detect_format(tmp_path / "a.epub") == "epub"
    assert detect_format(tmp_path / "a.txt") == "txt"
    assert detect_format(tmp_path / "a.html") == "html"
    assert detect_format(tmp_path / "a.htm") == "html"


def test_detect_format_rejects_unknown_suffix(tmp_path) -> None:
    with pytest.raises(WeaverError, match="Unsupported source format"):
        detect_format(tmp_path / "a.pdf")


def test_read_source_dispatches_txt(tmp_path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("本文。\n", encoding="utf-8")

    document = read_source(path)

    assert document.chapters[0].blocks[0].source_text == "本文。"


def test_same_text_in_two_volumes_yields_distinct_ids(tmp_path) -> None:
    body = "第一章\n同じ文章。\n"
    vol_a = tmp_path / "volume_a.txt"
    vol_b = tmp_path / "volume_b.txt"
    vol_a.write_text(body, encoding="utf-8")
    vol_b.write_text(body, encoding="utf-8")

    doc_a = read_txt(vol_a)
    doc_b = read_txt(vol_b)

    chapter_ids_a = {chapter.id for chapter in doc_a.chapters}
    chapter_ids_b = {chapter.id for chapter in doc_b.chapters}
    segment_ids_a = {block.id for chapter in doc_a.chapters for block in chapter.blocks}
    segment_ids_b = {block.id for chapter in doc_b.chapters for block in chapter.blocks}

    assert chapter_ids_a.isdisjoint(chapter_ids_b)
    assert segment_ids_a.isdisjoint(segment_ids_b)
