"""Tests for the Phase 4 translation orchestrator."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from weaver.core.slop_seed import DEFAULT_BANNED_PHRASES
from weaver.errors import GlossaryConflictError, ProviderResponseError
from weaver.providers.base import LLMProvider, ProviderStatus
from weaver.providers.fake import FakeProvider
from weaver.providers.types import Completion, TranslationRequest, TranslationResponse
from weaver.services.project import initialize_project
from weaver.services.translation import build_translation_profile, translate_project
from weaver.storage.db import connect_database, transaction
from weaver.storage.glossary import approve_glossary_candidate, insert_glossary_candidate
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


def test_translate_project_stops_on_cooperative_cancel(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    provider = CapturingProvider()
    checks = {"n": 0}

    def should_cancel() -> bool:
        # Allow the first segment through; cancel before the second.
        cancel = checks["n"] >= 1
        checks["n"] += 1
        return cancel

    summary = translate_project(init.project_toml, provider=provider, should_cancel=should_cancel)

    assert summary.translated_segments == 1
    assert len(provider.requests) == 1  # worker stopped after one segment
    assert summary.pending_segments >= 1  # remaining segments left consistent


def test_translate_project_injects_approved_glossary_terms_into_matching_prompt(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    provider = CapturingProvider()
    first_segment = _first_segment_text(init.database_path)
    term_source = first_segment[:2]
    with connect_database(init.database_path) as connection, transaction(connection):
        project_id = connection.execute("SELECT id FROM projects LIMIT 1").fetchone()["id"]
        candidate_id = insert_glossary_candidate(
            connection,
            project_id=project_id,
            source=term_source,
            target="Pinned Term",
            category="fallback",
            notes=None,
            status="pending",
            frequency=1,
        )
        approve_glossary_candidate(connection, candidate_id=candidate_id)

    translate_project(init.project_toml, provider=provider)

    first_request_terms = provider.requests[0].context.glossary_terms
    assert [(term.source, term.target) for term in first_request_terms] == [
        (term_source, "Pinned Term")
    ]


def _approve_pinned_term(db_path: Path, *, source: str, target: str) -> None:
    with connect_database(db_path) as connection, transaction(connection):
        project_id = connection.execute("SELECT id FROM projects LIMIT 1").fetchone()["id"]
        candidate_id = insert_glossary_candidate(
            connection,
            project_id=project_id,
            source=source,
            target=target,
            category="fallback",
            notes=None,
            status="pending",
            frequency=1,
        )
        approve_glossary_candidate(connection, candidate_id=candidate_id)


def test_enforcement_repairs_missing_glossary_target(tmp_path, monkeypatch) -> None:
    # ADR 019 E1+E2: the model dropped a glossary target -> one bounded repair re-ask
    # supplies it, and the repaired text is committed in place.
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    term_source = _first_segment_text(init.database_path)[:2]
    _approve_pinned_term(init.database_path, source=term_source, target="PinnedTarget")

    # Primary translation omits the target; the repair completion supplies it.
    provider = FakeProvider(
        pattern="A clean english line without the term.",
        completion='{"translation": "A line containing PinnedTarget exactly.",'
        ' "notes": [], "uncertain_terms": []}',
    )
    translate_project(init.project_toml, provider=provider)

    with sqlite3.connect(init.database_path) as connection:
        repaired = int(
            connection.execute(
                "SELECT COUNT(*) FROM translations WHERE text LIKE '%PinnedTarget%'"
            ).fetchone()[0]
        )
    assert repaired >= 1  # the matching segment was repaired in place


def test_translate_project_keeps_primary_when_repair_unparseable(tmp_path, monkeypatch) -> None:
    # A repair whose output cannot be parsed must keep the good primary translation
    # (never blocked, never substituted).
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    term_source = _first_segment_text(init.database_path)[:2]
    _approve_pinned_term(init.database_path, source=term_source, target="PinnedTarget")

    provider = FakeProvider(pattern="No target here.", completion="not valid json")
    summary = translate_project(init.project_toml, provider=provider)

    assert summary.translated_segments == 6  # all committed despite the repair parse-fail
    with sqlite3.connect(init.database_path) as connection:
        repaired = int(
            connection.execute(
                "SELECT COUNT(*) FROM translations WHERE text LIKE '%PinnedTarget%'"
            ).fetchone()[0]
        )
    assert repaired == 0  # nothing fabricated; original primary kept


class _UncertainProvider(LLMProvider):
    name = "fake"

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        return TranslationResponse(
            translation="A clean english line.",
            notes=(),
            uncertain_terms=("ナルトX", "新世界Y"),
            raw_response="{}",
            input_tokens=1,
            output_tokens=1,
        )

    def complete(self, prompt, *, system=None, max_output_tokens):  # pragma: no cover
        raise NotImplementedError

    def healthcheck(self) -> ProviderStatus:
        return ProviderStatus(
            healthy=True, provider_name=self.name, model="u", message=None, latency_ms=0
        )


def test_enforcement_records_uncertain_terms_as_candidates(tmp_path, monkeypatch) -> None:
    # ADR 019 E4: the model's self-reported uncertain terms become discovered
    # glossary candidates (deduped across segments, no extra model call).
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    translate_project(init.project_toml, provider=_UncertainProvider())

    with sqlite3.connect(init.database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT source, status, frequency, category FROM glossary_candidates "
            "WHERE source IN ('ナルトX', '新世界Y') ORDER BY source"
        ).fetchall()
    assert len(rows) == 2  # one row per term, deduped across the 6 segments
    assert all(r["status"] == "pending" and r["category"] == "discovered" for r in rows)
    assert all(r["frequency"] == 6 for r in rows)  # bumped once per translated segment


def test_uncertain_term_already_approved_is_not_recorded(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _approve_pinned_term(init.database_path, source="ナルトX", target="Naruto")

    translate_project(init.project_toml, provider=_UncertainProvider())

    with sqlite3.connect(init.database_path) as connection:
        discovered = int(
            connection.execute(
                "SELECT COUNT(*) FROM glossary_candidates "
                "WHERE source = 'ナルトX' AND category = 'discovered'"
            ).fetchone()[0]
        )
    assert discovered == 0  # already handled -> never re-proposed as a discovery


class _RepairUsageProvider(LLMProvider):
    """Every primary result carries JP residue (violates E1) and token usage;
    every repair completion is clean and also carries usage."""

    name = "stub"

    def __init__(self) -> None:
        self.complete_calls = 0

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        return TranslationResponse(
            translation="まだ日本語のままの行です。",
            notes=(),
            uncertain_terms=(),
            raw_response="{}",
            input_tokens=10,
            output_tokens=5,
        )

    def complete(self, prompt, *, system=None, max_output_tokens):  # noqa: ANN001, ANN201
        self.complete_calls += 1
        text = '{"translation": "A clean english line."}'
        return Completion(text=text, input_tokens=7, output_tokens=3, raw_response=text)

    def healthcheck(self) -> ProviderStatus:
        return ProviderStatus(
            healthy=True, provider_name=self.name, model="stub", message=None, latency_ms=0
        )


def test_run_summary_reconciles_exactly_with_row_tokens_including_repair(
    tmp_path, monkeypatch
) -> None:
    # Audit A5 acceptance: sum(rows) == summary, repair included, on a fixture
    # where every segment triggers one repair re-ask.
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    provider = _RepairUsageProvider()

    summary = translate_project(init.project_toml, provider=provider)

    assert summary.translated_segments == 6
    assert summary.repair_calls == 6
    assert summary.json_repair_calls == 0
    assert summary.input_tokens == 6 * (10 + 7)
    assert summary.output_tokens == 6 * (5 + 3)
    with sqlite3.connect(init.database_path) as connection:
        row = connection.execute(
            "SELECT "
            "SUM(COALESCE(input_tokens, 0) + COALESCE(repair_input_tokens, 0)) AS total_in, "
            "SUM(COALESCE(output_tokens, 0) + COALESCE(repair_output_tokens, 0)) AS total_out, "
            "SUM(repair_attempted) AS repairs, "
            "COUNT(*) AS rows_n "
            "FROM translations"
        ).fetchone()
    assert row[0] == summary.input_tokens
    assert row[1] == summary.output_tokens
    assert row[2] == summary.repair_calls
    assert row[3] == 6


class _JsonRepairFlaggingProvider(LLMProvider):
    """Simulates a provider that needed its internal JSON-parse repair call."""

    name = "stub"

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        return TranslationResponse(
            translation="A clean english line.",
            notes=(),
            uncertain_terms=(),
            raw_response="{}",
            input_tokens=12,
            output_tokens=6,
            json_repair_used=True,
        )

    def complete(self, prompt, *, system=None, max_output_tokens):  # pragma: no cover
        raise NotImplementedError

    def healthcheck(self) -> ProviderStatus:
        return ProviderStatus(
            healthy=True, provider_name=self.name, model="stub", message=None, latency_ms=0
        )


def test_run_summary_counts_provider_json_repair_calls(tmp_path, monkeypatch) -> None:
    # Audit F6: the provider-internal JSON-parse repair round-trip becomes a
    # visible count on the run summary instead of a silent extra network call.
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)

    summary = translate_project(init.project_toml, provider=_JsonRepairFlaggingProvider())

    assert summary.translated_segments == 6
    assert summary.json_repair_calls == 6
    assert summary.repair_calls == 0


def test_enforce_repair_off_run_persists_findings_with_zero_repair_calls(
    tmp_path, monkeypatch
) -> None:
    # Audit A4a acceptance: enforce_repair=false -> detection still runs and
    # persists findings; zero repair calls are issued.
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    text = init.project_toml.read_text(encoding="utf-8")
    init.project_toml.write_text(
        text.replace("[translation]", "[translation]\nenforce_repair = false", 1),
        encoding="utf-8",
    )
    provider = _RepairUsageProvider()

    summary = translate_project(init.project_toml, provider=provider)

    assert summary.translated_segments == 6
    assert summary.repair_calls == 0
    assert provider.complete_calls == 0
    with sqlite3.connect(init.database_path) as connection:
        rows = connection.execute(
            "SELECT enforcement_violations, repair_attempted FROM translations"
        ).fetchall()
    assert len(rows) == 6
    for violations_json, repair_attempted in rows:
        assert violations_json is not None and violations_json != "[]"
        assert repair_attempted == 0


def test_build_translation_profile_absent_is_none() -> None:
    assert build_translation_profile({"translation": {}}) is None


def test_build_translation_profile_applies_seed_and_style() -> None:
    profile = build_translation_profile(
        {"translation_profile": {"tone": "formal", "tense": "past"}}
    )
    assert profile is not None
    assert profile.tone == "formal"
    assert profile.has_style
    assert profile.banned_phrases == DEFAULT_BANNED_PHRASES  # seed applies once declared


def test_build_translation_profile_empty_banned_disables_seed() -> None:
    profile = build_translation_profile({"translation_profile": {"banned_phrases": []}})
    assert profile is not None
    assert profile.banned_phrases == ()
    assert not profile.has_style


def test_build_translation_profile_custom_banned_replaces_seed() -> None:
    profile = build_translation_profile(
        {"translation_profile": {"banned_phrases": ["very unique slop"]}}
    )
    assert profile is not None
    assert profile.banned_phrases == ("very unique slop",)


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


def test_translate_project_halts_when_approved_glossary_conflicts(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _set_fake_provider(init.project_toml)
    with connect_database(init.database_path) as connection, transaction(connection):
        project_id = connection.execute("SELECT id FROM projects LIMIT 1").fetchone()["id"]
        insert_glossary_candidate(
            connection,
            project_id=project_id,
            source="カイ",
            target="Kai",
            category="katakana",
            notes=None,
            status="approved",
            frequency=2,
        )
        insert_glossary_candidate(
            connection,
            project_id=project_id,
            source="カイ",
            target="Kye",
            category="katakana",
            notes=None,
            status="edited",
            frequency=2,
        )

    with pytest.raises(GlossaryConflictError):
        translate_project(init.project_toml)


class AlwaysFailProvider(LLMProvider):
    name = "fake"

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        raise ProviderResponseError(
            "Synthetic provider failure. "
            "Likely cause: test provider always fails. "
            "Next command: use FakeProvider for green-path testing."
        )

    def complete(self, prompt, *, system=None, max_output_tokens):  # pragma: no cover
        raise NotImplementedError

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

    def complete(self, prompt, *, system=None, max_output_tokens):  # pragma: no cover
        raise NotImplementedError

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
    text = text.replace('type = ""', 'type = "fake"')
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = ""', 'model = "fake-1"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    if 'pattern = "EN: {source}"' not in text:
        text = text.replace('model = "fake-1"', 'model = "fake-1"\npattern = "EN: {source}"')
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


def _count_persisted_raw_responses(db_path: Path) -> int:
    with sqlite3.connect(db_path) as connection:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM translations WHERE raw_response IS NOT NULL"
            ).fetchone()[0]
        )


def _enable_raw_response_logging(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace("raw_response_logging = false", "raw_response_logging = true")
    project_toml.write_text(text, encoding="utf-8")


def test_translate_project_omits_raw_response_when_logging_disabled(tmp_path, monkeypatch) -> None:
    # QF-07 / SD-9: the default [logging].raw_response_logging = false must stop
    # persisting the provider's raw response.
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    provider = CapturingProvider()

    translate_project(init.project_toml, provider=provider)

    assert _count_translations(init.database_path) == 6
    assert _count_persisted_raw_responses(init.database_path) == 0


def test_translate_project_persists_raw_response_when_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    _enable_raw_response_logging(init.project_toml)
    provider = CapturingProvider()

    translate_project(init.project_toml, provider=provider)

    assert _count_persisted_raw_responses(init.database_path) == 6


def test_translate_project_fallback_rescues_primary_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WEAVER_CONNECTIONS_PATH", str(tmp_path / "connections.toml"))
    from weaver.core.connection_registry import Connection, register_connection
    from weaver.providers.fake import FakeProvider

    init = initialize_project(FIXTURE_EPUB)
    register_connection(Connection(name="primary", base_url="https://p/v1", api_key_env="P_KEY"))
    register_connection(Connection(name="backup", base_url="https://b/v1", api_key_env="B_KEY"))

    text = init.project_toml.read_text(encoding="utf-8")
    text += (
        "\n[routing.translate]\n"
        'connection = "primary"\n'
        'model = "pm"\n'
        'fallback = [{ connection = "backup", model = "bm" }]\n'
    )
    init.project_toml.write_text(text, encoding="utf-8")

    calls = {"primary": 0, "backup": 0}

    class _CountingFake(FakeProvider):
        def __init__(self, who: str, fail_rate: float) -> None:
            super().__init__(fail_rate=fail_rate)
            self.name = who

        def translate(self, request: TranslationRequest) -> TranslationResponse:
            calls[self.name] += 1
            return super().translate(request)

    def _fake_build(cfg: dict[str, object]) -> FakeProvider:
        who = str(cfg.get("type") or "x")
        return _CountingFake(who, 1.0 if who == "primary" else 0.0)

    monkeypatch.setattr("weaver.services.translation.build_provider", _fake_build)

    summary = translate_project(init.project_toml)

    # The primary fails every call; the backup rescues every segment.
    assert summary.translated_segments == 6
    assert summary.failed_segments == 0
    # Primary fails segment 1, is cold-marked, then skipped — backup carries the rest.
    assert calls["primary"] == 1
    assert calls["backup"] == 6


def _first_segment_id(db_path: Path) -> str:
    with sqlite3.connect(db_path) as connection:
        return str(
            connection.execute("SELECT id FROM segments ORDER BY block_order LIMIT 1").fetchone()[0]
        )


def _first_segment_text(db_path: Path) -> str:
    with sqlite3.connect(db_path) as connection:
        return str(
            connection.execute(
                "SELECT source_text FROM segments ORDER BY block_order LIMIT 1"
            ).fetchone()[0]
        )


def _segment_ids_in_order(db_path: Path) -> list[str]:
    # Matches `list_segments_for_translation`'s selection order (chapter spine
    # order, then block order within the chapter) rather than raw block_order.
    with sqlite3.connect(db_path) as connection:
        return [
            str(row[0])
            for row in connection.execute(
                """
                SELECT s.id
                FROM segments s
                JOIN chapters c ON c.id = s.chapter_id
                ORDER BY c.spine_order, s.block_order
                """
            ).fetchall()
        ]


def _set_max_concurrent(project_toml: Path, value: int) -> None:
    text = project_toml.read_text(encoding="utf-8")
    assert "max_concurrent" not in text  # guard against a stale template default
    text = text.replace("timeout_seconds = 180", f"timeout_seconds = 180\nmax_concurrent = {value}")
    project_toml.write_text(text, encoding="utf-8")


def test_translate_project_default_is_sequential(tmp_path, monkeypatch) -> None:
    # max_concurrent absent (ADR 020 default 1): one worker connection, and the
    # provider observes segments strictly in source (block_order) order.
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    provider = CapturingProvider()

    summary = translate_project(init.project_toml, provider=provider)

    assert summary.translated_segments == 6
    assert summary.failed_segments == 0
    assert summary.pending_segments == 0
    assert _count_status(init.database_path, "translated") == 6
    assert _count_translations(init.database_path) == 6
    assert [request.segment_id for request in provider.requests] == _segment_ids_in_order(
        init.database_path
    )


def test_translate_project_honours_max_concurrent(tmp_path) -> None:
    # max_concurrent = 3 with a latency-simulating provider must beat sequential
    # wall-clock by a wide margin (ADR 020 / v0.7.3 exit criterion: >= 2.4x on the
    # bench harness; here we assert a conservative >= 1/0.6 speedup to keep the
    # unit test robust against CI scheduling jitter).
    sequential_dir = tmp_path / "sequential"
    concurrent_dir = tmp_path / "concurrent"
    sequential_dir.mkdir()
    concurrent_dir.mkdir()

    sequential_init = initialize_project(FIXTURE_EPUB, cwd=sequential_dir)
    concurrent_init = initialize_project(FIXTURE_EPUB, cwd=concurrent_dir)
    _set_max_concurrent(concurrent_init.project_toml, 3)

    latency_seconds = 0.2

    sequential_start = time.perf_counter()
    sequential_summary = translate_project(
        sequential_init.project_toml,
        cwd=sequential_dir,
        provider=FakeProvider(latency_seconds=latency_seconds),
    )
    sequential_elapsed = time.perf_counter() - sequential_start

    concurrent_start = time.perf_counter()
    concurrent_summary = translate_project(
        concurrent_init.project_toml,
        cwd=concurrent_dir,
        provider=FakeProvider(latency_seconds=latency_seconds),
    )
    concurrent_elapsed = time.perf_counter() - concurrent_start

    assert sequential_summary.translated_segments == 6
    assert concurrent_summary.translated_segments == 6
    assert concurrent_elapsed < sequential_elapsed * 0.6
