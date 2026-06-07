"""Tests for read-only EPUB structure preview service."""

from __future__ import annotations

from pathlib import Path

from ebooklib import epub

from weaver.services.epub_structure_preview import preview_epub_structure

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def _write_excerpt_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("urn:uuid:preview")
    book.set_title("プレビュー小説")
    book.set_language("ja")
    chapter = epub.EpubHtml(title="第一章", file_name="text/chapter01.xhtml", lang="ja")
    chapter.content = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<h1>第一章</h1><p>これは本文の抜粋です。</p></body></html>"
    )
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    book.toc = [chapter]
    epub.write_epub(str(path), book)


def test_preview_epub_structure_returns_metadata_counts_and_images() -> None:
    preview = preview_epub_structure(FIXTURE_EPUB)

    assert preview["metadata"]["title"]
    assert preview["counts"]["manifest"] >= 1
    assert "resources_by_category" in preview
    assert isinstance(preview["images"], list)
    assert isinstance(preview["validation_issues"], list)


def test_preview_exposes_reader_baseline_fields(tmp_path: Path) -> None:
    source = tmp_path / "preview.epub"
    _write_excerpt_epub(source)

    preview = preview_epub_structure(source)

    assert preview["readiness"] in {"safe", "warnings", "errors"}
    assert set(preview["severity_counts"]) == {"error", "warning", "info"}
    assert preview["is_safe_to_translate"] is (preview["severity_counts"]["error"] == 0)
    assert "page_progression_direction" in preview
    assert isinstance(preview["validation_by_scope"], dict)
    # Spine items carry reader-order attributes.
    assert "page_spread" in preview["spine"][0]
    assert "is_navigation" in preview["spine"][0]


def test_preview_includes_untranslated_chapter_excerpts(tmp_path: Path) -> None:
    source = tmp_path / "preview.epub"
    _write_excerpt_epub(source)

    excerpts = preview_epub_structure(source)["excerpts"]

    assert excerpts
    assert any("本文の抜粋" in entry["text"] for entry in excerpts)
    assert all("spine_index" in entry and "href" in entry for entry in excerpts)


def test_preview_groups_validation_by_scope(tmp_path: Path) -> None:
    source = tmp_path / "preview.epub"
    _write_excerpt_epub(source)

    preview = preview_epub_structure(source)
    flat = preview["validation_issues"]
    grouped = preview["validation_by_scope"]

    # Grouped issues cover exactly the flat issue set.
    assert sum(len(items) for items in grouped.values()) == len(flat)
    for scope, items in grouped.items():
        assert all(issue["scope"] == scope or scope == "other" for issue in items)
