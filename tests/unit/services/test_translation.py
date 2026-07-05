"""Tests for `build_context()` and `translate_one_segment()`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from weaver.core.segment import compute_source_hash
from weaver.providers.fake import FakeProvider
from weaver.providers.types import GlossaryTerm
from weaver.services.translation import (
    MAX_CONTEXT_SEGMENTS,
    MAX_GLOSSARY_TERMS_PER_SEGMENT,
    build_context,
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

    translated, reused, inp, out = translate_one_segment(
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

    assert translated, "fallback should have rescued the segment"
    assert not reused, "should not be a TM reuse"
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

    translated, _, _, _ = translate_one_segment(
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

    assert translated
    assert cold.get("fake", 0.0) > 0.0, "fallback should be cold-marked"
    conn.close()


def test_all_candidates_fail_marks_segment_failed(tmp_path: Path) -> None:
    conn, seg, proj = _db_with_segment(tmp_path / "test.db")
    primary = FakeProvider(fail_rate=1.0, seed=1)
    fallback = FakeProvider(fail_rate=1.0, seed=2)

    translated, reused, inp, out = translate_one_segment(
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

    assert not translated
    assert not reused
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

    translated, reused, inp, out = translate_one_segment(
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

    assert translated, "TM hit should return translated"
    assert reused, "TM reuse — no provider call"
    assert inp is None, "no input tokens when reused from TM"
    assert out is None, "no output tokens when reused from TM"
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

    translated, reused, _, _ = translate_one_segment(
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

    assert translated and not reused
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
