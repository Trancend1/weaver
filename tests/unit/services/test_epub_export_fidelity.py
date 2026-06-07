"""Tests for EPUB export fidelity reports."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from ebooklib import epub

from weaver.readers.epub import parse_epub_structure, read_epub
from weaver.renderers.epub import render_translated_epub
from weaver.services.epub_export_fidelity import compare_epub_export_fidelity
from weaver.services.epub_structure_preview import preview_epub_structure
from weaver.services.import_source import import_volume
from weaver.services.project import initialize_project


def _write_fidelity_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("urn:uuid:fidelity")
    book.set_title("Fidelity Source")
    book.set_language("ja")
    book.add_metadata("OPF", "meta", "cover-image", {"name": "cover", "content": "cover-image"})

    chapter = epub.EpubHtml(title="Chapter", file_name="text/chapter.xhtml", lang="ja")
    chapter.content = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
        '<link rel="stylesheet" type="text/css" href="../styles/book.css"/>'
        '</head><body><h1>Chapter</h1><img src="../images/cover.jpg"/><p>Body</p></body></html>'
    )
    style = epub.EpubItem(
        uid="style",
        file_name="styles/book.css",
        media_type="text/css",
        content=b"body { color: black; }",
    )
    cover = epub.EpubItem(
        uid="cover-image",
        file_name="images/cover.jpg",
        media_type="image/jpeg",
        content=b"fake-cover",
    )

    for item in [chapter, style, cover]:
        book.add_item(item)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    book.toc = [chapter]
    epub.write_epub(str(path), book)


def _remove_zip_member(path: Path, member_name: str) -> None:
    rewritten = path.with_suffix(".missing.epub")
    with ZipFile(path, "r") as source, ZipFile(rewritten, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            if item.filename == member_name:
                continue
            target.writestr(item, source.read(item.filename))
    rewritten.replace(path)


def _png(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"fake"


def _replace_zip_member(path: Path, member_name: str, content: bytes) -> None:
    rewritten = path.with_suffix(".rewritten.epub")
    with ZipFile(path, "r") as source, ZipFile(rewritten, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = content if item.filename == member_name else source.read(item.filename)
            target.writestr(item, data)
    rewritten.replace(path)


def _write_light_novel_fixture_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("urn:uuid:light-novel-f11")
    book.set_title("光の境界 1")
    book.set_language("ja")
    book.add_author("星野 詩音")
    book.add_metadata("OPF", "meta", "cover-image", {"name": "cover", "content": "cover-image"})

    cover_page = epub.EpubHtml(title="Cover", file_name="text/cover.xhtml", lang="ja")
    cover_page.content = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        '<img src="../Images/cover.jpg" alt="cover"/></body></html>'
    )
    color_page = epub.EpubHtml(title="口絵", file_name="text/color.xhtml", lang="ja")
    color_page.content = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        '<img src="../Images/color_illust_001.png" alt="口絵"/></body></html>'
    )
    character_page = epub.EpubHtml(title="人物紹介", file_name="text/characters.xhtml", lang="ja")
    character_page.content = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        '<img src="../Images/character_profile.png" alt="人物紹介"/></body></html>'
    )
    chapter = epub.EpubHtml(title="第一章", file_name="text/chapter01.xhtml", lang="ja")
    chapter.content = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
        '<link rel="stylesheet" type="text/css" href="../styles/book.css"/>'
        "</head><body><h1>第一章</h1><p>本文です。</p>"
        '<img src="../Images/insert_art_01.png" alt="挿絵"/>'
        '<img src="../Images/divider-line.svg" alt="divider"/></body></html>'
    )

    resources = [
        cover_page,
        color_page,
        character_page,
        chapter,
        epub.EpubItem(
            uid="style",
            file_name="styles/book.css",
            media_type="text/css",
            content=b"body { writing-mode: vertical-rl; }",
        ),
        epub.EpubItem(
            uid="font-main",
            file_name="fonts/main.otf",
            media_type="font/otf",
            content=b"fake-font",
        ),
        epub.EpubItem(
            uid="cover-image",
            file_name="Images/cover.jpg",
            media_type="image/jpeg",
            content=b"fake-cover",
        ),
        epub.EpubItem(
            uid="color-illustration",
            file_name="Images/color_illust_001.png",
            media_type="image/png",
            content=_png(640, 960),
        ),
        epub.EpubItem(
            uid="character-page-image",
            file_name="Images/character_profile.png",
            media_type="image/png",
            content=_png(600, 900),
        ),
        epub.EpubItem(
            uid="insert-art",
            file_name="Images/insert_art_01.png",
            media_type="image/png",
            content=_png(500, 500),
        ),
        epub.EpubItem(
            uid="divider",
            file_name="Images/divider-line.svg",
            media_type="image/svg+xml",
            content=b"<svg></svg>",
        ),
    ]
    for item in resources:
        book.add_item(item)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", (cover_page, "no"), color_page, character_page, chapter]
    book.toc = [
        (epub.Section("序盤"), [color_page, character_page]),
        (epub.Section("本編"), [chapter]),
    ]
    epub.write_epub(str(path), book)

    nav_xhtml = """<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<body>
  <nav epub:type="toc"><ol>
    <li><span>序盤</span><ol>
      <li><a href="text/color.xhtml">口絵</a></li>
      <li><a href="text/characters.xhtml">人物紹介</a></li>
    </ol></li>
    <li><a href="text/chapter01.xhtml">第一章</a></li>
  </ol></nav>
  <nav epub:type="landmarks"><ol><li><a href="text/cover.xhtml">表紙</a></li></ol></nav>
  <nav epub:type="page-list"><ol><li><a href="text/chapter01.xhtml#p1">1</a></li></ol></nav>
</body></html>"""
    _replace_zip_member(path, "EPUB/nav.xhtml", nav_xhtml.encode("utf-8"))


def _write_light_novel_fixture_with_missing_optional_resource(path: Path) -> None:
    _write_light_novel_fixture_epub(path)
    _remove_zip_member(path, "EPUB/fonts/main.otf")


def test_compare_epub_export_fidelity_passes_for_renderer_preserved_export(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.epub"
    output = tmp_path / "translated.epub"
    _write_fidelity_epub(source)

    render_translated_epub(
        source_epub_path=source,
        output_path=output,
        document=read_epub(source),
        translations_by_segment_id={},
    )

    report = compare_epub_export_fidelity(source, output)

    assert report.critical_count == 0
    assert any(check.code == "spine-order-preserved" for check in report.passed_checks)
    assert any(check.code == "image-resources-preserved" for check in report.passed_checks)
    assert report.source_counts["images"] == report.exported_counts["images"]


def test_compare_epub_export_fidelity_reports_missing_export_resource(tmp_path: Path) -> None:
    source = tmp_path / "source.epub"
    output = tmp_path / "translated.epub"
    _write_fidelity_epub(source)
    render_translated_epub(
        source_epub_path=source,
        output_path=output,
        document=read_epub(source),
        translations_by_segment_id={},
    )
    _remove_zip_member(output, "EPUB/images/cover.jpg")

    report = compare_epub_export_fidelity(source, output)

    assert report.critical_count >= 1
    assert "images/cover.jpg" in report.missing_resources
    assert any(check.code == "missing-resource" for check in report.critical_gaps)


def test_compare_epub_export_fidelity_report_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "source.epub"
    output = tmp_path / "translated.epub"
    _write_fidelity_epub(source)
    render_translated_epub(
        source_epub_path=source,
        output_path=output,
        document=read_epub(source),
        translations_by_segment_id={},
    )

    first = compare_epub_export_fidelity(source, output)
    second = compare_epub_export_fidelity(source, output)

    assert first == second


def test_light_novel_fixture_covers_broader_phase_f_structure(tmp_path: Path) -> None:
    source = tmp_path / "light_novel.epub"
    _write_light_novel_fixture_epub(source)

    parsed = parse_epub_structure(source)
    categories = {item.category for item in parsed.manifest}
    image_roles = {item.image_role for item in parsed.images}
    nav_types = {(item.source_type, item.nav_type) for item in parsed.navigation}

    assert {"chapter", "image", "css", "font", "nav", "ncx"} <= categories
    assert {
        "cover",
        "color_illustration",
        "insert_illustration",
        "character_page",
        "divider",
    } <= image_roles
    assert ("nav", "toc") in nav_types
    assert ("nav", "landmarks") in nav_types
    assert ("nav", "page-list") in nav_types
    assert any(item.children for item in parsed.navigation if item.nav_type == "toc")
    assert any(item.is_non_linear for item in parsed.spine)

    # Japanese navigation labels survive NAV parsing (top-level and nested).
    top_labels = {item.label for item in parsed.navigation}
    nested_labels = {child.label for item in parsed.navigation for child in item.children}
    assert "第一章" in top_labels
    assert {"口絵", "人物紹介"} <= nested_labels


def test_light_novel_fixture_missing_optional_resource_is_non_fatal(tmp_path: Path) -> None:
    source = tmp_path / "light_novel_missing_font.epub"
    _write_light_novel_fixture_with_missing_optional_resource(source)

    parsed = parse_epub_structure(source)

    assert any(issue.code == "missing-manifest-resource" for issue in parsed.validation_issues)
    assert any(item.category == "font" and not item.exists_in_archive for item in parsed.manifest)
    assert parsed.spine
    assert parsed.metadata.title == "光の境界 1"


def test_light_novel_fixture_keeps_document_ir_segments_stable(tmp_path: Path) -> None:
    source = tmp_path / "light_novel.epub"
    _write_light_novel_fixture_epub(source)

    document = read_epub(source)
    segment_texts = [block.source_text for chapter in document.chapters for block in chapter.blocks]

    assert document.metadata.title == "光の境界 1"
    assert document.metadata.language == "ja"
    assert segment_texts == ["第一章", "本文です。"]
    assert all("character_profile" not in text for text in segment_texts)
    assert all("insert_art" not in text for text in segment_texts)


def test_light_novel_fixture_import_export_preview_and_fidelity_regression(tmp_path: Path) -> None:
    source = tmp_path / "light_novel.epub"
    _write_light_novel_fixture_epub(source)
    project_source = tmp_path / "project_source.epub"
    _write_fidelity_epub(project_source)
    init = initialize_project(project_source, cwd=tmp_path / "project", provider="fake")

    import_result = import_volume(init.project_toml, source, cwd=tmp_path / "project")
    document = read_epub(source)
    output = tmp_path / "light_novel.translated.epub"
    render_translated_epub(
        source_epub_path=source,
        output_path=output,
        document=document,
        translations_by_segment_id={},
    )
    preview_before = preview_epub_structure(source)
    preview_after = preview_epub_structure(source)
    report = compare_epub_export_fidelity(source, output)

    assert import_result.chapter_count >= 1
    assert output.exists()
    assert preview_before == preview_after
    assert preview_before["counts"]["images"] >= 5
    assert report.critical_count == 0
    assert report.source_counts["images"] == report.exported_counts["images"]


def test_light_novel_fidelity_catches_missing_export_asset(tmp_path: Path) -> None:
    source = tmp_path / "light_novel.epub"
    output = tmp_path / "light_novel.translated.epub"
    _write_light_novel_fixture_epub(source)
    render_translated_epub(
        source_epub_path=source,
        output_path=output,
        document=read_epub(source),
        translations_by_segment_id={},
    )
    _remove_zip_member(output, "EPUB/Images/insert_art_01.png")

    report = compare_epub_export_fidelity(source, output)

    assert report.critical_count >= 1
    assert "Images/insert_art_01.png" in report.missing_resources
    assert any(check.code == "missing-image-resource" for check in report.critical_gaps)
