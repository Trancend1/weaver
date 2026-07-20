"""Tests for `build_context()` and `translate_one_segment()`."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from weaver.core.segment import compute_source_hash
from weaver.errors import ConfigError, ProviderResponseError, ProviderUnavailable
from weaver.providers.base import LLMProvider, ProviderStatus
from weaver.providers.fake import FakeProvider
from weaver.providers.types import Completion, GlossaryTerm, TranslationResponse
from weaver.services.translation import (
    MAX_CONTEXT_SEGMENTS,
    MAX_CONTEXT_TOKENS,
    MAX_GLOSSARY_TERMS_PER_SEGMENT,
    build_context,
    estimate_tokens,
    preflight_provider_chain,
    resolve_max_concurrent,
    translate_one_segment,
)
from weaver.storage.db import initialize_database
from weaver.storage.projects import ProjectRecord
from weaver.storage.segments import SegmentRecord


def test_build_context_filters_glossary_to_matching_terms() -> None:
    glossary = [
        GlossaryTerm(source="護衛", target="bodyguard"),
        GlossaryTerm(source="魔王", target="Demon King"),
    ]

    ctx = build_context(
        normalized_source_text="護衛が来た。",
        glossary_terms=glossary,
        previous_segments=[],
    )

    assert [term.source for term in ctx.glossary_terms] == ["護衛"]


def test_build_context_returns_empty_glossary_when_no_matches() -> None:
    glossary = [GlossaryTerm(source="護衛", target="bodyguard")]

    ctx = build_context(
        normalized_source_text="関係のない文章。", glossary_terms=glossary, previous_segments=[]
    )

    assert ctx.glossary_terms == ()


def test_build_context_caps_glossary_at_twenty_terms() -> None:
    text = "".join(f"term{i}" for i in range(30))
    glossary = [GlossaryTerm(source=f"term{i}", target=f"t{i}") for i in range(30)]

    ctx = build_context(normalized_source_text=text, glossary_terms=glossary, previous_segments=[])

    assert len(ctx.glossary_terms) == MAX_GLOSSARY_TERMS_PER_SEGMENT


def test_build_context_keeps_window_oldest_first_within_cap() -> None:
    window = [(f"src-{i}", f"trg-{i}") for i in range(8)]

    ctx = build_context(
        normalized_source_text="次の段落。", glossary_terms=[], previous_segments=window
    )

    assert len(ctx.previous_segments) == MAX_CONTEXT_SEGMENTS
    assert ctx.previous_segments[0] == ("src-3", "trg-3")
    assert ctx.previous_segments[-1] == ("src-7", "trg-7")


def test_build_context_first_segment_yields_empty_window() -> None:
    ctx = build_context(
        normalized_source_text="始まり。",
        glossary_terms=[],
        previous_segments=[],
    )

    assert ctx.previous_segments == ()


def test_build_context_case_insensitive_match_by_default() -> None:
    glossary = [GlossaryTerm(source="Kai", target="カイ")]

    ctx = build_context(
        normalized_source_text="kai walked away.", glossary_terms=glossary, previous_segments=[]
    )

    assert ctx.glossary_terms == tuple(glossary)


def test_build_context_case_sensitive_term_requires_exact_case() -> None:
    glossary = [GlossaryTerm(source="Kai", target="カイ", case_sensitive=True)]

    assert (
        build_context(
            normalized_source_text="kai walked away.",
            glossary_terms=glossary,
            previous_segments=[],
        ).glossary_terms
        == ()
    )
    assert build_context(
        normalized_source_text="Kai walked away.",
        glossary_terms=glossary,
        previous_segments=[],
    ).glossary_terms == tuple(glossary)


def test_build_context_rejects_unknown_honorific_policy() -> None:
    with pytest.raises(ValueError):
        build_context(
            normalized_source_text="テスト。",
            glossary_terms=[],
            previous_segments=[],
            honorific_policy="rude",
        )


def test_estimate_tokens_counts_cjk_near_one_token_per_char() -> None:
    # Audit N7: the flat chars//4 estimate undercounted Japanese ~3x.
    assert estimate_tokens("あ" * 100) == 100
    assert estimate_tokens("漢" * 100) == 100
    assert estimate_tokens("ｶ" * 100) == 100  # half-width katakana (FF00–FFEF)


def test_estimate_tokens_keeps_quarter_ratio_for_latin_text() -> None:
    assert estimate_tokens("a" * 100) == 25
    assert estimate_tokens("") == 0


def test_estimate_tokens_mixed_text_sums_both_classes() -> None:
    # 8 CJK chars (≈ 8 tokens) + 8 Latin/ASCII chars (≈ 2 tokens).
    assert estimate_tokens("吾輩は猫である。x" + "abcdefg") == 10


def test_window_budget_trims_japanese_windows_by_real_cost() -> None:
    # 5 pairs of (300 JP chars ≈ 300 tokens, 200 EN chars ≈ 50 tokens) is
    # ~1750 honest tokens; the 1000-token budget keeps only the 2 most recent
    # pairs. The old flat estimator priced this window at 625 "tokens" and
    # would have kept all 5.
    window = [("あ" * 300, "a" * 200) for _ in range(5)]

    ctx = build_context(
        normalized_source_text="次。",
        glossary_terms=[],
        previous_segments=window,
    )

    assert len(ctx.previous_segments) == 2
    kept_cost = sum(
        estimate_tokens(source) + estimate_tokens(translation)
        for source, translation in ctx.previous_segments
    )
    assert kept_cost <= MAX_CONTEXT_TOKENS


def test_build_context_drops_window_segments_when_over_token_budget() -> None:
    long_source = "あ" * 2000
    long_translation = "a" * 2000
    window = [(long_source, long_translation) for _ in range(5)]

    ctx = build_context(
        normalized_source_text="次。",
        glossary_terms=[],
        previous_segments=window,
    )

    assert len(ctx.previous_segments) < MAX_CONTEXT_SEGMENTS


# --- translate_one_segment fallback tests ---------------------------------


def _db_with_segment(path: Path) -> tuple[sqlite3.Connection, SegmentRecord, ProjectRecord]:
    """Create a minimal DB with a single pending segment. Returns (conn, seg, project)."""
    conn = initialize_database(path)
    conn.execute(
        "INSERT INTO projects "
        "(name, source_path, source_lang, target_lang, created_at, schema_version) "
        "VALUES (?, ?, ?, ?, datetime('now'), 12)",
        ("test", "/f.epub", "ja", "en"),
    )
    (project_id,) = conn.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    conn.execute(
        "INSERT INTO volumes "
        "(project_id, title, source_path, source_format, volume_order, created_at) "
        "VALUES (?, ?, ?, 'epub', 0, datetime('now'))",
        (project_id, "v1", "/f.epub"),
    )
    (volume_id,) = conn.execute("SELECT id FROM volumes ORDER BY id LIMIT 1").fetchone()
    conn.execute(
        "INSERT INTO chapters "
        "(id, project_id, volume_id, title, spine_order) VALUES (?, ?, ?, ?, 0)",
        ("ch1", project_id, volume_id, "Ch1"),
    )
    seg_id = "seg1"
    src_hash = compute_source_hash("hello")
    conn.execute(
        "INSERT INTO segments "
        "(id, chapter_id, block_order, kind, source_text, source_hash, status) "
        "VALUES (?, ?, 0, 'text', ?, ?, 'pending')",
        (seg_id, "ch1", "hello", src_hash),
    )
    conn.commit()
    seg = SegmentRecord(
        id=seg_id,
        chapter_id="ch1",
        block_order=0,
        kind="text",
        source_text="hello",
        source_hash=src_hash,
        status="pending",
    )
    proj = ProjectRecord(
        id=project_id,
        name="test",
        source_path="/f.epub",
        source_lang="ja",
        target_lang="en",
        schema_version=12,
    )
    return conn, seg, proj


def test_fallback_rescues_segment_when_primary_fails(tmp_path: Path) -> None:
    conn, seg, proj = _db_with_segment(tmp_path / "test.db")
    primary = FakeProvider(fail_rate=1.0, seed=1)
    fallback = FakeProvider(fail_rate=0.0, seed=2)
    cold: dict[str, float] = {}

    outcome = translate_one_segment(
        connection=conn,
        segment=seg,
        source_text="hello",
        normalized_source_text="hello",
        project=proj,
        glossary_terms=(),
        honorific_policy="preserve",
        provider=primary,
        provider_model="failer",
        fallbacks=[(fallback, "saver")],
        cold=cold,
        enforce_repair=False,
    )

    assert outcome.translated, "fallback should have rescued the segment"
    assert not outcome.reused_from_memory, "should not be a TM reuse"
    row = conn.execute(
        "SELECT status, provider, model FROM segments s "
        "JOIN translations t ON t.segment_id = s.id "
        "WHERE s.id = ? ORDER BY t.attempt DESC LIMIT 1",
        (seg.id,),
    ).fetchone()
    assert row is not None
    assert row["status"] == "translated"
    assert row["provider"] == "fake"
    assert row["model"] == "saver"
    conn.close()


def test_fallback_cold_mark_prevents_reuse_within_window(tmp_path: Path) -> None:
    conn, seg, proj = _db_with_segment(tmp_path / "test.db")
    primary = FakeProvider(fail_rate=1.0, seed=1)
    fallback = FakeProvider(fail_rate=0.0, seed=2)
    cold: dict[str, float] = {}

    outcome = translate_one_segment(
        connection=conn,
        segment=seg,
        source_text="hello",
        normalized_source_text="hello",
        project=proj,
        glossary_terms=(),
        honorific_policy="preserve",
        provider=primary,
        provider_model="failer",
        fallbacks=[(fallback, "saver")],
        cold=cold,
        enforce_repair=False,
    )

    assert outcome.translated
    assert cold.get("fake", 0.0) > 0.0, "fallback should be cold-marked"
    conn.close()


def test_all_candidates_fail_marks_segment_failed(tmp_path: Path) -> None:
    conn, seg, proj = _db_with_segment(tmp_path / "test.db")
    primary = FakeProvider(fail_rate=1.0, seed=1)
    fallback = FakeProvider(fail_rate=1.0, seed=2)

    outcome = translate_one_segment(
        connection=conn,
        segment=seg,
        source_text="hello",
        normalized_source_text="hello",
        project=proj,
        glossary_terms=(),
        honorific_policy="preserve",
        provider=primary,
        provider_model="failer",
        fallbacks=[(fallback, "also-failer")],
        enforce_repair=False,
    )

    assert not outcome.translated
    assert not outcome.reused_from_memory
    status = conn.execute("SELECT status FROM segments WHERE id = ?", (seg.id,)).fetchone()[
        "status"
    ]
    assert status == "failed"
    conn.close()


def test_tm_short_circuit_stays_ahead_of_fallback(tmp_path: Path) -> None:
    conn, seg, proj = _db_with_segment(tmp_path / "test.db")
    conn.execute(
        "INSERT INTO translation_memory "
        "(project_id, source_text, source_hash, target_text, "
        " provider, model, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'tm', 'tm', datetime('now'), datetime('now'))",
        (proj.id, "hello", seg.source_hash, "TM CACHED"),
    )
    conn.commit()

    primary = FakeProvider(fail_rate=1.0, seed=1)
    fallback = FakeProvider(fail_rate=0.0, seed=2)

    outcome = translate_one_segment(
        connection=conn,
        segment=seg,
        source_text="hello",
        normalized_source_text="hello",
        project=proj,
        glossary_terms=(),
        honorific_policy="preserve",
        provider=primary,
        provider_model="failer",
        fallbacks=[(fallback, "saver")],
        enforce_repair=False,
        cold={},
    )

    assert outcome.translated, "TM hit should return translated"
    assert outcome.reused_from_memory, "TM reuse — no provider call"
    assert outcome.input_tokens is None, "no input tokens when reused from TM"
    assert outcome.output_tokens is None, "no output tokens when reused from TM"
    row = conn.execute(
        "SELECT provider, model FROM translations "
        "WHERE segment_id = ? ORDER BY attempt DESC LIMIT 1",
        (seg.id,),
    ).fetchone()
    assert row["provider"] == "memory"
    conn.close()


def test_provider_call_runs_outside_write_transaction(tmp_path: Path) -> None:
    # The provider network call can take minutes (timeout x chain x repair).
    # Holding the WAL write lock across it starves every other writer into
    # "database is locked" (v0.7.2 audit finding H3) — so no transaction may
    # be open while the provider runs.
    conn, seg, proj = _db_with_segment(tmp_path / "test.db")
    in_txn_during_call: list[bool] = []

    class TxnProbeProvider(FakeProvider):
        def translate(self, request):  # noqa: ANN001, ANN201 — test double
            in_txn_during_call.append(conn.in_transaction)
            return super().translate(request)

    outcome = translate_one_segment(
        connection=conn,
        segment=seg,
        source_text="hello",
        normalized_source_text="hello",
        project=proj,
        glossary_terms=(),
        honorific_policy="preserve",
        provider=TxnProbeProvider(),
        provider_model="m",
        enforce_repair=False,
    )

    assert outcome.translated and not outcome.reused_from_memory
    assert in_txn_during_call == [False], "provider ran while holding the write lock"
    status = conn.execute("SELECT status FROM segments WHERE id = ?", (seg.id,)).fetchone()[
        "status"
    ]
    assert status == "translated"
    conn.close()


def test_unexpected_provider_exception_restores_prior_status(tmp_path: Path) -> None:
    # A non-ProviderError (e.g. ParserError) escapes the fallback loop. The
    # segment must not stay stranded ``in_progress``: its pre-run status is
    # restored before the exception propagates.
    conn, seg, proj = _db_with_segment(tmp_path / "test.db")

    class ExplodingProvider(FakeProvider):
        def translate(self, request):  # noqa: ANN001, ANN201 — test double
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        translate_one_segment(
            connection=conn,
            segment=seg,
            source_text="hello",
            normalized_source_text="hello",
            project=proj,
            glossary_terms=(),
            honorific_policy="preserve",
            provider=ExplodingProvider(),
            provider_model="m",
            enforce_repair=False,
        )

    status = conn.execute("SELECT status FROM segments WHERE id = ?", (seg.id,)).fetchone()[
        "status"
    ]
    assert status == "pending", "segment must return to its pre-run status"
    conn.close()


# --- enforcement provenance tests (v0.7.3 M3, audit A4/A5) ------------------


class _UsageProvider(LLMProvider):
    """Reports token usage; primary omits the glossary target, repair supplies it."""

    name = "stub"

    def __init__(
        self,
        *,
        repair_text: str = '{"translation": "A line containing Bonjour."}',
        fail_repair: bool = False,
    ) -> None:
        self.complete_calls = 0
        self._repair_text = repair_text
        self._fail_repair = fail_repair

    def translate(self, request):  # noqa: ANN001, ANN201 — test double
        return TranslationResponse(
            translation="A line without the term.",
            notes=(),
            uncertain_terms=(),
            raw_response="{}",
            input_tokens=100,
            output_tokens=40,
        )

    def complete(self, prompt, *, system=None, max_output_tokens):  # noqa: ANN001, ANN201
        self.complete_calls += 1
        if self._fail_repair:
            raise ProviderResponseError(
                "Synthetic repair failure. "
                "Likely cause: test double configured to fail. "
                "Next command: none."
            )
        return Completion(
            text=self._repair_text,
            input_tokens=55,
            output_tokens=20,
            raw_response=self._repair_text,
        )

    def healthcheck(self) -> ProviderStatus:
        return ProviderStatus(
            healthy=True, provider_name=self.name, model="stub", message=None, latency_ms=0
        )


_BONJOUR_TERM = GlossaryTerm(source="hello", target="Bonjour")


def _provenance_row(conn: sqlite3.Connection, segment_id: str) -> sqlite3.Row:
    return conn.execute(
        "SELECT text, input_tokens, output_tokens, enforcement_violations, "
        "repair_attempted, repair_outcome, repair_input_tokens, repair_output_tokens "
        "FROM translations WHERE segment_id = ? ORDER BY attempt DESC LIMIT 1",
        (segment_id,),
    ).fetchone()


def test_enforce_repair_off_still_runs_detection_and_persists_verdict(tmp_path: Path) -> None:
    # Audit A4a: detection is free and always runs; the flag gates only the
    # token-costing repair re-ask.
    conn, seg, proj = _db_with_segment(tmp_path / "test.db")
    provider = _UsageProvider()

    outcome = translate_one_segment(
        connection=conn,
        segment=seg,
        source_text="hello",
        normalized_source_text="hello",
        project=proj,
        glossary_terms=(_BONJOUR_TERM,),
        honorific_policy="preserve",
        provider=provider,
        provider_model="stub-1",
        enforce_repair=False,
    )

    assert outcome.translated
    assert not outcome.repair_call_made
    assert provider.complete_calls == 0, "enforce_repair=False must issue zero repair calls"
    row = _provenance_row(conn, seg.id)
    violations = json.loads(row["enforcement_violations"])
    assert violations, "the missing glossary target must be persisted as a finding"
    assert row["repair_attempted"] == 0
    assert row["repair_outcome"] is None
    assert row["input_tokens"] == 100
    conn.close()


def test_clean_translation_persists_empty_verdict_not_null(tmp_path: Path) -> None:
    conn, seg, proj = _db_with_segment(tmp_path / "test.db")

    outcome = translate_one_segment(
        connection=conn,
        segment=seg,
        source_text="hello",
        normalized_source_text="hello",
        project=proj,
        glossary_terms=(),
        honorific_policy="preserve",
        provider=FakeProvider(),
        provider_model="fake-1",
        enforce_repair=True,
    )

    assert outcome.translated
    row = _provenance_row(conn, seg.id)
    assert row["enforcement_violations"] == "[]", "evaluated-clean must be distinct from NULL"
    conn.close()


def test_repair_accepted_splits_primary_and_repair_tokens(tmp_path: Path) -> None:
    # Audit A5: the row keeps the primary call's tokens; the repair spend has its
    # own columns; the outcome totals reconcile with the row by construction.
    conn, seg, proj = _db_with_segment(tmp_path / "test.db")
    provider = _UsageProvider()

    outcome = translate_one_segment(
        connection=conn,
        segment=seg,
        source_text="hello",
        normalized_source_text="hello",
        project=proj,
        glossary_terms=(_BONJOUR_TERM,),
        honorific_policy="preserve",
        provider=provider,
        provider_model="stub-1",
        enforce_repair=True,
    )

    assert outcome.translated
    assert outcome.repair_call_made
    assert outcome.input_tokens == 155
    assert outcome.output_tokens == 60
    row = _provenance_row(conn, seg.id)
    assert "Bonjour" in row["text"], "the repaired text must be committed"
    assert row["input_tokens"] == 100
    assert row["output_tokens"] == 40
    assert row["repair_input_tokens"] == 55
    assert row["repair_output_tokens"] == 20
    assert row["repair_attempted"] == 1
    assert row["repair_outcome"] == "accepted"
    assert json.loads(row["enforcement_violations"]) == []
    assert row["input_tokens"] + row["repair_input_tokens"] == outcome.input_tokens
    assert row["output_tokens"] + row["repair_output_tokens"] == outcome.output_tokens
    conn.close()


def test_repair_failure_keeps_primary_and_records_failed_outcome(tmp_path: Path) -> None:
    conn, seg, proj = _db_with_segment(tmp_path / "test.db")
    provider = _UsageProvider(fail_repair=True)

    outcome = translate_one_segment(
        connection=conn,
        segment=seg,
        source_text="hello",
        normalized_source_text="hello",
        project=proj,
        glossary_terms=(_BONJOUR_TERM,),
        honorific_policy="preserve",
        provider=provider,
        provider_model="stub-1",
        enforce_repair=True,
    )

    assert outcome.translated
    assert outcome.repair_call_made
    assert outcome.input_tokens == 100, "a failed repair reports no usage to add"
    row = _provenance_row(conn, seg.id)
    assert row["text"] == "A line without the term."
    assert row["repair_outcome"] == "failed"
    assert row["repair_input_tokens"] is None
    assert json.loads(row["enforcement_violations"]), "residual violation stays visible"
    conn.close()


def test_repair_that_regresses_is_discarded_with_original_verdict(tmp_path: Path) -> None:
    conn, seg, proj = _db_with_segment(tmp_path / "test.db")
    # The "repair" still misses the target AND introduces untranslated Japanese:
    # strictly worse, so it must be discarded.
    provider = _UsageProvider(repair_text='{"translation": "まだ日本語のままの行です。"}')

    outcome = translate_one_segment(
        connection=conn,
        segment=seg,
        source_text="hello",
        normalized_source_text="hello",
        project=proj,
        glossary_terms=(_BONJOUR_TERM,),
        honorific_policy="preserve",
        provider=provider,
        provider_model="stub-1",
        enforce_repair=True,
    )

    assert outcome.translated
    row = _provenance_row(conn, seg.id)
    assert row["text"] == "A line without the term.", "regressed repair must be discarded"
    assert row["repair_outcome"] == "discarded"
    # The repair call was spent regardless; its cost stays visible.
    assert row["repair_input_tokens"] == 55
    assert outcome.input_tokens == 155
    violations = json.loads(row["enforcement_violations"])
    assert len(violations) == 1, "verdict describes the committed (original) text"
    conn.close()


# --- preflight_provider_chain tests (audit A1) ------------------------------


class _HealthStub(LLMProvider):
    """Provider stub whose healthcheck outcome is fixed at construction."""

    def __init__(self, name: str, *, healthy: bool) -> None:
        self.name = name
        self._healthy = healthy

    def translate(self, request):  # pragma: no cover - never called at preflight
        raise NotImplementedError

    def complete(self, prompt, *, system=None, max_output_tokens):  # pragma: no cover
        raise NotImplementedError

    def healthcheck(self) -> ProviderStatus:
        return ProviderStatus(
            healthy=self._healthy,
            provider_name=self.name,
            model="m",
            message=None if self._healthy else "connection refused",
            latency_ms=0,
        )


def test_preflight_healthy_primary_returns_no_warning() -> None:
    warning = preflight_provider_chain(_HealthStub("primary", healthy=True))
    assert warning is None


def test_preflight_dead_primary_with_healthy_fallback_warns_not_aborts() -> None:
    primary = _HealthStub("primary", healthy=False)
    fallback = _HealthStub("backup", healthy=True)

    warning = preflight_provider_chain(primary, [(fallback, "m2")])

    assert warning is not None
    assert "primary" in warning
    assert "backup" in warning


def test_preflight_dead_primary_without_fallback_aborts_unchanged() -> None:
    with pytest.raises(ProviderUnavailable) as exc_info:
        preflight_provider_chain(_HealthStub("primary", healthy=False))

    message = str(exc_info.value)
    assert "Provider primary is unavailable: connection refused." in message
    assert "weaver inspect --healthcheck" in message


def test_preflight_dead_primary_and_dead_fallback_aborts() -> None:
    primary = _HealthStub("primary", healthy=False)
    fallback = _HealthStub("backup", healthy=False)

    with pytest.raises(ProviderUnavailable) as exc_info:
        preflight_provider_chain(primary, [(fallback, "m2")])

    assert "no configured fallback passed its healthcheck" in str(exc_info.value)


def test_absent_max_concurrent_defaults_to_one() -> None:
    assert resolve_max_concurrent({}) == 1


def test_valid_values_accepted() -> None:
    for value in (1, 2, 3, 4):
        assert resolve_max_concurrent({"max_concurrent": value}) == value


@pytest.mark.parametrize("value", [0, 5, -1, 100])
def test_out_of_range_rejected(value: int) -> None:
    with pytest.raises(ConfigError, match="max_concurrent"):
        resolve_max_concurrent({"max_concurrent": value})


@pytest.mark.parametrize("value", ["3", 2.5, True, None])
def test_non_integer_rejected(value: object) -> None:
    with pytest.raises(ConfigError, match="max_concurrent"):
        resolve_max_concurrent({"max_concurrent": value})
