"""EPUB reader integration tests."""

from __future__ import annotations

from pathlib import Path

from weaver.core.ir import DocumentIR
from weaver.core.segment import compute_source_hash
from weaver.readers.epub import read_epub

FIXTURE_EPUB = Path(__file__).parents[2] / "fixtures" / "aozora_sample.epub"


def test_read_epub_fixture_end_to_end_produces_document_ir() -> None:
    document = read_epub(FIXTURE_EPUB)

    assert isinstance(document, DocumentIR)
    assert document.metadata.title == "Aozora Weaver Sample"
    assert document.metadata.author == "Natsume Soseki"
    assert document.metadata.language == "ja"
    assert document.metadata.identifier == "weaver-aozora-sample"
    assert [chapter.href for chapter in document.chapters] == [
        "text/chapter01.xhtml",
        "text/chapter02.xhtml",
    ]
    assert [chapter.title for chapter in document.chapters] == ["第一章", "第二章"]
    assert [block.kind for block in document.chapters[0].blocks] == [
        "heading",
        "paragraph",
        "paragraph",
        "quote",
    ]
    assert document.chapters[0].blocks[1].source_text == "吾輩は猫である。"
    assert document.chapters[0].blocks[1].normalized_source_text == "吾輩は猫である。"
    assert document.chapters[0].blocks[1].markup_context.xpath.endswith("/p[1]")
    assert document.chapters[0].blocks[3].markup_context.tag == "blockquote"
    assert document.assets


def test_read_epub_fixture_is_deterministic_across_runs() -> None:
    first = read_epub(FIXTURE_EPUB)
    second = read_epub(FIXTURE_EPUB)

    first_ids = _block_ids(first)
    second_ids = _block_ids(second)

    assert first_ids == second_ids
    assert len(first_ids) == len(set(first_ids))


def test_read_epub_source_hash_changes_when_paragraph_text_changes() -> None:
    document = read_epub(FIXTURE_EPUB)
    original_block = document.chapters[0].blocks[1]
    original_hash = compute_source_hash(original_block.normalized_source_text)
    changed_hash = compute_source_hash("吾輩は犬である。")

    assert changed_hash != original_hash


def _block_ids(document: DocumentIR) -> list[str]:
    return [block.id for chapter in document.chapters for block in chapter.blocks]
