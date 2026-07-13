"""Equivalence regression for the chapter-scoped rolling-window CTE (v0.7.3 M1.2).

The rolling-window / export-state queries were rewritten from an *unscoped*
``GROUP BY segment_id`` over the whole ``translations`` table (O(n²) across a
run) to a chapter-scoped CTE. Because a segment belongs to exactly one chapter,
``MAX(attempt)`` per segment is identical either way, so the results must be
byte-identical. These tests pin that by comparing the shipped functions against
the pre-M1.2 global-CTE SQL run inline as a reference oracle.
"""

from __future__ import annotations

from weaver.storage.db import initialize_database
from weaver.storage.projects import create_project
from weaver.storage.segments import insert_segment, update_segment_status
from weaver.storage.translations import (
    list_export_segment_states,
    list_previous_translated_segments,
    record_translation,
)

# Pre-M1.2 SQL (unscoped `latest` CTE) kept verbatim as the equivalence oracle.
_OLD_PREVIOUS_SQL = """
    WITH latest AS (
      SELECT segment_id, MAX(attempt) AS attempt
      FROM translations
      GROUP BY segment_id
    )
    SELECT s.source_text, t.text
    FROM segments s
    JOIN latest l ON l.segment_id = s.id
    JOIN translations t ON t.segment_id = l.segment_id AND t.attempt = l.attempt
    WHERE s.chapter_id = ?
      AND s.block_order < ?
      AND s.status IN ('translated', 'manual')
      AND t.source_hash = s.source_hash
    ORDER BY s.block_order DESC
    LIMIT ?
"""


def _old_previous(connection, *, chapter_id, before_block_order, limit=5):
    rows = connection.execute(_OLD_PREVIOUS_SQL, (chapter_id, before_block_order, limit)).fetchall()
    return [(str(row["source_text"]), str(row["text"])) for row in reversed(rows)]


def _old_export(connection, *, chapter_ids):
    ids = list(chapter_ids)
    if not ids:
        return []
    placeholders = ", ".join("?" for _ in ids)
    rows = connection.execute(
        f"""
        WITH latest AS (
          SELECT segment_id, MAX(attempt) AS attempt
          FROM translations
          GROUP BY segment_id
        )
        SELECT
          s.id AS id,
          s.status AS status,
          CASE
            WHEN s.status IN ('translated', 'manual') AND t.source_hash = s.source_hash
            THEN t.text
            ELSE NULL
          END AS publishable_text
        FROM segments s
        LEFT JOIN latest l ON l.segment_id = s.id
        LEFT JOIN translations t
          ON t.segment_id = l.segment_id
         AND t.attempt = l.attempt
        WHERE s.chapter_id IN ({placeholders})
        ORDER BY s.chapter_id, s.block_order
        """,
        ids,
    ).fetchall()
    return [(str(r["id"]), str(r["status"]), r["publishable_text"]) for r in rows]


def _add_chapter(connection, project_id: int, chapter_id: str, order: int) -> None:
    connection.execute(
        "INSERT INTO chapters (id, project_id, title, href, spine_order) VALUES (?, ?, ?, ?, ?)",
        (chapter_id, project_id, chapter_id, f"text/{chapter_id}.xhtml", order),
    )


def _seed_multi_chapter(connection) -> int:
    """Build 3 chapters with mixed statuses, multi-attempt rows, and a hash mismatch."""

    project_id = create_project(
        connection,
        name="fixture",
        source_path="fixture.epub",
        source_lang="ja",
        target_lang="en",
    )
    for order, chapter_id in enumerate(("chapter-a", "chapter-b", "chapter-c")):
        _add_chapter(connection, project_id, chapter_id, order)

    # chapter-a: translated (2 attempts), manual, pending (no tx), hash-mismatch.
    _seg(connection, "a1", "chapter-a", 0, "hash-a1")
    record_translation(
        connection, segment_id="a1", text="A1 v1", source_hash="hash-a1", provider="fake", model="m"
    )
    record_translation(
        connection, segment_id="a1", text="A1 v2", source_hash="hash-a1", provider="fake", model="m"
    )
    update_segment_status(connection, segment_id="a1", status="translated")

    _seg(connection, "a2", "chapter-a", 1, "hash-a2")
    record_translation(
        connection, segment_id="a2", text="A2", source_hash="hash-a2", provider="fake", model="m"
    )
    update_segment_status(connection, segment_id="a2", status="manual")

    _seg(connection, "a3", "chapter-a", 2, "hash-a3")  # pending, no translation

    _seg(connection, "a4", "chapter-a", 3, "hash-a4")
    record_translation(
        connection,
        segment_id="a4",
        text="A4 stale-hash",
        source_hash="OLD-hash",
        provider="fake",
        model="m",
    )
    update_segment_status(connection, segment_id="a4", status="translated")

    # chapter-b and chapter-c: translated rows to prove cross-chapter isolation.
    _seg(connection, "b1", "chapter-b", 0, "hash-b1")
    record_translation(
        connection, segment_id="b1", text="B1", source_hash="hash-b1", provider="fake", model="m"
    )
    update_segment_status(connection, segment_id="b1", status="translated")

    _seg(connection, "c1", "chapter-c", 0, "hash-c1")
    record_translation(
        connection, segment_id="c1", text="C1", source_hash="hash-c1", provider="fake", model="m"
    )
    update_segment_status(connection, segment_id="c1", status="translated")
    return project_id


def _seg(connection, seg: str, chapter_id: str, order: int, source_hash: str) -> None:
    insert_segment(
        connection,
        segment_id=seg,
        chapter_id=chapter_id,
        block_order=order,
        kind="paragraph",
        source_text=f"src-{seg}",
        source_hash=source_hash,
    )


def test_previous_window_matches_unscoped_reference(tmp_path) -> None:
    with initialize_database(tmp_path / "weaver.db") as connection:
        _seed_multi_chapter(connection)
        for chapter_id in ("chapter-a", "chapter-b", "chapter-c"):
            for before in (0, 1, 2, 3, 4, 99):
                expected = _old_previous(
                    connection, chapter_id=chapter_id, before_block_order=before
                )
                actual = list_previous_translated_segments(
                    connection, chapter_id=chapter_id, before_block_order=before
                )
                assert actual == expected, (chapter_id, before)


def test_previous_window_excludes_hash_mismatch_and_pending(tmp_path) -> None:
    with initialize_database(tmp_path / "weaver.db") as connection:
        _seed_multi_chapter(connection)
        pairs = list_previous_translated_segments(
            connection, chapter_id="chapter-a", before_block_order=99
        )
    # a3 (pending) and a4 (hash mismatch) excluded; a1 uses latest attempt (v2).
    assert pairs == [("src-a1", "A1 v2"), ("src-a2", "A2")]


def test_export_states_match_unscoped_reference(tmp_path) -> None:
    with initialize_database(tmp_path / "weaver.db") as connection:
        _seed_multi_chapter(connection)
        for chapter_ids in (
            ["chapter-a"],
            ["chapter-b"],
            ["chapter-a", "chapter-b"],
            ["chapter-a", "chapter-b", "chapter-c"],
        ):
            expected = _old_export(connection, chapter_ids=chapter_ids)
            actual = [
                (s.id, s.status, s.publishable_text)
                for s in list_export_segment_states(connection, chapter_ids=chapter_ids)
            ]
            assert actual == expected, chapter_ids


def test_export_states_hash_mismatch_yields_null_publishable(tmp_path) -> None:
    with initialize_database(tmp_path / "weaver.db") as connection:
        _seed_multi_chapter(connection)
        states = {
            s.id: s for s in list_export_segment_states(connection, chapter_ids=["chapter-a"])
        }
    assert states["a1"].publishable_text == "A1 v2"
    assert states["a2"].publishable_text == "A2"
    assert states["a3"].publishable_text is None  # pending
    assert states["a4"].publishable_text is None  # latest attempt hash mismatch
