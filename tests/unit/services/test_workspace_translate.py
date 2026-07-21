"""Tests for chapter-/selection-scoped AI translation (Sprint 4A)."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import replace
from pathlib import Path

import pytest

from weaver.core.connection_registry import Connection, register_connection
from weaver.errors import ChapterNotFoundError, ProviderUnavailable, SegmentNotFoundError
from weaver.providers.fake import FakeProvider
from weaver.services.config_writer import set_routing
from weaver.services.project import initialize_project
from weaver.services.workspace_edit import save_segment_translation
from weaver.services.workspace_translate import (
    prepare_chapter_translation,
    run_translation,
)
from weaver.storage.db import connect_database, transaction
from weaver.storage.segments import update_segment_status

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def _set_fake_provider(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = ""', 'type = "fake"')
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = ""', 'model = "fake-1"\npattern = "EN: {source}"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"\npattern = "EN: {source}"')
    project_toml.write_text(text, encoding="utf-8")


def _register_fake_connection(name: str, model: str = "fake-1") -> None:
    """Register a `fake`-protocol connection so the cockpit path can run offline."""

    register_connection(
        Connection(
            name=name,
            base_url="https://fake.invalid/v1",
            api_key_env="",
            default_model=model,
            protocol="fake",
            requires_key=False,
        )
    )


def _register_dead_connection(name: str) -> None:
    """Register a real-protocol connection to a closed local port (dead primary)."""

    register_connection(
        Connection(
            name=name,
            base_url="http://127.0.0.1:9/v1",
            api_key_env="",
            default_model="dead-1",
            protocol="openai_chat",
            requires_key=False,
            timeout_seconds=1.0,
        )
    )


def _first_chapter_id(db_path: Path) -> str:
    with sqlite3.connect(db_path) as connection:
        return str(
            connection.execute(
                "SELECT chapter_id FROM segments ORDER BY block_order LIMIT 1"
            ).fetchone()[0]
        )


def _chapter_segment_ids(db_path: Path, chapter_id: str) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        return [
            str(row[0])
            for row in connection.execute(
                "SELECT id FROM segments WHERE chapter_id = ? ORDER BY block_order",
                (chapter_id,),
            ).fetchall()
        ]


def _status(db_path: Path, segment_id: str) -> str:
    with sqlite3.connect(db_path) as connection:
        return str(
            connection.execute(
                "SELECT status FROM segments WHERE id = ?", (segment_id,)
            ).fetchone()[0]
        )


def _count_translations(db_path: Path) -> int:
    with sqlite3.connect(db_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM translations").fetchone()[0])


def _attempt_texts(db_path: Path, segment_id: str) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        return [
            str(row[0])
            for row in connection.execute(
                "SELECT text FROM translations WHERE segment_id = ? ORDER BY attempt",
                (segment_id,),
            ).fetchall()
        ]


def test_chapter_translate_translates_all_pending(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)

    plan = prepare_chapter_translation(init.project_toml, chapter_id)
    result = run_translation(plan)

    assert plan.mode == "chapter"
    assert result.selected == len(segment_ids)
    assert result.translated == len(segment_ids)
    assert result.failed == 0
    assert result.skipped == 0
    assert _count_translations(init.database_path) == len(segment_ids)
    for segment_id in segment_ids:
        assert _status(init.database_path, segment_id) == "translated"


def test_selection_translate_only_given_segments(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)
    chosen = segment_ids[:2]

    plan = prepare_chapter_translation(init.project_toml, chapter_id, segment_ids=chosen)
    result = run_translation(plan)

    assert plan.mode == "selection"
    assert result.selected == 2
    assert result.translated == 2
    for segment_id in chosen:
        assert _status(init.database_path, segment_id) == "translated"
    for segment_id in segment_ids[2:]:
        assert _status(init.database_path, segment_id) == "pending"


def test_chapter_translate_skips_already_translated(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)
    with connect_database(init.database_path) as connection, transaction(connection):
        update_segment_status(connection, segment_id=segment_ids[0], status="translated")

    plan = prepare_chapter_translation(init.project_toml, chapter_id)
    result = run_translation(plan)

    assert result.selected == len(segment_ids) - 1
    assert result.skipped == 1
    assert result.translated == len(segment_ids) - 1
    assert segment_ids[0] not in plan.target_segment_ids


def test_prepare_rejects_unknown_chapter(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)

    with pytest.raises(ChapterNotFoundError):
        prepare_chapter_translation(init.project_toml, "does-not-exist")


def test_prepare_rejects_segment_from_other_chapter(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)

    with pytest.raises(SegmentNotFoundError):
        prepare_chapter_translation(init.project_toml, chapter_id, segment_ids=["nope"])


def test_prepare_rejects_empty_selection(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)

    with pytest.raises(ValueError):
        prepare_chapter_translation(init.project_toml, chapter_id, segment_ids=[])


def test_provider_override_runs_fake_without_editing_config(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)  # default provider left unchanged
    chapter_id = _first_chapter_id(init.database_path)

    plan = prepare_chapter_translation(
        init.project_toml,
        chapter_id,
        provider_override={"type": "fake", "model": "fake-1"},
    )
    result = run_translation(plan)

    assert plan.provider.name == "fake"
    assert plan.provider_model == "fake-1"
    assert result.translated == result.selected
    assert result.translated > 0


def test_prepare_rejects_unknown_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)

    with pytest.raises(ValueError):
        prepare_chapter_translation(init.project_toml, chapter_id, mode="bogus")


def test_skip_existing_skips_everything_once_translated(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)
    run_translation(prepare_chapter_translation(init.project_toml, chapter_id))

    plan = prepare_chapter_translation(init.project_toml, chapter_id)  # skip_existing default
    result = run_translation(plan)

    assert plan.target_segment_ids == ()
    assert result.selected == 0
    assert result.skipped == len(segment_ids)


def test_retranslate_non_manual_retranslates_translated_protects_manual(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)
    run_translation(prepare_chapter_translation(init.project_toml, chapter_id))  # all translated
    save_segment_translation(init.project_toml, chapter_id, segment_ids[0], "hand edit")  # manual

    plan = prepare_chapter_translation(init.project_toml, chapter_id, mode="retranslate_non_manual")
    run_translation(plan)

    assert segment_ids[0] not in plan.target_segment_ids  # manual protected
    assert set(segment_ids[1:]) <= set(plan.target_segment_ids)  # translated retranslated
    assert _status(init.database_path, segment_ids[0]) == "manual"


def test_force_selected_overwrites_manual_and_appends_attempt(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)
    save_segment_translation(init.project_toml, chapter_id, segment_ids[0], "hand edit")
    before = _attempt_texts(init.database_path, segment_ids[0])

    plan = prepare_chapter_translation(
        init.project_toml, chapter_id, segment_ids=[segment_ids[0]], mode="force_selected"
    )
    result = run_translation(plan)

    assert plan.target_segment_ids == (segment_ids[0],)
    assert result.translated == 1
    after = _attempt_texts(init.database_path, segment_ids[0])
    assert len(after) == len(before) + 1  # append-only
    assert "hand edit" in after  # prior manual attempt preserved as history
    assert _status(init.database_path, segment_ids[0]) == "translated"


def test_connection_first_project_translates_via_routing(tmp_path, monkeypatch) -> None:
    # Regression (ADR 018): a connection-first project sets its model under
    # [routing.translate] (Active AI) and leaves [provider] model empty. The
    # cockpit chapter path must resolve routing — not raise "no model configured".
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WEAVER_CONNECTIONS_PATH", str(tmp_path / "connections.toml"))
    init = initialize_project(FIXTURE_EPUB)  # [provider] model left empty on purpose
    _register_fake_connection("localfake")
    set_routing(init.project_toml, task="translate", connection="localfake", model="fake-1")
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)

    plan = prepare_chapter_translation(init.project_toml, chapter_id)
    result = run_translation(plan)

    assert plan.provider.name == "fake"
    assert plan.provider_model == "fake-1"
    assert result.translated == len(segment_ids)
    assert result.failed == 0


def test_dead_primary_with_healthy_fallback_completes_run(tmp_path, monkeypatch) -> None:
    # Audit A1: a dead primary must not abort a run that has a healthy fallback —
    # the per-segment try-next chain cold-marks the primary and carries the run.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WEAVER_CONNECTIONS_PATH", str(tmp_path / "connections.toml"))
    init = initialize_project(FIXTURE_EPUB)
    _register_dead_connection("deadprimary")
    _register_fake_connection("backup", model="fake-2")
    set_routing(
        init.project_toml,
        task="translate",
        connection="deadprimary",
        model="dead-1",
        fallbacks=[("backup", "fake-2")],
    )
    chapter_id = _first_chapter_id(init.database_path)
    segment_ids = _chapter_segment_ids(init.database_path, chapter_id)

    plan = prepare_chapter_translation(init.project_toml, chapter_id)

    assert plan.preflight_warning is not None
    assert "deadprimary" in plan.preflight_warning or "openai_chat" in plan.preflight_warning

    result = run_translation(plan)

    assert result.translated == len(segment_ids)
    assert result.failed == 0
    assert result.preflight_warning == plan.preflight_warning


def test_dead_primary_without_fallback_still_aborts(tmp_path, monkeypatch) -> None:
    # Audit A1 boundary: with no fallback configured, the pre-flight abort stands.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WEAVER_CONNECTIONS_PATH", str(tmp_path / "connections.toml"))
    init = initialize_project(FIXTURE_EPUB)
    _register_dead_connection("deadprimary")
    set_routing(init.project_toml, task="translate", connection="deadprimary", model="dead-1")
    chapter_id = _first_chapter_id(init.database_path)

    with pytest.raises(ProviderUnavailable) as exc_info:
        prepare_chapter_translation(init.project_toml, chapter_id)

    assert "is unavailable" in str(exc_info.value)


def test_routing_fallback_chain_lands_on_the_plan(tmp_path, monkeypatch) -> None:
    # The cockpit plan must carry the configured fallback engines (ADR 018 D4) so
    # run_translation can try-next per segment, matching translate_project (CLI).
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WEAVER_CONNECTIONS_PATH", str(tmp_path / "connections.toml"))
    init = initialize_project(FIXTURE_EPUB)
    _register_fake_connection("primary")
    _register_fake_connection("backup", model="fake-2")
    set_routing(
        init.project_toml,
        task="translate",
        connection="primary",
        model="fake-1",
        fallbacks=[("backup", "fake-2")],
    )
    chapter_id = _first_chapter_id(init.database_path)

    plan = prepare_chapter_translation(init.project_toml, chapter_id)

    assert plan.provider_model == "fake-1"
    assert [model for _provider, model in plan.fallback_engines] == ["fake-2"]
    assert plan.fallback_engines[0][0].name == "fake"


def _set_max_concurrent(project_toml: Path, value: int) -> None:
    text = project_toml.read_text(encoding="utf-8")
    assert "max_concurrent" not in text  # guard against a stale template default
    text = text.replace("timeout_seconds = 180", f"timeout_seconds = 180\nmax_concurrent = {value}")
    project_toml.write_text(text, encoding="utf-8")


def test_plan_carries_max_concurrent_from_config(tmp_path, monkeypatch) -> None:
    # max_concurrent travels on the plan (ADR 020) so batch_translate inherits
    # concurrency without its own segment loop; absent config means 1.
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)

    assert prepare_chapter_translation(init.project_toml, chapter_id).max_concurrent == 1

    _set_max_concurrent(init.project_toml, 3)

    assert prepare_chapter_translation(init.project_toml, chapter_id).max_concurrent == 3


def test_run_translation_honours_max_concurrent(tmp_path) -> None:
    # A 3-worker window must beat sequential wall-clock by a wide margin while
    # producing identical counters (the conservative 0.6 factor keeps the unit
    # test robust against CI scheduling jitter; the >= 2.4x exit criterion is
    # measured by the bench harness, not here).
    sequential_dir = tmp_path / "sequential"
    concurrent_dir = tmp_path / "concurrent"
    sequential_dir.mkdir()
    concurrent_dir.mkdir()

    sequential_init = initialize_project(FIXTURE_EPUB, cwd=sequential_dir)
    concurrent_init = initialize_project(FIXTURE_EPUB, cwd=concurrent_dir)
    _set_fake_provider(sequential_init.project_toml)
    _set_fake_provider(concurrent_init.project_toml)
    _set_max_concurrent(concurrent_init.project_toml, 3)

    latency_seconds = 0.2
    results = []
    elapsed = []
    for init, cwd in (
        (sequential_init, sequential_dir),
        (concurrent_init, concurrent_dir),
    ):
        chapter_id = _first_chapter_id(init.database_path)
        plan = prepare_chapter_translation(init.project_toml, chapter_id, cwd=cwd)
        plan = replace(plan, provider=FakeProvider(latency_seconds=latency_seconds))
        start = time.perf_counter()
        results.append(run_translation(plan))
        elapsed.append(time.perf_counter() - start)

    sequential_result, concurrent_result = results
    sequential_elapsed, concurrent_elapsed = elapsed

    assert concurrent_elapsed < sequential_elapsed * 0.6
    assert concurrent_result.translated == sequential_result.translated
    assert concurrent_result.reused_from_memory == sequential_result.reused_from_memory
    assert concurrent_result.failed == sequential_result.failed
    assert sequential_result.failed == 0
    assert concurrent_result.cancelled is False
    # Counting alone is not enough: the concurrent path must leave the same
    # database state, with no duplicate attempt rows from two workers racing.
    for init, result in (
        (sequential_init, sequential_result),
        (concurrent_init, concurrent_result),
    ):
        assert _count_translations(init.database_path) == result.translated
        chapter_id = _first_chapter_id(init.database_path)
        for segment_id in _chapter_segment_ids(init.database_path, chapter_id):
            assert _status(init.database_path, segment_id) == "translated"


def test_run_translation_skips_missing_segments_under_concurrency(tmp_path, monkeypatch) -> None:
    # A target id with no segment row is skipped: no counter moves and no
    # progress callback fires — same as the sequential path.
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    chapter_id = _first_chapter_id(init.database_path)
    real_ids = _chapter_segment_ids(init.database_path, chapter_id)

    plan = prepare_chapter_translation(init.project_toml, chapter_id)
    plan = replace(
        plan,
        max_concurrent=3,
        target_segment_ids=(*plan.target_segment_ids, "ghost-segment-id"),
    )
    seen: list[str] = []

    def _record(index, total, segment, translated, input_tokens, output_tokens) -> None:
        seen.append(segment.id)

    result = run_translation(plan, progress_callback=_record)

    assert result.selected == len(real_ids) + 1
    assert result.translated == len(real_ids)
    assert result.failed == 0
    assert sorted(seen) == sorted(real_ids)
