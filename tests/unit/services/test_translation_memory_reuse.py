"""Translation-memory reuse / lookup-before-AI tests (Sprint 6A).

Proves the engine reuses an exact source match instead of calling the provider,
that reuse is project-scoped, that manual edits become the source of truth, and
that explicit retranslate bypasses the lookup.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from weaver.errors import ProviderResponseError
from weaver.providers.base import LLMProvider, ProviderStatus
from weaver.providers.types import TranslationRequest, TranslationResponse
from weaver.services.manual_edit import apply_manual_translation
from weaver.services.project import initialize_project
from weaver.services.translation import translate_project
from weaver.services.workspace_translate import prepare_chapter_translation, run_translation
from weaver.storage.db import connect_database, transaction

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"
FAKE_OVERRIDE = {"type": "fake", "model": "fake-1"}


class CapturingProvider(LLMProvider):
    """Records every translate() call so a reused segment can be proven to skip it."""

    name = "fake"

    def __init__(self) -> None:
        self.requests: list[TranslationRequest] = []

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        self.requests.append(request)
        return TranslationResponse(
            translation=f"EN: {request.normalized_source_text}",
            notes=(),
            uncertain_terms=(),
            raw_response='{"translation":"ok","notes":[],"uncertain_terms":[]}',
            input_tokens=10,
            output_tokens=5,
        )

    def complete(self, prompt, *, system=None, max_output_tokens):  # pragma: no cover
        raise NotImplementedError

    def healthcheck(self) -> ProviderStatus:
        return ProviderStatus(
            healthy=True, provider_name=self.name, model="fake-capture", message=None, latency_ms=0
        )


class AlwaysFailProvider(LLMProvider):
    name = "fake"

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        raise ProviderResponseError(
            "Synthetic provider failure. Likely cause: test provider. "
            "Next command: use FakeProvider."
        )

    def complete(self, prompt, *, system=None, max_output_tokens):  # pragma: no cover
        raise NotImplementedError

    def healthcheck(self) -> ProviderStatus:
        return ProviderStatus(
            healthy=True, provider_name=self.name, model="fake-fail", message=None, latency_ms=0
        )


def _reset_all_to_pending(db_path: Path) -> None:
    with connect_database(db_path) as connection, transaction(connection):
        connection.execute("UPDATE segments SET status = 'pending'")


def _count_tm(db_path: Path) -> int:
    with sqlite3.connect(db_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM translation_memory").fetchone()[0])


def _memory_attempts(db_path: Path) -> int:
    with sqlite3.connect(db_path) as connection:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM translations WHERE provider = 'memory' AND model = 'memory'"
            ).fetchone()[0]
        )


def _first_chapter_id(db_path: Path) -> str:
    with sqlite3.connect(db_path) as connection:
        return str(
            connection.execute(
                "SELECT chapter_id FROM segments ORDER BY block_order LIMIT 1"
            ).fetchone()[0]
        )


def _first_chapter_segment(db_path: Path) -> tuple[str, str, str]:
    """Return (chapter_id, segment_id, source_hash) for the earliest segment.

    Picks chapter and segment from one row (ordered by spine then block) so the
    segment is guaranteed to belong to the returned chapter.
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT s.chapter_id, s.id, s.source_hash
            FROM segments s
            JOIN chapters c ON c.id = s.chapter_id
            ORDER BY c.spine_order, s.block_order
            LIMIT 1
            """
        ).fetchone()
    return str(row[0]), str(row[1]), str(row[2])


def _tm_provider(db_path: Path, source_hash: str) -> str | None:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT provider FROM translation_memory WHERE source_hash = ?", (source_hash,)
        ).fetchone()
    return None if row is None else str(row[0])


def test_repeat_translation_reuses_memory_and_skips_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    provider = CapturingProvider()

    first = translate_project(init.project_toml, provider=provider)
    calls_after_first = len(provider.requests)

    assert first.translated_segments == 6
    assert first.reused_from_memory == 0
    assert calls_after_first == 6
    assert _count_tm(init.database_path) == 6

    _reset_all_to_pending(init.database_path)
    second = translate_project(init.project_toml, provider=provider)

    # The whole point: the second pass makes zero new provider calls.
    assert len(provider.requests) == calls_after_first
    assert second.translated_segments == 6
    assert second.reused_from_memory == 6
    # Derived miss count (provider successes) is zero on a full reuse pass.
    assert second.translated_segments - second.reused_from_memory == 0


def test_memory_hit_records_memory_provider_attempt(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    provider = CapturingProvider()

    translate_project(init.project_toml, provider=provider)
    assert _memory_attempts(init.database_path) == 0  # first pass is all provider

    _reset_all_to_pending(init.database_path)
    translate_project(init.project_toml, provider=provider)

    # Reuse is recorded as an audit-able attempt tagged provider/model "memory".
    assert _memory_attempts(init.database_path) == 6


def test_provider_failure_does_not_populate_memory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    summary = translate_project(init.project_toml, provider=AlwaysFailProvider())

    assert summary.failed_segments == 6
    assert summary.translated_segments == 0
    assert _count_tm(init.database_path) == 0


def test_memory_not_shared_across_projects(tmp_path, monkeypatch) -> None:
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    dir_b = tmp_path / "b"
    dir_b.mkdir()

    monkeypatch.chdir(dir_a)
    init_a = initialize_project(FIXTURE_EPUB)
    provider_a = CapturingProvider()
    summary_a = translate_project(init_a.project_toml, provider=provider_a)

    monkeypatch.chdir(dir_b)
    init_b = initialize_project(FIXTURE_EPUB)
    provider_b = CapturingProvider()
    summary_b = translate_project(init_b.project_toml, provider=provider_b)

    # Identical source text, different project → no cross-project reuse.
    assert summary_a.reused_from_memory == 0
    assert summary_b.reused_from_memory == 0
    assert len(provider_b.requests) == 6


def test_chapter_skip_existing_reuses_memory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    chapter_id = _first_chapter_id(init.database_path)

    first = run_translation(
        prepare_chapter_translation(init.project_toml, chapter_id, provider_override=FAKE_OVERRIDE)
    )
    assert first.reused_from_memory == 0
    count = first.translated

    _reset_all_to_pending(init.database_path)
    second = run_translation(
        prepare_chapter_translation(init.project_toml, chapter_id, provider_override=FAKE_OVERRIDE)
    )

    assert second.translated == count
    assert second.reused_from_memory == count


def test_retranslate_non_manual_bypasses_memory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    chapter_id = _first_chapter_id(init.database_path)

    first = run_translation(
        prepare_chapter_translation(init.project_toml, chapter_id, provider_override=FAKE_OVERRIDE)
    )

    second = run_translation(
        prepare_chapter_translation(
            init.project_toml,
            chapter_id,
            mode="retranslate_non_manual",
            provider_override=FAKE_OVERRIDE,
        )
    )

    # Explicit retranslate must hit the provider, not silently reuse memory.
    assert second.reused_from_memory == 0
    assert second.translated == first.translated


def test_manual_edit_enters_memory_and_survives_provider_retranslate(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    chapter_id, segment_id, source_hash = _first_chapter_segment(init.database_path)

    apply_manual_translation(init.project_toml, segment_id, "MANUAL TRUTH")

    # Manual edit is written into memory as the source of truth.
    assert _tm_provider(init.database_path, source_hash) == "manual"

    result = run_translation(
        prepare_chapter_translation(
            init.project_toml,
            chapter_id,
            segment_ids=[segment_id],
            mode="force_selected",
            provider_override=FAKE_OVERRIDE,
        )
    )

    # force_selected calls the provider (lookup off) but must not clobber the manual entry.
    assert result.translated == 1
    assert result.reused_from_memory == 0
    assert _tm_provider(init.database_path, source_hash) == "manual"
