"""Tests for the Phase 4 translation orchestrator."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from weaver.errors import ProviderResponseError
from weaver.providers.base import LLMProvider, ProviderStatus
from weaver.providers.types import TranslationRequest, TranslationResponse
from weaver.services.project import initialize_project
from weaver.services.translation import translate_project
from weaver.storage.db import connect_database, transaction
from weaver.storage.segments import update_segment_status

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def test_translate_project_runs_fixture_end_to_end_with_fake_provider(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)

    summary = translate_project(init.project_toml)

    assert summary.total_segments == 6
    assert summary.translated_segments == 6
    assert summary.failed_segments == 0
    assert summary.pending_segments == 0
    assert _count_status(init.database_path, "translated") == 6
    assert _count_translations(init.database_path) == 6


def test_translate_project_sends_previous_chapter_window_to_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    provider = CapturingProvider()

    translate_project(init.project_toml, provider=provider)

    assert provider.requests[0].context.previous_segments == ()
    assert provider.requests[1].context.previous_segments == (
        (
            provider.requests[0].normalized_source_text,
            f"EN: {provider.requests[0].normalized_source_text}",
        ),
    )


def test_translate_project_resets_interrupted_segment_and_resumes(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    first_segment = _first_segment_id(init.database_path)
    with connect_database(init.database_path) as connection, transaction(connection):
        update_segment_status(connection, segment_id=first_segment, status="in_progress")

    summary = translate_project(init.project_toml)

    assert summary.translated_segments == 6
    assert _count_status(init.database_path, "translated") == 6
    assert _count_status(init.database_path, "in_progress") == 0


def test_translate_project_leaves_failed_segments_until_retry_failed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    first_segment = _first_segment_id(init.database_path)
    with connect_database(init.database_path) as connection, transaction(connection):
        update_segment_status(connection, segment_id=first_segment, status="failed")

    first_summary = translate_project(init.project_toml)
    retry_summary = translate_project(init.project_toml, retry_failed=True)

    assert first_summary.translated_segments == 5
    assert first_summary.failed_segments == 1
    assert retry_summary.translated_segments == 1
    assert _count_status(init.database_path, "translated") == 6
    assert _count_status(init.database_path, "failed") == 0


def test_translate_project_marks_provider_failure_failed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    provider = AlwaysFailProvider()

    summary = translate_project(init.project_toml, provider=provider)

    assert summary.translated_segments == 0
    assert summary.failed_segments == 6
    assert _count_status(init.database_path, "failed") == 6
    assert _count_translations(init.database_path) == 0


def test_translate_project_syncs_source_and_marks_changed_segment_stale(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    first_segment = _first_segment_id(init.database_path)
    with connect_database(init.database_path) as connection, transaction(connection):
        update_segment_status(connection, segment_id=first_segment, status="translated")
        connection.execute(
            "UPDATE segments SET source_hash = ? WHERE id = ?",
            ("outdated-hash", first_segment),
        )

    summary = translate_project(init.project_toml)

    assert summary.stale_segments == 1
    assert _count_status(init.database_path, "stale") == 1


class AlwaysFailProvider(LLMProvider):
    name = "fake"

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        raise ProviderResponseError(
            "Synthetic provider failure. "
            "Likely cause: test provider always fails. "
            "Next command: use FakeProvider for green-path testing."
        )

    def healthcheck(self) -> ProviderStatus:
        return ProviderStatus(
            healthy=True,
            provider_name=self.name,
            model="fake-fail",
            message=None,
            latency_ms=0,
        )


class CapturingProvider(LLMProvider):
    name = "fake"

    def __init__(self) -> None:
        self.requests: list[TranslationRequest] = []

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        self.requests.append(request)
        translation = f"EN: {request.normalized_source_text}"
        return TranslationResponse(
            translation=translation,
            notes=(),
            uncertain_terms=(),
            raw_response='{"translation":"ok","notes":[],"uncertain_terms":[]}',
            input_tokens=10,
            output_tokens=5,
        )

    def healthcheck(self) -> ProviderStatus:
        return ProviderStatus(
            healthy=True,
            provider_name=self.name,
            model="fake-capture",
            message=None,
            latency_ms=0,
        )


def _set_fake_provider(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    text = text.replace('base_url = "http://localhost:11434"', 'pattern = "EN: {source}"')
    project_toml.write_text(text, encoding="utf-8")


def _count_status(db_path: Path, status: str) -> int:
    with sqlite3.connect(db_path) as connection:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM segments WHERE status = ?", (status,)
            ).fetchone()[0]
        )


def _count_translations(db_path: Path) -> int:
    with sqlite3.connect(db_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM translations").fetchone()[0])


def _first_segment_id(db_path: Path) -> str:
    with sqlite3.connect(db_path) as connection:
        return str(
            connection.execute("SELECT id FROM segments ORDER BY block_order LIMIT 1").fetchone()[0]
        )
