"""TXT reader tests (Sprint 1b)."""

from __future__ import annotations

import pytest

from weaver.errors import WeaverError
from weaver.readers.txt import read_txt

_SAMPLE = """第一章 はじまり

吾輩は猫である。
名前はまだ無い。

どこで生れたか頓と見当がつかぬ。

第二章 つづき

ここで始めて人間というものを見た。
"""


def test_read_txt_splits_chapters_on_headings_and_groups_paragraphs(tmp_path) -> None:
    path = tmp_path / "novel.txt"
    path.write_text(_SAMPLE, encoding="utf-8")

    document = read_txt(path)

    assert [chapter.title for chapter in document.chapters] == ["第一章 はじまり", "第二章 つづき"]
    first = document.chapters[0]
    # heading block + 2 paragraph blocks (blank line splits the two paragraphs)
    assert [block.kind for block in first.blocks] == ["heading", "paragraph", "paragraph"]
    assert first.blocks[1].source_text == "吾輩は猫である。 名前はまだ無い。"
    assert all(block.markup_context is None for block in first.blocks)


def test_read_txt_without_heading_falls_back_to_single_chapter(tmp_path) -> None:
    path = tmp_path / "plain.txt"
    path.write_text("ただの文章。\nもう一行。\n", encoding="utf-8")

    document = read_txt(path)

    assert len(document.chapters) == 1
    assert document.chapters[0].title is None
    assert document.chapters[0].blocks[0].kind == "paragraph"


def test_read_txt_rejects_empty_file(tmp_path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("   \n\n", encoding="utf-8")

    with pytest.raises(WeaverError, match="No translatable text"):
        read_txt(path)
