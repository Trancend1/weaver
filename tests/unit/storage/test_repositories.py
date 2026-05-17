"""Repository function tests for Phase 2 storage."""

from __future__ import annotations

import time

from weaver.core.ir import (
    BlockIR,
    ChapterIR,
    DocumentIR,
    DocumentMetadata,
    EpubMarkupContext,
)
from weaver.storage.db import initialize_database
from weaver.storage.projects import create_project
from weaver.storage.segments import (
    insert_segment,
    list_pending_segments,
    reset_in_progress_segments,
    sync_document_segments,
    update_segment_status,
)
from weaver.storage.translations import record_translation


def test_sync_document_segments_inserts_chapters_and_pending_segments(tmp_path) -> None:
    db_path = tmp_path / "weaver.db"
    document = _document_with_text("吾輩は猫である。")

    with initialize_database(db_path) as connection:
        project_id = create_project(
            connection,
            name="fixture",
            source_path="fixture.epub",
            source_lang="ja",
            target_lang="en",
        )
        sync_document_segments(connection, project_id=project_id, document=document)
        segments = connection.execute(
            "SELECT id, source_hash, status FROM segments ORDER BY block_order"
        ).fetchall()
        chapters = connection.execute("SELECT id, spine_order FROM chapters").fetchall()

    assert len(chapters) == 1
    assert len(segments) == 1
    assert segments[0]["id"] == "seg-1"
    assert segments[0]["source_hash"]
    assert segments[0]["status"] == "pending"


def test_sync_document_segments_marks_existing_changed_segment_stale(tmp_path) -> None:
    db_path = tmp_path / "weaver.db"

    with initialize_database(db_path) as connection:
        project_id = create_project(
            connection,
            name="fixture",
            source_path="fixture.epub",
            source_lang="ja",
            target_lang="en",
        )
        sync_document_segments(
            connection,
            project_id=project_id,
            document=_document_with_text("吾輩は猫である。"),
        )
        update_segment_status(connection, segment_id="seg-1", status="translated")
        record_translation(
            connection,
            segment_id="seg-1",
            text="I am a cat.",
            source_hash="old-hash",
            provider="fake",
            model="fake-model",
        )
        sync_document_segments(
            connection,
            project_id=project_id,
            document=_document_with_text("吾輩は犬である。"),
        )
        segment = connection.execute(
            "SELECT status, source_hash FROM segments WHERE id = 'seg-1'"
        ).fetchone()

    assert segment["status"] == "stale"
    assert segment["source_hash"] != "old-hash"


def test_repository_functions_update_status_record_translation_and_list_pending(tmp_path) -> None:
    db_path = tmp_path / "weaver.db"

    with initialize_database(db_path) as connection:
        project_id = create_project(
            connection,
            name="fixture",
            source_path="fixture.epub",
            source_lang="ja",
            target_lang="en",
        )
        sync_document_segments(
            connection,
            project_id=project_id,
            document=_document_with_text("一。"),
        )
        insert_segment(
            connection,
            segment_id="seg-2",
            chapter_id="chapter-1",
            block_order=1,
            kind="paragraph",
            source_text="二。",
            source_hash="hash-2",
        )
        update_segment_status(connection, segment_id="seg-1", status="translated")
        record_translation(
            connection,
            segment_id="seg-1",
            text="One.",
            source_hash="hash-1",
            provider="fake",
            model="fake-model",
        )

        pending = list_pending_segments(connection, project_id=project_id)
        translation = connection.execute(
            "SELECT attempt, text FROM translations WHERE segment_id = 'seg-1'"
        ).fetchone()

    assert [segment.id for segment in pending] == ["seg-2"]
    assert translation["attempt"] == 1
    assert translation["text"] == "One."


def test_reset_in_progress_and_10000_segment_pending_scan_stays_under_budget(tmp_path) -> None:
    db_path = tmp_path / "weaver.db"

    with initialize_database(db_path) as connection:
        project_id = create_project(
            connection,
            name="fixture",
            source_path="fixture.epub",
            source_lang="ja",
            target_lang="en",
        )
        connection.execute(
            """
            INSERT INTO chapters (id, project_id, title, href, spine_order)
            VALUES ('chapter-1', ?, 'Chapter', 'text/chapter.xhtml', 0)
            """,
            (project_id,),
        )
        for index in range(10_000):
            insert_segment(
                connection,
                segment_id=f"seg-{index:05d}",
                chapter_id="chapter-1",
                block_order=index,
                kind="paragraph",
                source_text=f"source {index}",
                source_hash=f"hash-{index}",
                status="in_progress" if index < 3 else "pending",
            )
        reset_in_progress_segments(connection)

        started = time.perf_counter()
        pending = list_pending_segments(connection, project_id=project_id)
        elapsed = time.perf_counter() - started

    assert len(pending) == 10_000
    assert elapsed < 5


def _document_with_text(source_text: str) -> DocumentIR:
    return DocumentIR(
        metadata=DocumentMetadata(
            title="Fixture",
            author=None,
            language="ja",
            identifier="fixture-id",
            publisher=None,
            description=None,
        ),
        assets=[],
        chapters=[
            ChapterIR(
                id="chapter-1",
                title="Chapter",
                href="text/chapter.xhtml",
                order=0,
                blocks=[
                    BlockIR(
                        id="seg-1",
                        chapter_id="chapter-1",
                        order=0,
                        kind="paragraph",
                        source_text=source_text,
                        normalized_source_text=source_text,
                        markup_context=EpubMarkupContext(
                            file_href="text/chapter.xhtml",
                            xpath="/html/body/p[1]",
                            tag="p",
                            attrs={},
                            text_node_index=0,
                        ),
                    )
                ],
            )
        ],
    )
