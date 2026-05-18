"""Phase 8 EPUB renderer tests."""

from __future__ import annotations

from pathlib import Path

from ebooklib import epub

from weaver.readers.epub import read_epub
from weaver.renderers.epub import render_translated_epub

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def test_render_translated_epub_replaces_text_for_known_segments(tmp_path) -> None:
    document = read_epub(FIXTURE_EPUB)
    translations = {
        block.id: f"EN[{index}]: {block.normalized_source_text}"
        for index, chapter in enumerate(document.chapters)
        for block in chapter.blocks
    }
    output_path = tmp_path / "out" / "aozora_sample.translated.epub"

    result = render_translated_epub(
        source_epub_path=FIXTURE_EPUB,
        output_path=output_path,
        document=document,
        translations_by_segment_id=translations,
    )

    assert result.translated_blocks == 6
    assert result.fallback_blocks == 0
    assert output_path.exists()

    book = epub.read_epub(str(output_path))
    chapter01 = next(item for item in book.get_items() if item.get_name() == "text/chapter01.xhtml")
    body = chapter01.get_content().decode("utf-8")
    for translation in translations.values():
        if "[0]" in translation:
            assert translation in body


def test_render_translated_epub_preserves_metadata_spine_and_assets(tmp_path) -> None:
    document = read_epub(FIXTURE_EPUB)
    output_path = tmp_path / "preserved.translated.epub"

    render_translated_epub(
        source_epub_path=FIXTURE_EPUB,
        output_path=output_path,
        document=document,
        translations_by_segment_id={},
    )

    original = epub.read_epub(str(FIXTURE_EPUB))
    rendered = epub.read_epub(str(output_path))
    assert rendered.get_metadata("DC", "title") == original.get_metadata("DC", "title")
    assert rendered.get_metadata("DC", "language") == original.get_metadata("DC", "language")
    assert [item_id for item_id, _ in rendered.spine] == [item_id for item_id, _ in original.spine]
    original_assets = {item.get_name() for item in original.get_items()}
    rendered_assets = {item.get_name() for item in rendered.get_items()}
    assert original_assets <= rendered_assets


def test_render_translated_epub_falls_back_to_source_when_translation_missing(tmp_path) -> None:
    document = read_epub(FIXTURE_EPUB)
    first_block = document.chapters[0].blocks[0]
    translations = {first_block.id: "Only first block translated."}
    output_path = tmp_path / "partial.translated.epub"

    result = render_translated_epub(
        source_epub_path=FIXTURE_EPUB,
        output_path=output_path,
        document=document,
        translations_by_segment_id=translations,
    )

    assert result.translated_blocks == 1
    assert result.fallback_blocks == 5
    rendered = epub.read_epub(str(output_path))
    chapter01 = next(
        item for item in rendered.get_items() if item.get_name() == "text/chapter01.xhtml"
    )
    body = chapter01.get_content().decode("utf-8")
    assert "Only first block translated." in body
    second_block = document.chapters[0].blocks[1]
    assert second_block.source_text in body
