"""Per-chapter import degradation for malformed XHTML (v0.7.3 M2, audit N5).

Gate-B decision: one broken spine chapter is a visible validation issue, not a
whole-book failure — parseable chapters import unchanged.
"""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from weaver.readers.epub import read_epub
from weaver.services.project import initialize_project

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"
MALFORMED_CHAPTER = "text/chapter02.xhtml"


def _epub_with_one_malformed_chapter(tmp_path: Path) -> Path:
    """Copy the fixture, replacing one spine chapter with unparseable bytes.

    Note: mildly broken markup (e.g. an unclosed tag) is *repaired* by
    ebooklib/lxml and imports fine — only content that is unparseable even
    after that repair (binary garbage, truncated/empty files) hits the
    per-chapter degradation path.
    """

    broken = tmp_path / "broken_chapter.epub"
    with ZipFile(FIXTURE_EPUB) as source, ZipFile(broken, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == MALFORMED_CHAPTER:
                data = b"%PDF-1.4 binary \xff\xfe not xhtml <<<"
            target.writestr(item, data)
    return broken


def test_read_epub_skips_malformed_chapter_and_reports_issue(tmp_path: Path) -> None:
    baseline = read_epub(FIXTURE_EPUB)
    document = read_epub(_epub_with_one_malformed_chapter(tmp_path))

    assert len(document.chapters) == len(baseline.chapters) - 1
    assert len(document.read_issues) == 1
    assert MALFORMED_CHAPTER in document.read_issues[0]
    # The surviving chapters import unchanged.
    assert all(chapter.blocks for chapter in document.chapters)


def test_read_epub_on_clean_fixture_reports_no_issues() -> None:
    assert read_epub(FIXTURE_EPUB).read_issues == ()


def test_init_with_malformed_chapter_imports_rest_and_surfaces_issue(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    broken = _epub_with_one_malformed_chapter(tmp_path)

    result = initialize_project(broken, cwd=tmp_path)

    assert result.chapter_count >= 1  # the parseable chapter imported
    assert result.segment_count > 0
    assert len(result.read_issues) == 1
    assert MALFORMED_CHAPTER in result.read_issues[0]
