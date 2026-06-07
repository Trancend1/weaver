"""Tests for Phase F EPUB structure parsing skeleton."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from ebooklib import epub

from weaver.readers.epub import parse_epub_structure, read_chapter_excerpt, read_epub

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def _write_minimal_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("urn:isbn:9780000000001")
    book.set_title("テスト小説")
    book.set_language("ja")
    book.add_author("山田 太郎")
    book.add_metadata("DC", "publisher", "テスト出版社")
    book.add_metadata("DC", "description", "説明文です。")

    chapter = epub.EpubHtml(
        title="第一章",
        file_name="text/chapter01.xhtml",
        lang="ja",
    )
    chapter.content = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<h1>第一章</h1><p>本文です。</p>"
        "</body></html>"
    )
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    book.toc = [chapter]

    epub.write_epub(str(path), book)


def _write_rich_metadata_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("urn:uuid:rich-metadata")
    book.set_title("Rich Metadata")
    book.set_language("ja")
    book.add_author("Primary Creator")
    book.add_metadata("DC", "contributor", "Editor One")
    book.add_metadata("DC", "contributor", "Illustrator Two")
    book.add_metadata("DC", "date", "2026-01-02")
    book.add_metadata("DC", "subject", "Light Novel")
    book.add_metadata("DC", "subject", "Fantasy")
    book.add_metadata("DC", "rights", "All rights reserved")
    book.add_metadata("DC", "source", "Original JP EPUB")
    book.add_metadata("DC", "coverage", "Japan")
    book.add_metadata("DC", "relation", "Volume 1")
    book.add_metadata("DC", "type", "Text")
    book.add_metadata("DC", "format", "application/epub+zip")
    book.add_metadata("OPF", "meta", "cover-image", {"name": "cover", "content": "cover-image"})
    book.add_metadata("OPF", "meta", "Series Name", {"name": "calibre:series"})
    book.add_metadata("OPF", "meta", "2", {"name": "calibre:series_index"})
    book.add_metadata(
        "OPF",
        "meta",
        "2026-01-03T04:05:06Z",
        {"property": "dcterms:modified"},
    )
    book.add_metadata("OPF", "meta", "Collection Name", {"property": "belongs-to-collection"})
    book.add_metadata("OPF", "meta", "series", {"property": "collection-type"})
    book.add_metadata("OPF", "meta", "2", {"property": "group-position"})
    book.add_metadata("OPF", "meta", "Vendor Value", {"property": "vendor:custom"})

    chapter = epub.EpubHtml(title="Chapter", file_name="text/chapter.xhtml", lang="ja")
    chapter.content = '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Body</p></body></html>'
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    book.toc = [chapter]

    epub.write_epub(str(path), book)


def _write_resource_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("urn:uuid:resources")
    book.set_title("Resource Map")
    book.set_language("ja")

    chapter = epub.EpubHtml(title="Chapter", file_name="text/chapter.xhtml", lang="ja")
    chapter.content = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
        '<link rel="stylesheet" type="text/css" href="../styles/book.css"/>'
        '</head><body><img src="../images/cover.jpg"/><p>Body</p></body></html>'
    )
    style = epub.EpubItem(
        uid="style",
        file_name="styles/book.css",
        media_type="text/css",
        content=b"body { color: black; }",
    )
    image = epub.EpubItem(
        uid="cover-image",
        file_name="images/cover.jpg",
        media_type="image/jpeg",
        content=b"fake-jpeg",
    )
    font = epub.EpubItem(
        uid="font-main",
        file_name="fonts/main.otf",
        media_type="font/otf",
        content=b"fake-font",
    )
    script = epub.EpubItem(
        uid="script-main",
        file_name="scripts/app.js",
        media_type="application/javascript",
        content=b"console.log('x')",
    )
    audio = epub.EpubItem(
        uid="audio-main",
        file_name="audio/opening.mp3",
        media_type="audio/mpeg",
        content=b"fake-audio",
    )
    unknown = epub.EpubItem(
        uid="unknown-bin",
        file_name="misc/blob.bin",
        media_type="application/x-custom",
        content=b"blob",
    )
    missing = epub.EpubItem(
        uid="missing-css",
        file_name="styles/missing.css",
        media_type="text/css",
        content=b"missing",
    )

    book.add_metadata("OPF", "meta", "cover-image", {"name": "cover", "content": "cover-image"})
    for item in [chapter, style, image, font, script, audio, unknown, missing]:
        book.add_item(item)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    book.toc = [chapter]

    epub.write_epub(str(path), book)
    _remove_zip_member(path, "EPUB/styles/missing.css")


def _remove_zip_member(path: Path, member_name: str) -> None:
    rewritten = path.with_suffix(".rewritten.epub")
    with ZipFile(path, "r") as source, ZipFile(rewritten, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            if item.filename == member_name:
                continue
            target.writestr(item, source.read(item.filename))
    rewritten.replace(path)


def test_parse_epub_structure_excludes_navigation_from_spine() -> None:
    parsed = parse_epub_structure(FIXTURE_EPUB)
    spine_hrefs = [item.href for item in parsed.spine if item.href is not None]
    assert all("nav" not in href for href in spine_hrefs)
    assert all(href.endswith((".xhtml", ".html")) for href in spine_hrefs)


def test_parse_epub_structure_extracts_minimal_opf_metadata(tmp_path: Path) -> None:
    source = tmp_path / "minimal.epub"
    _write_minimal_epub(source)

    parsed = parse_epub_structure(source)

    assert parsed.package_path == source
    assert parsed.metadata.title == "テスト小説"
    assert parsed.metadata.creator == "山田 太郎"
    assert parsed.metadata.language == "ja"
    assert parsed.metadata.publisher == "テスト出版社"
    assert parsed.metadata.identifier == "urn:isbn:9780000000001"
    assert parsed.metadata.description == "説明文です。"


def test_parse_epub_structure_populates_phase_f_placeholders(tmp_path: Path) -> None:
    source = tmp_path / "minimal.epub"
    _write_minimal_epub(source)

    parsed = parse_epub_structure(source)

    assert parsed.manifest
    assert [item.href for item in parsed.spine] == ["text/chapter01.xhtml"]
    assert parsed.navigation
    assert parsed.resources
    assert parsed.validation_issues == []


def test_read_epub_document_ir_still_uses_existing_import_contract(tmp_path: Path) -> None:
    document = read_epub(FIXTURE_EPUB)

    assert document.metadata.title
    assert document.metadata.language
    assert document.chapters
    for chapter in document.chapters:
        assert chapter.href
        assert "nav" not in chapter.href


def test_parse_epub_structure_extracts_repeated_dc_metadata(tmp_path: Path) -> None:
    source = tmp_path / "rich.epub"
    _write_rich_metadata_epub(source)

    metadata = parse_epub_structure(source).metadata

    assert metadata.contributors == ["Editor One", "Illustrator Two"]
    assert metadata.dates == ["2026-01-02"]
    assert metadata.subjects == ["Light Novel", "Fantasy"]
    assert metadata.rights == ["All rights reserved"]
    assert metadata.sources == ["Original JP EPUB"]
    assert metadata.coverages == ["Japan"]
    assert metadata.relations == ["Volume 1"]
    assert metadata.types == ["Text"]
    assert metadata.formats == ["application/epub+zip"]


def test_parse_epub_structure_extracts_vendor_and_epub3_metadata(tmp_path: Path) -> None:
    source = tmp_path / "rich.epub"
    _write_rich_metadata_epub(source)

    metadata = parse_epub_structure(source).metadata

    assert metadata.modified is not None
    assert metadata.modified.endswith("Z")
    assert metadata.cover == "cover-image"
    assert metadata.series == "Series Name"
    assert metadata.series_index == "2"
    assert metadata.collection == "Collection Name"
    assert metadata.collection_type == "series"
    assert metadata.group_position == "2"


def test_parse_epub_structure_keeps_raw_metadata_fallback(tmp_path: Path) -> None:
    source = tmp_path / "rich.epub"
    _write_rich_metadata_epub(source)

    metadata = parse_epub_structure(source).metadata

    assert "OPF:meta:vendor:custom" in metadata.raw
    assert metadata.raw["OPF:meta:vendor:custom"] == ["Vendor Value"]


def test_parse_epub_structure_expands_manifest_resource_fields(tmp_path: Path) -> None:
    source = tmp_path / "resources.epub"
    _write_resource_epub(source)

    parsed = parse_epub_structure(source)
    resources = {item.id: item for item in parsed.manifest}

    chapter = resources["chapter_0"]
    assert chapter.href == "text/chapter.xhtml"
    assert chapter.resolved_path == "EPUB/text/chapter.xhtml"
    assert chapter.category == "chapter"
    assert chapter.exists_in_archive is True
    assert chapter.is_spine_item is True
    assert chapter.is_navigation is False
    assert chapter.referenced_by == []

    style = resources["style"]
    assert style.category == "css"
    assert style.is_stylesheet is True
    assert style.is_image is False

    image = resources["cover-image"]
    assert image.category == "image"
    assert image.is_image is True
    assert image.is_cover_candidate is True

    font = resources["font-main"]
    assert font.category == "font"
    assert font.is_font is True

    script = resources["script-main"]
    assert script.category == "script"
    assert script.is_script is True

    audio = resources["audio-main"]
    assert audio.category == "audio"

    unknown = resources["unknown-bin"]
    assert unknown.category == "unknown"


def test_parse_epub_structure_maps_nav_ncx_and_spine_linkage(tmp_path: Path) -> None:
    source = tmp_path / "resources.epub"
    _write_resource_epub(source)

    parsed = parse_epub_structure(source)
    by_href = {item.href: item for item in parsed.manifest}

    assert by_href["nav.xhtml"].category == "nav"
    assert by_href["nav.xhtml"].is_navigation is True
    assert by_href["toc.ncx"].category == "ncx"
    assert by_href["toc.ncx"].is_navigation is True
    assert [item.href for item in parsed.spine] == ["text/chapter.xhtml"]


def test_parse_epub_structure_preserves_manifest_order(tmp_path: Path) -> None:
    source = tmp_path / "resources.epub"
    _write_resource_epub(source)

    parsed = parse_epub_structure(source)

    assert [item.href for item in parsed.manifest[:3]] == [
        "text/chapter.xhtml",
        "styles/book.css",
        "images/cover.jpg",
    ]


def test_parse_epub_structure_reports_missing_manifest_resources(tmp_path: Path) -> None:
    source = tmp_path / "resources.epub"
    _write_resource_epub(source)

    parsed = parse_epub_structure(source)
    missing = next(item for item in parsed.manifest if item.href == "styles/missing.css")

    assert missing.exists_in_archive is False
    assert missing.category == "css"
    assert any(
        issue.severity == "error"
        and issue.code == "missing-manifest-resource"
        and issue.href == "styles/missing.css"
        for issue in parsed.validation_issues
    )


def _replace_opf_text(path: Path, replace: Callable[[str], str]) -> None:
    rewritten = path.with_suffix(".opf-rewritten.epub")
    with ZipFile(path, "r") as source, ZipFile(rewritten, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "EPUB/content.opf":
                data = replace(data.decode("utf-8")).encode("utf-8")
            target.writestr(item, data)
    rewritten.replace(path)


def _write_spine_epub(path: Path, *, missing_archive: bool = False) -> None:
    book = epub.EpubBook()
    book.set_identifier("urn:uuid:spine")
    book.set_title("Spine Map")
    book.set_language("ja")

    chapter_a = epub.EpubHtml(title="A", file_name="text/a.xhtml", lang="ja")
    chapter_a.content = '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>A</p></body></html>'
    chapter_b = epub.EpubHtml(title="B", file_name="text/b.xhtml", lang="ja")
    chapter_b.content = '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>B</p></body></html>'
    appendix = epub.EpubHtml(title="Appendix", file_name="text/appendix.xhtml", lang="ja")
    appendix.content = '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>X</p></body></html>'

    book.add_item(chapter_a)
    book.add_item(chapter_b)
    book.add_item(appendix)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [
        "nav",
        chapter_b,
        ("chapter_2", "no"),
        chapter_a,
        "missing-id",
        chapter_b,
    ]
    book.toc = [chapter_a, chapter_b]
    epub.write_epub(str(path), book)

    def replace(opf: str) -> str:
        opf = opf.replace(
            '<spine toc="ncx">',
            '<spine toc="ncx" page-progression-direction="rtl">',
        )
        opf = opf.replace('idref="chapter_0"', 'idref="chapter_0" page-spread="left"')
        opf = opf.replace(
            'idref="chapter_1"',
            'idref="chapter_1" properties="rendition:page-spread-right"',
        )
        return opf

    _replace_opf_text(path, replace)
    if missing_archive:
        _remove_zip_member(path, "EPUB/text/appendix.xhtml")


def _write_empty_spine_epub(path: Path) -> None:
    _write_minimal_epub(path)

    def replace(opf: str) -> str:
        start = opf.index("<spine")
        end = opf.index("</spine>") + len("</spine>")
        return (
            opf[:start] + '<spine toc="ncx" page-progression-direction="ltr"></spine>' + opf[end:]
        )

    _replace_opf_text(path, replace)


def test_parse_epub_structure_preserves_spine_order_and_attributes(tmp_path: Path) -> None:
    source = tmp_path / "spine.epub"
    _write_spine_epub(source)

    parsed = parse_epub_structure(source)

    assert parsed.spine_toc == "ncx"
    assert parsed.page_progression_direction == "rtl"
    assert [item.idref for item in parsed.spine] == [
        "chapter_1",
        "chapter_2",
        "chapter_0",
        "missing-id",
        "chapter_1",
    ]
    assert [item.href for item in parsed.spine[:3]] == [
        "text/b.xhtml",
        "text/appendix.xhtml",
        "text/a.xhtml",
    ]
    assert parsed.spine[1].linear is False
    assert parsed.spine[1].is_non_linear is True
    assert parsed.spine[2].page_spread == "left"
    assert parsed.spine[0].properties == ["rendition:page-spread-right"]


def test_parse_epub_structure_reports_spine_validation_issues(tmp_path: Path) -> None:
    source = tmp_path / "spine.epub"
    _write_spine_epub(source, missing_archive=True)

    parsed = parse_epub_structure(source)
    issues = {(issue.code, issue.href) for issue in parsed.validation_issues}

    assert ("spine-idref-missing-manifest", "missing-id") in issues
    assert ("spine-resource-missing-archive", "text/appendix.xhtml") in issues
    assert ("duplicate-spine-idref", "chapter_1") in issues
    assert any(issue.code == "non-linear-spine-item" for issue in parsed.validation_issues)


def test_parse_epub_structure_reports_empty_spine(tmp_path: Path) -> None:
    source = tmp_path / "empty-spine.epub"
    _write_empty_spine_epub(source)

    parsed = parse_epub_structure(source)

    assert parsed.spine == []
    assert any(issue.code == "empty-spine" for issue in parsed.validation_issues)


def test_parse_epub_structure_spine_links_manifest_and_archive_state(tmp_path: Path) -> None:
    source = tmp_path / "spine.epub"
    _write_spine_epub(source, missing_archive=True)

    parsed = parse_epub_structure(source)
    missing_manifest = next(item for item in parsed.spine if item.idref == "missing-id")
    missing_archive = next(item for item in parsed.spine if item.idref == "chapter_2")

    assert missing_manifest.exists_in_manifest is False
    assert missing_manifest.exists_in_archive is False
    assert missing_manifest.media_type is None
    assert missing_manifest.href is None
    assert missing_archive.exists_in_manifest is True
    assert missing_archive.exists_in_archive is False
    assert missing_archive.resolved_path == "EPUB/text/appendix.xhtml"


def _write_navigation_epub(path: Path) -> None:
    _write_minimal_epub(path)

    nav_xhtml = """<?xml version='1.0' encoding='utf-8'?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head><title>Navigation</title></head>
  <body>
    <nav epub:type="toc" id="toc"><ol>
      <li><a href="text/chapter01.xhtml">???</a>
        <ol><li><a href="text/chapter01.xhtml#scene-1">???</a></li></ol>
      </li>
      <li><a href="text/missing.xhtml">Missing Chapter</a></li>
    </ol></nav>
    <nav epub:type="landmarks"><ol>
      <li><a href="text/chapter01.xhtml">????</a></li>
    </ol></nav>
    <nav epub:type="page-list"><ol>
      <li><a href="text/chapter01.xhtml#page-1">1</a></li>
    </ol></nav>
    <nav epub:type="lot"><ol>
      <li><span>List of Tables Placeholder</span></li>
    </ol></nav>
  </body>
</html>
"""
    ncx = """<?xml version='1.0' encoding='utf-8'?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:isbn:9780000000001"/></head>
  <docTitle><text>Navigation Fixture</text></docTitle>
  <navMap>
    <navPoint id="ncx-1" playOrder="1">
      <navLabel><text>?????</text></navLabel>
      <content src="text/chapter01.xhtml"/>
      <navPoint id="ncx-1-1" playOrder="2">
        <navLabel><text>???</text></navLabel>
        <content src="text/chapter01.xhtml#child"/>
      </navPoint>
    </navPoint>
  </navMap>
</ncx>
"""
    rewritten = path.with_suffix(".nav-rewritten.epub")
    with ZipFile(path, "r") as source, ZipFile(rewritten, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "EPUB/nav.xhtml":
                data = nav_xhtml.encode("utf-8")
            if item.filename == "EPUB/toc.ncx":
                data = ncx.encode("utf-8")
            target.writestr(item, data)
    rewritten.replace(path)


def test_parse_epub_structure_parses_nested_epub3_nav(tmp_path: Path) -> None:
    source = tmp_path / "navigation.epub"
    _write_navigation_epub(source)

    parsed = parse_epub_structure(source)
    toc_entries = [
        entry
        for entry in parsed.navigation
        if entry.source_type == "nav" and entry.nav_type == "toc"
    ]

    assert toc_entries[0].label == "???"
    assert toc_entries[0].href == "text/chapter01.xhtml"
    assert toc_entries[0].resolved_path == "EPUB/text/chapter01.xhtml"
    assert toc_entries[0].fragment is None
    assert toc_entries[0].depth == 0
    assert toc_entries[0].linked_manifest_id == "chapter_0"
    assert toc_entries[0].linked_spine_index == 1
    assert toc_entries[0].children[0].label == "???"
    assert toc_entries[0].children[0].fragment == "scene-1"


def test_parse_epub_structure_parses_landmarks_page_list_and_lot(tmp_path: Path) -> None:
    source = tmp_path / "navigation.epub"
    _write_navigation_epub(source)

    parsed = parse_epub_structure(source)
    nav_types = {(entry.source_type, entry.nav_type, entry.label) for entry in parsed.navigation}

    assert ("nav", "landmarks", "????") in nav_types
    assert ("nav", "page-list", "1") in nav_types
    assert ("nav", "lot", "List of Tables Placeholder") in nav_types


def test_parse_epub_structure_parses_ncx_hierarchy_and_play_order(tmp_path: Path) -> None:
    source = tmp_path / "navigation.epub"
    _write_navigation_epub(source)

    parsed = parse_epub_structure(source)
    ncx_entries = [entry for entry in parsed.navigation if entry.source_type == "ncx"]

    assert ncx_entries[0].label == "?????"
    assert ncx_entries[0].play_order == 1
    assert ncx_entries[0].children[0].label == "???"
    assert ncx_entries[0].children[0].play_order == 2


def test_parse_epub_structure_reports_nav_validation_issues(tmp_path: Path) -> None:
    source = tmp_path / "navigation.epub"
    _write_navigation_epub(source)

    parsed = parse_epub_structure(source)
    issues = {(issue.code, issue.href) for issue in parsed.validation_issues}

    assert ("nav-href-missing-resource", "text/missing.xhtml") in issues
    assert ("nav-href-outside-spine", "text/missing.xhtml") in issues
    assert ("duplicate-nav-href", "text/chapter01.xhtml") in issues


def test_parse_epub_structure_reports_empty_toc(tmp_path: Path) -> None:
    source = tmp_path / "navigation.epub"
    _write_navigation_epub(source)

    def replace(opf: str) -> str:
        return opf

    _replace_opf_text(source, replace)
    rewritten = source.with_suffix(".empty-nav.epub")
    with ZipFile(source, "r") as source_zip, ZipFile(rewritten, "w", ZIP_DEFLATED) as target:
        for item in source_zip.infolist():
            data = source_zip.read(item.filename)
            if item.filename == "EPUB/nav.xhtml":
                data = b'<html xmlns="http://www.w3.org/1999/xhtml"><body><nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops"><ol></ol></nav></body></html>'
            if item.filename == "EPUB/toc.ncx":
                data = (
                    b'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" '
                    b'version="2005-1"><navMap></navMap></ncx>'
                )
            target.writestr(item, data)
    rewritten.replace(source)

    parsed = parse_epub_structure(source)

    assert any(issue.code == "empty-toc" for issue in parsed.validation_issues)


def _png(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"fake"


def _write_image_epub(path: Path, *, missing_cover: bool = False) -> None:
    book = epub.EpubBook()
    book.set_identifier("urn:uuid:images")
    book.set_title("Image Map")
    book.set_language("ja")
    book.add_metadata("OPF", "meta", "cover-image", {"name": "cover", "content": "cover-image"})

    chapter = epub.EpubHtml(title="Images", file_name="text/images.xhtml", lang="ja")
    chapter.content = """
<html xmlns="http://www.w3.org/1999/xhtml"><body>
  <img src="../Images/cover.jpg" alt="Cover"/>
  <img src="../Images/color_illust_001.png" title="Color"/>
  <img src="../Images/character_profile.png" alt="Characters"/>
  <img src="../Images/divider-line.svg" alt="Divider"/>
  <img src="../Images/publisher_logo.png" alt="Publisher"/>
  <img src="../Images/insert_art_01.png" alt="Insert"/>
  <img src="../Images/unmanifested.png" alt="Missing"/>
</body></html>
"""
    cover = epub.EpubItem(
        uid="cover-image",
        file_name="Images/cover.jpg",
        media_type="image/jpeg",
        content=b"fake-jpeg-cover",
    )
    color = epub.EpubItem(
        uid="color-illustration",
        file_name="Images/color_illust_001.png",
        media_type="image/png",
        content=_png(640, 960),
    )
    character = epub.EpubItem(
        uid="character-page",
        file_name="Images/character_profile.png",
        media_type="image/png",
        content=_png(600, 900),
    )
    divider = epub.EpubItem(
        uid="divider",
        file_name="Images/divider-line.svg",
        media_type="image/svg+xml",
        content=b"<svg></svg>",
    )
    logo = epub.EpubItem(
        uid="publisher-logo",
        file_name="Images/publisher_logo.png",
        media_type="image/png",
        content=_png(120, 60),
    )
    insert = epub.EpubItem(
        uid="insert-art",
        file_name="Images/insert_art_01.png",
        media_type="image/png",
        content=_png(500, 500),
    )
    unsupported = epub.EpubItem(
        uid="gif-image",
        file_name="Images/bonus.gif",
        media_type="image/gif",
        content=b"GIF89a",
    )

    for item in [chapter, cover, color, character, divider, logo, insert, unsupported]:
        book.add_item(item)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    book.toc = [chapter]
    epub.write_epub(str(path), book)
    if missing_cover:
        _remove_zip_member(path, "EPUB/Images/cover.jpg")


def test_parse_epub_structure_classifies_light_novel_image_roles(tmp_path: Path) -> None:
    source = tmp_path / "images.epub"
    _write_image_epub(source)

    parsed = parse_epub_structure(source)
    images = {item.id: item for item in parsed.images}

    assert images["cover-image"].image_role == "cover"
    assert images["cover-image"].image_kind == "cover"
    assert images["color-illustration"].image_role == "color_illustration"
    assert images["character-page"].image_role == "character_page"
    assert images["divider"].image_role == "divider"
    assert images["publisher-logo"].image_role == "publisher_logo"
    assert images["insert-art"].image_role == "insert_illustration"
    assert images["gif-image"].image_role == "unknown"


def test_parse_epub_structure_adds_image_preview_metadata(tmp_path: Path) -> None:
    source = tmp_path / "images.epub"
    _write_image_epub(source)

    parsed = parse_epub_structure(source)
    color = next(item for item in parsed.images if item.id == "color-illustration")

    assert color.manifest_id == "color-illustration"
    assert color.width == 640
    assert color.height == 960
    assert color.byte_size is not None
    assert color.preview_available is True
    assert color.linked_spine_index == 1
    assert color.referenced_by == ["text/images.xhtml"]


def test_parse_epub_structure_reports_image_validation_issues(tmp_path: Path) -> None:
    source = tmp_path / "images.epub"
    _write_image_epub(source, missing_cover=True)

    parsed = parse_epub_structure(source)
    issues = {(issue.code, issue.href) for issue in parsed.validation_issues}

    assert ("missing-image-resource", "Images/cover.jpg") in issues
    assert ("image-reference-missing-manifest", "Images/unmanifested.png") in issues
    assert ("unsupported-image-media-type", "Images/bonus.gif") in issues


def test_epub_validation_issues_are_stable_and_scoped(tmp_path: Path) -> None:
    source = tmp_path / "images.epub"
    _write_image_epub(source, missing_cover=True)

    first = parse_epub_structure(source).validation_issues
    second = parse_epub_structure(source).validation_issues

    assert [(issue.scope, issue.code, issue.href, issue.resource_id) for issue in first] == [
        (issue.scope, issue.code, issue.href, issue.resource_id) for issue in second
    ]
    missing_image = next(issue for issue in first if issue.code == "missing-image-resource")
    assert missing_image.scope == "image"
    assert missing_image.resource_id == "cover-image"
    assert missing_image.path == "EPUB/Images/cover.jpg"


def test_parse_epub_structure_builds_chapter_translation_context(tmp_path: Path) -> None:
    source = tmp_path / "navigation.epub"
    _write_navigation_epub(source)

    parsed = parse_epub_structure(source)
    chapter = parsed.preservation_context.chapters[0]

    assert chapter.href == "text/chapter01.xhtml"
    assert chapter.manifest_id == "chapter_0"
    assert chapter.spine_index == 1
    assert "???" in chapter.nav_labels
    assert chapter.segment_source == "document_ir"
    assert chapter.translatable is True


def test_parse_epub_structure_builds_non_text_preservation_records(tmp_path: Path) -> None:
    source = tmp_path / "images.epub"
    _write_image_epub(source)

    parsed = parse_epub_structure(source)
    records = {record.resource_id: record for record in parsed.preservation_context.records}

    assert records["cover-image"].preservation_kind == "image"
    assert records["cover-image"].image_role == "cover"
    assert records["cover-image"].translatable is False
    assert records["cover-image"].future_ocr_placeholder is True
    assert records["publisher-logo"].image_role == "publisher_logo"
    assert any(record.category in {"nav", "ncx"} for record in records.values())


def test_parse_epub_structure_links_image_preservation_to_spine_context(tmp_path: Path) -> None:
    source = tmp_path / "images.epub"
    _write_image_epub(source)

    parsed = parse_epub_structure(source)
    color = next(
        record
        for record in parsed.preservation_context.records
        if record.resource_id == "color-illustration"
    )

    assert color.referenced_by == ["text/images.xhtml"]
    assert color.linked_spine_index == 1
    assert color.placeholder_kind == "future_ocr_image_text"


def _write_japanese_image_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("urn:uuid:jp-images")
    book.set_title("画像テスト")
    book.set_language("ja")

    chapter = epub.EpubHtml(title="本編", file_name="text/main.xhtml", lang="ja")
    chapter.content = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        '<img src="../images/口絵01.png" alt="口絵"/>'
        '<img src="../images/人物紹介.png" alt="人物紹介"/>'
        '<img src="../images/挿絵02.png" alt="挿絵"/>'
        "</body></html>"
    )
    kuchie = epub.EpubItem(
        uid="kuchie",
        file_name="images/口絵01.png",
        media_type="image/png",
        content=_png(10, 10),
    )
    jinbutsu = epub.EpubItem(
        uid="jinbutsu",
        file_name="images/人物紹介.png",
        media_type="image/png",
        content=_png(10, 10),
    )
    sashie = epub.EpubItem(
        uid="sashie",
        file_name="images/挿絵02.png",
        media_type="image/png",
        content=_png(10, 10),
    )
    for item in [chapter, kuchie, jinbutsu, sashie]:
        book.add_item(item)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    book.toc = [chapter]
    epub.write_epub(str(path), book)


def test_parse_epub_structure_classifies_japanese_image_roles(tmp_path: Path) -> None:
    source = tmp_path / "jp_images.epub"
    _write_japanese_image_epub(source)

    parsed = parse_epub_structure(source)
    images = {item.id: item for item in parsed.images}

    assert images["kuchie"].image_role == "color_illustration"
    assert images["jinbutsu"].image_role == "character_page"
    assert images["sashie"].image_role == "insert_illustration"


def test_read_chapter_excerpt_extracts_body_text(tmp_path: Path) -> None:
    source = tmp_path / "minimal.epub"
    _write_minimal_epub(source)

    parsed = parse_epub_structure(source)
    chapter = parsed.preservation_context.chapters[0]
    excerpt = read_chapter_excerpt(source, chapter.resolved_path)

    assert excerpt is not None
    assert "本文です" in excerpt
    assert read_chapter_excerpt(source, "EPUB/does-not-exist.xhtml") is None


def test_read_chapter_excerpt_truncates_long_text(tmp_path: Path) -> None:
    source = tmp_path / "long.epub"
    book = epub.EpubBook()
    book.set_identifier("urn:uuid:long")
    book.set_title("長文")
    book.set_language("ja")
    chapter = epub.EpubHtml(title="長章", file_name="text/long.xhtml", lang="ja")
    chapter.content = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>' + ("あ" * 600) + "</p></body></html>"
    )
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    book.toc = [chapter]
    epub.write_epub(str(source), book)

    excerpt = read_chapter_excerpt(source, "EPUB/text/long.xhtml", limit=80)

    assert excerpt is not None
    assert excerpt.endswith("…")
    assert len(excerpt) <= 81


def test_read_epub_keeps_images_out_of_translation_segments(tmp_path: Path) -> None:
    source = tmp_path / "images.epub"
    _write_image_epub(source)
    text_source = tmp_path / "minimal.epub"
    _write_minimal_epub(text_source)

    document = read_epub(source)
    text_document = read_epub(text_source)
    segment_texts = [block.source_text for chapter in document.chapters for block in chapter.blocks]
    text_segment_texts = [
        block.source_text for chapter in text_document.chapters for block in chapter.blocks
    ]

    assert text_segment_texts
    assert all("cover" not in text.lower() for text in segment_texts)
    assert all("publisher_logo" not in text.lower() for text in segment_texts)
