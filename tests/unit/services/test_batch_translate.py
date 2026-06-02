"""Tests for batch (chapter/volume/novel) translation planning + run (Sprint 7A)."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest

from weaver.errors import ChapterNotFoundError, VolumeNotFoundError
from weaver.services.batch_translate import (
    BatchTranslationResult,
    prepare_batch_translation,
    run_batch_translation,
)
from weaver.storage.db import initialize_database, transaction
from weaver.storage.projects import create_project
from weaver.storage.segments import insert_segment
from weaver.storage.volumes import create_volume

_PROJECT_TOML = """\
[project]
name = "demo"
source_file = "book.epub"
database_path = "state.db"
output_dir = "out"

[provider]
type = "fake"
model = "fake-1"
pattern = "EN: {source}"

[translation]
source_lang = "ja"
target_lang = "en"
honorifics = "preserve"
"""


def _seed(tmp_path: Path, volumes: list[list[tuple[str, list]]]) -> Path:
    """Create a project DB from a nested Novel -> Volume -> Chapter structure.

    Args:
        tmp_path: Test temp dir.
        volumes: list of volumes; each volume is a list of
            ``(chapter_id, [segment_spec, ...])`` chapters created in order. A
            segment spec is a status string (auto unique source_hash) or a
            ``(status, source_hash)`` tuple to force a translation-memory match.

    Returns the project.toml path. Volume ids are assigned 1, 2, ... in order.
    """

    project_toml = tmp_path / "project.toml"
    project_toml.write_text(_PROJECT_TOML, encoding="utf-8")

    with closing(initialize_database(tmp_path / "state.db")) as conn, transaction(conn):
        project_id = create_project(
            conn,
            name="demo",
            source_path="book.epub",
            source_lang="ja",
            target_lang="en",
        )
        for volume in volumes:
            volume_id = create_volume(
                conn,
                project_id=project_id,
                title="Volume",
                source_path="book.epub",
                source_format="epub",
            )
            for spine, (chapter_id, segments) in enumerate(volume):
                conn.execute(
                    "INSERT INTO chapters (id, project_id, volume_id, title, href, spine_order) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (chapter_id, project_id, volume_id, chapter_id, f"{chapter_id}.xhtml", spine),
                )
                for index, spec in enumerate(segments):
                    status, source_hash = (
                        spec if isinstance(spec, tuple) else (spec, f"{chapter_id}-{index}")
                    )
                    insert_segment(
                        conn,
                        segment_id=f"{chapter_id}-seg{index}",
                        chapter_id=chapter_id,
                        block_order=index,
                        kind="paragraph",
                        source_text=f"こんにちは{index}",
                        source_hash=source_hash,
                        status=status,
                    )
    return project_toml


# --------------------------------------------------------------------------- #
# prepare: scope resolution + ordering
# --------------------------------------------------------------------------- #


def test_prepare_novel_orders_chapters_deterministically(tmp_path: Path) -> None:
    project_toml = _seed(
        tmp_path,
        [
            [("v1c1", ["pending"]), ("v1c2", ["pending"])],
            [("v2c1", ["pending"])],
        ],
    )
    plan = prepare_batch_translation(project_toml, scope="novel")
    assert [p.chapter_id for p in plan.chapter_plans] == ["v1c1", "v1c2", "v2c1"]
    assert plan.chapters_total == 3
    assert plan.scope_id is None


def test_prepare_volume_scope_limits_to_volume(tmp_path: Path) -> None:
    project_toml = _seed(
        tmp_path,
        [
            [("v1c1", ["pending"]), ("v1c2", ["pending"])],
            [("v2c1", ["pending"])],
        ],
    )
    plan = prepare_batch_translation(project_toml, scope="volume", target_id="1")
    assert [p.chapter_id for p in plan.chapter_plans] == ["v1c1", "v1c2"]
    assert plan.scope_id == "1"


def test_prepare_chapter_scope_single_chapter(tmp_path: Path) -> None:
    project_toml = _seed(tmp_path, [[("v1c1", ["pending"]), ("v1c2", ["pending"])]])
    plan = prepare_batch_translation(project_toml, scope="chapter", target_id="v1c2")
    assert [p.chapter_id for p in plan.chapter_plans] == ["v1c2"]
    assert plan.chapters_total == 1


def test_prepare_unknown_chapter_raises(tmp_path: Path) -> None:
    project_toml = _seed(tmp_path, [[("v1c1", ["pending"])]])
    with pytest.raises(ChapterNotFoundError):
        prepare_batch_translation(project_toml, scope="chapter", target_id="missing")


def test_prepare_unknown_volume_raises(tmp_path: Path) -> None:
    project_toml = _seed(tmp_path, [[("v1c1", ["pending"])]])
    with pytest.raises(VolumeNotFoundError):
        prepare_batch_translation(project_toml, scope="volume", target_id="9999")


def test_prepare_invalid_scope_raises(tmp_path: Path) -> None:
    project_toml = _seed(tmp_path, [[("v1c1", ["pending"])]])
    with pytest.raises(ValueError):
        prepare_batch_translation(project_toml, scope="bogus")


def test_prepare_invalid_mode_raises(tmp_path: Path) -> None:
    project_toml = _seed(tmp_path, [[("v1c1", ["pending"])]])
    with pytest.raises(ValueError):
        prepare_batch_translation(project_toml, scope="novel", mode="bogus")


def test_prepare_missing_target_id_raises(tmp_path: Path) -> None:
    project_toml = _seed(tmp_path, [[("v1c1", ["pending"])]])
    with pytest.raises(ValueError):
        prepare_batch_translation(project_toml, scope="chapter", target_id=None)


def test_prepare_segments_total_honors_mode(tmp_path: Path) -> None:
    project_toml = _seed(tmp_path, [[("v1c1", ["pending", "translated", "manual"])]])
    skip = prepare_batch_translation(project_toml, scope="novel", mode="skip_existing")
    non_manual = prepare_batch_translation(
        project_toml, scope="novel", mode="retranslate_non_manual"
    )
    force = prepare_batch_translation(project_toml, scope="novel", mode="force_selected")
    assert skip.segments_total == 1
    assert non_manual.segments_total == 2
    assert force.segments_total == 3


# --------------------------------------------------------------------------- #
# prepare/run: empty scope is valid (done(0)), not an error
# --------------------------------------------------------------------------- #


def test_empty_novel_is_done_zero(tmp_path: Path) -> None:
    project_toml = _seed(tmp_path, [[]])  # one volume, no chapters
    plan = prepare_batch_translation(project_toml, scope="novel")
    assert plan.chapters_total == 0
    assert plan.segments_total == 0
    result = run_batch_translation(plan)
    assert result.chapters_done == 0
    assert result.translated == 0
    assert result.failed == 0
    assert result.skipped == 0
    assert result.cancelled is False


def test_empty_volume_is_done_zero(tmp_path: Path) -> None:
    project_toml = _seed(tmp_path, [[]])  # volume 1 with no chapters
    plan = prepare_batch_translation(project_toml, scope="volume", target_id="1")
    assert plan.chapters_total == 0
    result = run_batch_translation(plan)
    assert result.chapters_done == 0
    assert result.cancelled is False


# --------------------------------------------------------------------------- #
# run: aggregation + invariants
# --------------------------------------------------------------------------- #


def test_run_aggregates_counts_across_chapters(tmp_path: Path) -> None:
    project_toml = _seed(
        tmp_path,
        [
            [("v1c1", ["pending", "pending"]), ("v1c2", ["pending"])],
            [("v2c1", ["pending"])],
        ],
    )
    plan = prepare_batch_translation(project_toml, scope="novel")
    result = run_batch_translation(plan)
    assert isinstance(result, BatchTranslationResult)
    assert result.segments_total == 4
    assert result.translated == 4
    assert result.failed == 0
    assert result.chapters_done == 3
    # invariant: translated + failed == segments_total on full completion
    assert result.translated + result.failed == result.segments_total
    assert result.reused_from_memory <= result.translated
    assert len(result.chapters) == 3
    assert {c.chapter_id for c in result.chapters} == {"v1c1", "v1c2", "v2c1"}
    # timing populated for observability
    assert result.started_at
    assert result.finished_at
    assert result.duration_seconds >= 0.0


def test_run_skipped_aggregated(tmp_path: Path) -> None:
    project_toml = _seed(tmp_path, [[("v1c1", ["pending", "translated"])]])
    plan = prepare_batch_translation(project_toml, scope="novel")
    result = run_batch_translation(plan)
    assert result.segments_total == 1
    assert result.translated == 1
    assert result.skipped == 1


def test_run_reused_from_memory_aggregated(tmp_path: Path) -> None:
    # Two segments sharing a source_hash: the first populates TM, the second
    # is served from memory (skip_existing enables lookup-before-AI).
    project_toml = _seed(
        tmp_path,
        [[("v1c1", [("pending", "dup-hash"), ("pending", "dup-hash")])]],
    )
    plan = prepare_batch_translation(project_toml, scope="novel")
    result = run_batch_translation(plan)
    assert result.translated == 2
    assert result.reused_from_memory == 1
    assert result.reused_from_memory <= result.translated
    assert result.chapters[0].reused_from_memory == 1


def test_run_protects_manual_unless_force(tmp_path: Path) -> None:
    project_toml = _seed(tmp_path, [[("v1c1", ["manual"])]])
    skip_plan = prepare_batch_translation(project_toml, scope="novel", mode="skip_existing")
    assert skip_plan.segments_total == 0
    non_manual_plan = prepare_batch_translation(
        project_toml, scope="novel", mode="retranslate_non_manual"
    )
    assert non_manual_plan.segments_total == 0
    force_plan = prepare_batch_translation(project_toml, scope="novel", mode="force_selected")
    assert force_plan.segments_total == 1


# --------------------------------------------------------------------------- #
# run: cancellation at both levels
# --------------------------------------------------------------------------- #


def test_run_cancel_before_first_chapter(tmp_path: Path) -> None:
    project_toml = _seed(tmp_path, [[("v1c1", ["pending", "pending"]), ("v1c2", ["pending"])]])
    plan = prepare_batch_translation(project_toml, scope="novel")
    result = run_batch_translation(plan, should_cancel=lambda: True)
    assert result.cancelled is True
    assert result.chapters_done == 0
    assert result.translated == 0
    assert result.chapters == ()


def test_run_cancel_mid_chapter(tmp_path: Path) -> None:
    project_toml = _seed(
        tmp_path,
        [[("v1c1", ["pending", "pending", "pending"]), ("v1c2", ["pending"])]],
    )
    plan = prepare_batch_translation(project_toml, scope="novel")

    # Calls: #1 batch-before-c1 (False), #2 before segA (False) -> translate A,
    # #3 before segB (True) -> stop mid-chapter; c2 never starts.
    calls = {"n": 0}

    def should_cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    result = run_batch_translation(plan, should_cancel=should_cancel)
    assert result.cancelled is True
    assert result.chapters_done == 1
    assert result.translated == 1
    assert len(result.chapters) == 1
    assert result.chapters[0].chapter_id == "v1c1"
    assert result.chapters[0].cancelled is True
