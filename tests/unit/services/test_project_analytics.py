"""Tests for deterministic project analytics (Sprint Q8)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from weaver.services.project import initialize_project
from weaver.services.project_analytics import (
    ProjectAnalytics,
    build_project_analytics,
    build_workspace_rollup,
)
from weaver.services.workspace_index import build_workspace_index

FIXTURE_EPUB = Path(__file__).parents[2] / "fixtures" / "aozora_sample.epub"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _seed_translated_segment(conn: sqlite3.Connection) -> str:
    """Mark one segment translated with a hash-matching attempt; return its id."""
    row = conn.execute("SELECT id, source_hash FROM segments LIMIT 1").fetchone()
    seg_id, source_hash = str(row["id"]), str(row["source_hash"])
    conn.execute("UPDATE segments SET status = 'translated' WHERE id = ?", (seg_id,))
    conn.execute(
        "INSERT INTO translations (segment_id, attempt, text, source_hash, provider, "
        "model, created_at, input_tokens, output_tokens) "
        "VALUES (?, 1, 'Hello', ?, 'fake', 'fake-1', '2025-01-01T00:00:00+00:00', 120, 30)",
        (seg_id, source_hash),
    )
    return seg_id


# ---------- per-project analytics ----------


def test_analytics_reconcile_against_db(tmp_path: Path) -> None:
    result = initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    db_path = tmp_path / ".weaver" / "alpha" / "weaver.db"
    conn = _connect(db_path)
    _seed_translated_segment(conn)
    conn.commit()

    # Direct DB truths
    seg_total = conn.execute("SELECT COUNT(*) AS n FROM segments").fetchone()["n"]
    translated = conn.execute(
        "SELECT COUNT(*) AS n FROM segments WHERE status = 'translated'"
    ).fetchone()["n"]
    conn.close()

    a = build_project_analytics(result.project_toml, cwd=tmp_path)
    assert isinstance(a, ProjectAnalytics)
    assert a.segment_total == seg_total
    assert a.status_counts.get("translated", 0) == translated
    assert a.status_counts.get("pending", 0) == seg_total - translated
    assert a.review_counts.get("not_reviewed", 0) == seg_total


def test_analytics_token_usage_per_provider_model(tmp_path: Path) -> None:
    result = initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    db_path = tmp_path / ".weaver" / "alpha" / "weaver.db"
    conn = _connect(db_path)
    _seed_translated_segment(conn)
    conn.commit()
    conn.close()

    a = build_project_analytics(result.project_toml, cwd=tmp_path)
    assert len(a.token_usage) == 1
    usage = a.token_usage[0]
    assert usage.provider == "fake"
    assert usage.model == "fake-1"
    assert usage.attempts == 1
    assert usage.input_tokens == 120
    assert usage.output_tokens == 30


def test_analytics_export_readiness_uses_publishable_predicate(tmp_path: Path) -> None:
    result = initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    db_path = tmp_path / ".weaver" / "alpha" / "weaver.db"
    conn = _connect(db_path)
    _seed_translated_segment(conn)
    # A translated segment whose attempt hash mismatches is NOT publishable.
    row = conn.execute("SELECT id FROM segments WHERE status = 'pending' LIMIT 1").fetchone()
    stale_id = str(row["id"])
    conn.execute("UPDATE segments SET status = 'translated' WHERE id = ?", (stale_id,))
    conn.execute(
        "INSERT INTO translations (segment_id, attempt, text, source_hash, provider, "
        "model, created_at) VALUES (?, 1, 'Old', 'mismatched-hash', 'fake', 'fake-1', "
        "'2025-01-01T00:00:00+00:00')",
        (stale_id,),
    )
    conn.commit()
    conn.close()

    a = build_project_analytics(result.project_toml, cwd=tmp_path)
    assert a.export_readiness.total == a.segment_total
    assert a.export_readiness.publishable == 1  # only the hash-matching one


def test_analytics_empty_project_zeroes(tmp_path: Path) -> None:
    result = initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    a = build_project_analytics(result.project_toml, cwd=tmp_path)
    assert a.token_usage == []
    assert a.export_history == []
    assert a.recent_jobs == []
    assert a.export_readiness.publishable == 0
    assert a.export_readiness.percent == 0


def test_analytics_does_not_modify_database(tmp_path: Path) -> None:
    result = initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    db_path = tmp_path / ".weaver" / "alpha" / "weaver.db"
    mtime_before = db_path.stat().st_mtime_ns

    build_project_analytics(result.project_toml, cwd=tmp_path)

    assert db_path.stat().st_mtime_ns == mtime_before


# ---------- workspace rollup ----------


def test_rollup_aggregates_across_projects(tmp_path: Path) -> None:
    for name in ("alpha", "beta", "gamma"):
        initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name=name)
    conn = _connect(tmp_path / ".weaver" / "alpha" / "weaver.db")
    _seed_translated_segment(conn)
    conn.commit()
    conn.close()

    index = build_workspace_index(tmp_path)
    rollup = build_workspace_rollup(list(index.entries))

    assert rollup.project_count == 3
    assert rollup.segment_total == sum(e.segment_count for e in index.entries)
    assert rollup.translated_total == 1
    assert rollup.input_tokens == 120
    assert rollup.output_tokens == 30
    assert rollup.review_totals.get("not_reviewed", 0) == rollup.segment_total


def test_rollup_empty_entries() -> None:
    rollup = build_workspace_rollup([])
    assert rollup.project_count == 0
    assert rollup.segment_total == 0
    assert rollup.input_tokens == 0


# ---------- index token extension ----------


def test_index_entry_carries_token_totals(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    conn = _connect(tmp_path / ".weaver" / "alpha" / "weaver.db")
    _seed_translated_segment(conn)
    conn.commit()
    conn.close()

    index = build_workspace_index(tmp_path)
    entry = index.entries[0]
    assert entry.input_tokens == 120
    assert entry.output_tokens == 30
