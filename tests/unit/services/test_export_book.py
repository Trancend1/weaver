"""Tests for volume-aware EPUB export (Sprint 8A).

Covers the Gate 8A end-to-end criterion (a mixed-format EPUB+TXT+HTML novel
exports to per-volume EPUBs) plus the export-specific guarantees: read-only on
the DB, no source re-read for TXT/HTML, latest-attempt-only, manual preserved,
source fallback for untranslated content (incl. hash-mismatch), and
collision-safe filenames.
"""

from __future__ import annotations

import zipfile
from contextlib import closing
from pathlib import Path

import pytest
from ebooklib import epub

from weaver.core.ir import scope_document_to_volume
from weaver.errors import ChapterNotFoundError, VolumeNotFoundError
from weaver.readers.epub import read_epub
from weaver.services.export_book import (
    ExportResult,
    export_chapter,
    export_novel,
    export_volume,
    prepare_export,
)
from weaver.storage.db import (
    connect_readonly_database,
    initialize_database,
    transaction,
)
from weaver.storage.projects import create_project
from weaver.storage.segments import (
    SegmentStatus,
    insert_segment,
    list_chapter_segments,
    sync_document_segments,
    update_segment_status,
)
from weaver.storage.translations import record_translation
from weaver.storage.volumes import VolumeFormat, create_volume

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"

_PROJECT_TOML = """\
[project]
name = "demo"
source_file = "book.epub"
database_path = "state.db"
output_dir = "out"

[provider]
type = "fake"
model = "fake-1"

[translation]
source_lang = "ja"
target_lang = "en"
honorifics = "preserve"
"""

# A synthetic-volume segment spec: (suffix, kind, source_text, status, translation|None).
SynthSeg = tuple[str, str, str, SegmentStatus, str | None]


def _init(tmp_path: Path) -> tuple[Path, Path]:
    project_toml = tmp_path / "project.toml"
    project_toml.write_text(_PROJECT_TOML, encoding="utf-8")
    return project_toml, tmp_path / "state.db"


def _add_synth_volume(
    conn,
    *,
    project_id: int,
    title: str,
    source_format: VolumeFormat,
    source_path: str,
    chapters: list[tuple[str, int, list[SynthSeg]]],
) -> int:
    """Seed a TXT/HTML volume directly in the DB (no real source file needed)."""

    volume_id = create_volume(
        conn,
        project_id=project_id,
        title=title,
        source_path=source_path,
        source_format=source_format,
    )
    for chapter_id, spine_order, segs in chapters:
        conn.execute(
            "INSERT INTO chapters (id, project_id, volume_id, title, href, spine_order) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (chapter_id, project_id, volume_id, chapter_id, f"{chapter_id}.xhtml", spine_order),
        )
        for index, (suffix, kind, source_text, status, translation) in enumerate(segs):
            segment_id = f"{chapter_id}-{suffix}"
            source_hash = f"{segment_id}-h"
            insert_segment(
                conn,
                segment_id=segment_id,
                chapter_id=chapter_id,
                block_order=index,
                kind=kind,
                source_text=source_text,
                source_hash=source_hash,
                status=status,
            )
            if translation is not None:
                record_translation(
                    conn,
                    segment_id=segment_id,
                    text=translation,
                    source_hash=source_hash,
                    provider="fake",
                    model="fake-1",
                )
    return volume_id


def _add_epub_volume(conn, *, project_id: int, translate_first_n: int) -> list[tuple[str, str]]:
    """Seed an EPUB volume from the fixture and translate its first N segments.

    Returns ``(segment_id, expected_translation_text)`` for the translated ones.
    """

    document = read_epub(FIXTURE_EPUB)
    volume_id = create_volume(
        conn,
        project_id=project_id,
        title="EPUB Vol",
        source_path=str(FIXTURE_EPUB),
        source_format="epub",
    )
    # Mirror production: ids are volume-scoped before sync so the export's
    # re-read source joins 1:1 with stored rows (Stage 11B-1.5).
    document = scope_document_to_volume(document, volume_id)
    sync_document_segments(conn, project_id=project_id, volume_id=volume_id, document=document)

    ordered = [
        segment
        for chapter in document.chapters
        for segment in list_chapter_segments(conn, chapter_id=chapter.id)
    ]
    translated: list[tuple[str, str]] = []
    for segment in ordered[:translate_first_n]:
        text = f"EN: {segment.source_text}"
        record_translation(
            conn,
            segment_id=segment.id,
            text=text,
            source_hash=segment.source_hash,
            provider="fake",
            model="fake-1",
        )
        update_segment_status(conn, segment_id=segment.id, status="translated")
        translated.append((segment.id, text))
    return translated


def _count_translations(db_path: Path) -> int:
    with closing(connect_readonly_database(db_path)) as conn:
        return int(conn.execute("SELECT COUNT(*) AS n FROM translations").fetchone()["n"])


def _epub_text(path: Path) -> str:
    book = epub.read_epub(str(path))
    return "".join(
        item.get_content().decode("utf-8")
        for item in book.get_items()
        if item.get_name().endswith(".xhtml")
    )


# --------------------------------------------------------------------------- #
# Gate 8A: mixed-format novel exports to per-volume EPUBs
# --------------------------------------------------------------------------- #


def test_gate_8a_mixed_format_novel(tmp_path: Path) -> None:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn,
            name="demo",
            source_path=str(FIXTURE_EPUB),
            source_lang="ja",
            target_lang="en",
        )
        epub_translated = _add_epub_volume(conn, project_id=project_id, translate_first_n=2)
        _add_synth_volume(
            conn,
            project_id=project_id,
            title="TXT Vol",
            source_format="txt",
            source_path=str(tmp_path / "missing.txt"),
            chapters=[
                (
                    "txt-c1",
                    0,
                    [
                        ("h", "heading", "序章", "pending", None),
                        ("p1", "paragraph", "テキスト1", "translated", "EN txt para1"),
                        ("p2", "paragraph", "テキスト2", "manual", "MANUAL txt para2"),
                    ],
                )
            ],
        )
        _add_synth_volume(
            conn,
            project_id=project_id,
            title="HTML Vol",
            source_format="html",
            source_path=str(tmp_path / "missing.html"),
            chapters=[
                (
                    "html-c1",
                    0,
                    [
                        ("p1", "paragraph", "HTML源1", "translated", "EN html para1"),
                        ("p2", "paragraph", "HTML源2", "failed", None),
                    ],
                )
            ],
        )

    result = export_novel(project_toml)

    assert isinstance(result, ExportResult)
    assert result.scope == "novel"
    assert result.target == "epub"
    assert result.volumes_total == 3
    assert result.volumes_exported == 3
    assert [artifact.source_format for artifact in result.artifacts] == ["epub", "txt", "html"]
    for artifact in result.artifacts:
        assert artifact.output_path.exists()
        assert artifact.output_path.parent == tmp_path / "out" / "epub"

    epub_art, txt_art, html_art = result.artifacts
    assert (epub_art.translated_segments, epub_art.fallback_segments) == (2, 4)
    assert (txt_art.translated_segments, txt_art.fallback_segments) == (2, 1)
    assert txt_art.fallback_by_status.pending == 1
    assert (html_art.translated_segments, html_art.fallback_segments) == (1, 1)
    assert html_art.fallback_by_status.failed == 1

    assert result.translated_segments == 5
    assert result.fallback_segments == 6

    # TXT synthesized EPUB: translated + manual present, untranslated heading falls back.
    txt_body = _epub_text(txt_art.output_path)
    assert "EN txt para1" in txt_body
    assert "MANUAL txt para2" in txt_body
    assert "序章" in txt_body

    # EPUB write-back: a translated block carries its translation.
    epub_body = _epub_text(epub_art.output_path)
    assert epub_translated[0][1] in epub_body


# --------------------------------------------------------------------------- #
# Export is read-only on the database
# --------------------------------------------------------------------------- #


def test_export_writes_no_translation_rows(tmp_path: Path) -> None:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path="x", source_lang="ja", target_lang="en"
        )
        _add_synth_volume(
            conn,
            project_id=project_id,
            title="TXT",
            source_format="txt",
            source_path="x.txt",
            chapters=[
                (
                    "c1",
                    0,
                    [
                        ("p1", "paragraph", "本文1", "translated", "EN1"),
                        ("p2", "paragraph", "本文2", "pending", None),
                    ],
                )
            ],
        )

    before = _count_translations(db_path)
    export_novel(project_toml)
    assert _count_translations(db_path) == before


# --------------------------------------------------------------------------- #
# TXT/HTML export never re-reads the original source file
# --------------------------------------------------------------------------- #


def test_txt_html_export_does_not_reread_source(tmp_path: Path, monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise AssertionError("source file was re-read during export")

    monkeypatch.setattr("weaver.readers.txt.read_txt", _boom)
    monkeypatch.setattr("weaver.readers.html.read_html", _boom)
    monkeypatch.setattr("weaver.readers.read_txt", _boom, raising=False)
    monkeypatch.setattr("weaver.readers.read_html", _boom, raising=False)

    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path="x", source_lang="ja", target_lang="en"
        )
        _add_synth_volume(
            conn,
            project_id=project_id,
            title="TXT",
            source_format="txt",
            source_path="x.txt",
            chapters=[("c1", 0, [("p1", "paragraph", "本文", "translated", "EN")])],
        )
        _add_synth_volume(
            conn,
            project_id=project_id,
            title="HTML",
            source_format="html",
            source_path="x.html",
            chapters=[("c2", 0, [("p1", "paragraph", "本文", "translated", "EN")])],
        )

    result = export_novel(project_toml)
    assert result.volumes_exported == 2


# --------------------------------------------------------------------------- #
# Selection rule: latest attempt only, manual preserved, hash-mismatch fallback
# --------------------------------------------------------------------------- #


def test_export_uses_latest_attempt_only(tmp_path: Path) -> None:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path="x", source_lang="ja", target_lang="en"
        )
        volume_id = create_volume(
            conn, project_id=project_id, title="T", source_path="x.txt", source_format="txt"
        )
        conn.execute(
            "INSERT INTO chapters (id, project_id, volume_id, title, href, spine_order) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("c1", project_id, volume_id, "c1", "c1.xhtml", 0),
        )
        insert_segment(
            conn,
            segment_id="c1-s0",
            chapter_id="c1",
            block_order=0,
            kind="paragraph",
            source_text="本文",
            source_hash="h",
            status="translated",
        )
        record_translation(
            conn, segment_id="c1-s0", text="OLD", source_hash="h", provider="fake", model="fake-1"
        )
        record_translation(
            conn, segment_id="c1-s0", text="NEW", source_hash="h", provider="fake", model="fake-1"
        )

    result = export_volume(project_toml, volume_id)
    body = _epub_text(result.artifacts[0].output_path)
    assert "NEW" in body
    assert "OLD" not in body


def test_translated_with_hash_mismatch_falls_back_as_untranslated(tmp_path: Path) -> None:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path="x", source_lang="ja", target_lang="en"
        )
        volume_id = create_volume(
            conn, project_id=project_id, title="T", source_path="x.txt", source_format="txt"
        )
        conn.execute(
            "INSERT INTO chapters (id, project_id, volume_id, title, href, spine_order) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("c1", project_id, volume_id, "c1", "c1.xhtml", 0),
        )
        insert_segment(
            conn,
            segment_id="c1-s0",
            chapter_id="c1",
            block_order=0,
            kind="paragraph",
            source_text="本文",
            source_hash="orig",
            status="translated",
        )
        record_translation(
            conn,
            segment_id="c1-s0",
            text="EN body",
            source_hash="orig",
            provider="fake",
            model="fake-1",
        )
        # Source changed after translation: latest attempt no longer matches.
        conn.execute("UPDATE segments SET source_hash = 'changed' WHERE id = 'c1-s0'")

    result = export_volume(project_toml, volume_id)
    artifact = result.artifacts[0]
    assert artifact.translated_segments == 0
    assert artifact.fallback_segments == 1
    assert artifact.fallback_by_status.untranslated == 1

    body = _epub_text(artifact.output_path)
    assert "本文" in body
    assert "EN body" not in body


# --------------------------------------------------------------------------- #
# Multi-volume naming: collision-safe on duplicate volume_order
# --------------------------------------------------------------------------- #


def test_duplicate_volume_order_produces_distinct_artifacts(tmp_path: Path) -> None:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path="x", source_lang="ja", target_lang="en"
        )
        for title, chapter_id in (("A", "a-c1"), ("B", "b-c1")):
            volume_id = create_volume(
                conn,
                project_id=project_id,
                title=title,
                source_path=f"{title}.txt",
                source_format="txt",
                volume_order=5,  # same order for both
            )
            conn.execute(
                "INSERT INTO chapters (id, project_id, volume_id, title, href, spine_order) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (chapter_id, project_id, volume_id, chapter_id, f"{chapter_id}.xhtml", 0),
            )
            insert_segment(
                conn,
                segment_id=f"{chapter_id}-s0",
                chapter_id=chapter_id,
                block_order=0,
                kind="paragraph",
                source_text="本文",
                source_hash=f"{chapter_id}-h",
                status="pending",
            )

    result = export_novel(project_toml)
    paths = [artifact.output_path for artifact in result.artifacts]
    assert len(set(paths)) == 2
    assert all(path.exists() for path in paths)


# --------------------------------------------------------------------------- #
# Scope routing + validation errors
# --------------------------------------------------------------------------- #


def _seed_minimal(tmp_path: Path) -> Path:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path="x", source_lang="ja", target_lang="en"
        )
        _add_synth_volume(
            conn,
            project_id=project_id,
            title="TXT",
            source_format="txt",
            source_path="x.txt",
            chapters=[
                ("c1", 0, [("p1", "paragraph", "本文1", "translated", "EN1")]),
                ("c2", 1, [("p1", "paragraph", "本文2", "translated", "EN2")]),
            ],
        )
    return project_toml


def test_export_chapter_single_chapter(tmp_path: Path) -> None:
    project_toml = _seed_minimal(tmp_path)
    result = export_chapter(project_toml, "c2")
    assert result.scope == "chapter"
    assert result.scope_id == "c2"
    assert result.chapters_exported == 1
    assert len(result.artifacts) == 1
    assert result.artifacts[0].output_path.name.startswith("chapter-")


def test_export_volume_filename_includes_id(tmp_path: Path) -> None:
    project_toml = _seed_minimal(tmp_path)
    result = export_volume(project_toml, 1)
    name = result.artifacts[0].output_path.name
    assert name.startswith("volume-")
    assert "id1" in name


def test_empty_novel_exports_nothing(tmp_path: Path) -> None:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        create_project(conn, name="demo", source_path="x", source_lang="ja", target_lang="en")

    result = export_novel(project_toml)
    assert result.volumes_total == 0
    assert result.artifacts == ()
    assert result.translated_segments == 0


def test_prepare_unknown_scope_raises(tmp_path: Path) -> None:
    project_toml = _seed_minimal(tmp_path)
    with pytest.raises(ValueError):
        prepare_export(project_toml, scope="bogus")


def test_prepare_unsupported_target_raises(tmp_path: Path) -> None:
    project_toml = _seed_minimal(tmp_path)
    with pytest.raises(ValueError):
        prepare_export(project_toml, scope="novel", target="pdf")


def test_prepare_missing_target_id_raises(tmp_path: Path) -> None:
    project_toml = _seed_minimal(tmp_path)
    with pytest.raises(ValueError):
        prepare_export(project_toml, scope="volume", target_id=None)


def test_export_unknown_volume_raises(tmp_path: Path) -> None:
    project_toml = _seed_minimal(tmp_path)
    with pytest.raises(VolumeNotFoundError):
        export_volume(project_toml, 9999)


def test_export_unknown_chapter_raises(tmp_path: Path) -> None:
    project_toml = _seed_minimal(tmp_path)
    with pytest.raises(ChapterNotFoundError):
        export_chapter(project_toml, "missing")


# --------------------------------------------------------------------------- #
# TXT / HTML output targets (Sprint 8C)
# --------------------------------------------------------------------------- #


def test_export_txt_target_novel(tmp_path: Path) -> None:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path="x", source_lang="ja", target_lang="en"
        )
        _add_synth_volume(
            conn,
            project_id=project_id,
            title="V",
            source_format="txt",
            source_path="x.txt",
            chapters=[
                (
                    "c1",
                    0,
                    [
                        ("p1", "paragraph", "本文1", "translated", "EN1"),
                        ("p2", "paragraph", "本文2", "pending", None),
                    ],
                )
            ],
        )

    result = export_novel(project_toml, target="txt")
    assert result.target == "txt"
    artifact = result.artifacts[0]
    assert artifact.output_path.suffix == ".txt"
    assert artifact.output_path.exists()
    assert artifact.translated_segments == 1
    assert artifact.fallback_segments == 1
    text = artifact.output_path.read_text(encoding="utf-8")
    assert "EN1" in text  # translated
    assert "本文2" in text  # source fallback


def test_export_html_target_volume_scope(tmp_path: Path) -> None:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path="x", source_lang="ja", target_lang="en"
        )
        volume_id = _add_synth_volume(
            conn,
            project_id=project_id,
            title="V",
            source_format="html",
            source_path="x.html",
            chapters=[
                (
                    "c1",
                    0,
                    [
                        ("h", "heading", "章", "manual", "MANUAL H"),
                        ("p1", "paragraph", "本文", "translated", "EN body"),
                    ],
                )
            ],
        )

    result = export_volume(project_toml, volume_id, target="html")
    assert result.target == "html"
    artifact = result.artifacts[0]
    assert artifact.output_path.suffix == ".html"
    assert artifact.output_path.exists()
    html = artifact.output_path.read_text(encoding="utf-8")
    assert "<h2>MANUAL H</h2>" in html
    assert "<p>EN body</p>" in html


def test_export_html_target_chapter_scope(tmp_path: Path) -> None:
    project_toml = _seed_minimal(tmp_path)
    result = export_chapter(project_toml, "c2", target="html")
    assert result.target == "html"
    assert result.chapters_exported == 1
    artifact = result.artifacts[0]
    assert artifact.output_path.suffix == ".html"
    assert artifact.output_path.name.startswith("chapter-")
    assert artifact.output_path.exists()


def test_export_txt_does_not_reread_epub_source(tmp_path: Path, monkeypatch) -> None:
    # An EPUB-source volume exported to TXT must build from the DB, never re-read
    # the source EPUB.
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path=str(FIXTURE_EPUB), source_lang="ja", target_lang="en"
        )
        _add_epub_volume(conn, project_id=project_id, translate_first_n=1)

    def _boom(*_args, **_kwargs):
        raise AssertionError("source EPUB was re-read during a TXT export")

    monkeypatch.setattr("weaver.services.export_book.read_epub", _boom)
    result = export_novel(project_toml, target="txt")
    assert result.artifacts[0].output_path.suffix == ".txt"
    assert result.artifacts[0].output_path.exists()


# --------------------------------------------------------------------------- #
# DOCX output target (Phase D)
# --------------------------------------------------------------------------- #


def _docx_document_xml(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read("word/document.xml").decode("utf-8")


def test_export_docx_target_novel(tmp_path: Path) -> None:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path="x", source_lang="ja", target_lang="en"
        )
        _add_synth_volume(
            conn,
            project_id=project_id,
            title="My Volume",
            source_format="txt",
            source_path="x.txt",
            chapters=[
                (
                    "c1",
                    0,
                    [
                        ("h", "heading", "章タイトル", "manual", "MANUAL HEADING"),
                        ("p1", "paragraph", "本文1", "translated", "EN BODY"),
                        ("p2", "paragraph", "本文2", "pending", None),
                    ],
                )
            ],
        )

    result = export_novel(project_toml, target="docx")
    assert result.target == "docx"
    artifact = result.artifacts[0]
    assert artifact.output_path.suffix == ".docx"
    assert artifact.output_path.exists()
    assert zipfile.is_zipfile(artifact.output_path)
    assert artifact.translated_segments == 2  # manual + translated
    assert artifact.fallback_segments == 1  # pending → source fallback

    document = _docx_document_xml(artifact.output_path)
    assert "My Volume" in document  # document title
    assert "MANUAL HEADING" in document  # manual edit preserved
    assert "EN BODY" in document  # latest translation
    assert "本文2" in document  # untranslated → source fallback
    assert '<w:pStyle w:val="Heading1"/>' in document  # heading block → Heading1


def test_export_docx_one_artifact_per_volume(tmp_path: Path) -> None:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path="x", source_lang="ja", target_lang="en"
        )
        for vol in ("A", "B"):
            _add_synth_volume(
                conn,
                project_id=project_id,
                title=f"Vol {vol}",
                source_format="txt",
                source_path=f"{vol}.txt",
                chapters=[(f"c{vol}", 0, [("p1", "paragraph", "本文", "translated", "EN")])],
            )

    result = export_novel(project_toml, target="docx")
    assert result.volumes_exported == 2
    assert len(result.artifacts) == 2
    suffixes = {a.output_path.suffix for a in result.artifacts}
    assert suffixes == {".docx"}
    assert all(a.output_path.exists() for a in result.artifacts)


def test_export_docx_volume_and_chapter_scope(tmp_path: Path) -> None:
    project_toml = _seed_minimal(tmp_path)  # txt volume id=1, chapters c1/c2

    vol_result = export_volume(project_toml, 1, target="docx")
    assert vol_result.target == "docx"
    vol_artifact = vol_result.artifacts[0]
    assert vol_artifact.output_path.name.startswith("volume-")
    assert vol_artifact.output_path.suffix == ".docx"
    assert vol_artifact.output_path.exists()

    ch_result = export_chapter(project_toml, "c2", target="docx")
    assert ch_result.target == "docx"
    assert ch_result.chapters_exported == 1
    ch_artifact = ch_result.artifacts[0]
    assert ch_artifact.output_path.name.startswith("chapter-")
    assert ch_artifact.output_path.suffix == ".docx"
    assert ch_artifact.output_path.exists()


def test_export_docx_writes_no_translation_rows(tmp_path: Path) -> None:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path="x", source_lang="ja", target_lang="en"
        )
        _add_synth_volume(
            conn,
            project_id=project_id,
            title="TXT",
            source_format="txt",
            source_path="x.txt",
            chapters=[
                (
                    "c1",
                    0,
                    [
                        ("p1", "paragraph", "本文1", "translated", "EN1"),
                        ("p2", "paragraph", "本文2", "pending", None),
                    ],
                )
            ],
        )

    before = _count_translations(db_path)
    export_novel(project_toml, target="docx")
    assert _count_translations(db_path) == before


def test_export_docx_does_not_reread_epub_source(tmp_path: Path, monkeypatch) -> None:
    # An EPUB-source volume exported to DOCX must build from the DB, never re-read
    # the source EPUB (DOCX has no write-back path).
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path=str(FIXTURE_EPUB), source_lang="ja", target_lang="en"
        )
        _add_epub_volume(conn, project_id=project_id, translate_first_n=1)

    def _boom(*_args, **_kwargs):
        raise AssertionError("source EPUB was re-read during a DOCX export")

    monkeypatch.setattr("weaver.services.export_book.read_epub", _boom)
    result = export_novel(project_toml, target="docx")
    assert result.artifacts[0].output_path.suffix == ".docx"
    assert result.artifacts[0].output_path.exists()


# --------------------------------------------------------------------------- #
# Combined ZIP bundle (Phase D)
# --------------------------------------------------------------------------- #


def _seed_two_volume_novel(tmp_path: Path) -> Path:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn, name="demo", source_path="x", source_lang="ja", target_lang="en"
        )
        for vol in ("A", "B"):
            _add_synth_volume(
                conn,
                project_id=project_id,
                title=f"Vol {vol}",
                source_format="txt",
                source_path=f"{vol}.txt",
                chapters=[(f"c{vol}", 0, [("p1", "paragraph", "本文", "translated", "EN")])],
            )
    return project_toml


def test_export_novel_bundle_zips_per_volume_artifacts(tmp_path: Path) -> None:
    project_toml = _seed_two_volume_novel(tmp_path)

    result = export_novel(project_toml, target="docx", bundle=True)

    assert result.bundle_path is not None
    assert result.bundle_path.exists()
    assert result.bundle_path.name == "bundle-docx.zip"
    # the per-volume artifacts still exist individually
    assert len(result.artifacts) == 2
    assert all(a.output_path.exists() for a in result.artifacts)
    # the ZIP contains exactly the per-volume artifacts, stored by basename
    with zipfile.ZipFile(result.bundle_path) as archive:
        names = sorted(archive.namelist())
    assert names == sorted(a.output_path.name for a in result.artifacts)
    assert all(name.endswith(".docx") for name in names)


def test_export_bundle_works_for_txt_target(tmp_path: Path) -> None:
    project_toml = _seed_two_volume_novel(tmp_path)
    result = export_novel(project_toml, target="txt", bundle=True)
    assert result.bundle_path is not None
    assert result.bundle_path.name == "bundle-txt.zip"
    with zipfile.ZipFile(result.bundle_path) as archive:
        assert all(name.endswith(".txt") for name in archive.namelist())


def test_export_without_bundle_has_no_bundle_path(tmp_path: Path) -> None:
    project_toml = _seed_two_volume_novel(tmp_path)
    result = export_novel(project_toml, target="txt")
    assert result.bundle_path is None


def test_bundle_skipped_when_no_artifacts(tmp_path: Path) -> None:
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        create_project(conn, name="demo", source_path="x", source_lang="ja", target_lang="en")

    result = export_novel(project_toml, target="txt", bundle=True)

    assert result.artifacts == ()
    assert result.bundle_path is None


def test_epub_export_generates_fidelity_reports(tmp_path: Path) -> None:
    """EPUB-sourced volumes produce fidelity reports on EPUB export (Sprint K4)."""
    project_toml, db_path = _init(tmp_path)
    with closing(initialize_database(db_path)) as conn, transaction(conn):
        project_id = create_project(
            conn,
            name="demo",
            source_path=str(FIXTURE_EPUB),
            source_lang="ja",
            target_lang="en",
        )
        _add_epub_volume(conn, project_id=project_id, translate_first_n=0)

    result = export_novel(project_toml)

    assert len(result.fidelity_reports) == 1
    report = result.fidelity_reports[0]
    assert report.source_path == FIXTURE_EPUB
    assert report.exported_path.exists()
    assert len(report.source_counts) > 0
    assert len(report.exported_counts) > 0
    assert len(report.passed_checks) >= 1

    # Non-EPUB target does not produce fidelity reports.
    txt_result = export_novel(project_toml, target="txt")
    assert len(txt_result.fidelity_reports) == 0


def test_atomic_epub_write_does_not_leak_partials(tmp_path: Path) -> None:
    """EPUB renderer writes atomically; failure leaves no partial file (Sprint K3)."""
    from ebooklib import epub

    from weaver.renderers._atomic import atomic_write_epub

    book = epub.EpubBook()
    book.set_identifier("urn:uuid:atomic")
    book.set_title("Atomic")
    book.set_language("en")

    output = tmp_path / "out.epub"
    atomic_write_epub(output, book)

    assert output.exists()
    partials = list(tmp_path.glob("*.partial"))
    assert len(partials) == 0


def test_atomic_text_write_does_not_leak_partials(tmp_path: Path) -> None:
    """Text renderer writes atomically; failure leaves no partial file (Sprint K3)."""
    from weaver.renderers._atomic import atomic_write_text

    output = tmp_path / "out.txt"
    atomic_write_text(output, "hello world")

    assert output.exists()
    assert output.read_text(encoding="utf-8") == "hello world"
    partials = list(tmp_path.glob("*.partial"))
    assert len(partials) == 0
