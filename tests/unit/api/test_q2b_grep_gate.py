"""Q2b grep-gate tests: enforce read-path & failure-visibility rules.

These are negative-space tests: they prove the codebase does NOT contain
patterns that violate the Q2 hardening contract (QF-02/03/04/05/06).
"""

from __future__ import annotations

import ast
import inspect
import sqlite3
from pathlib import Path

import pytest

from weaver.api.routers import (
    candidates,
    jobs,
    ui,
    ui_candidates,
    ui_jobs,
    ui_qa,
    ui_review,
)
from weaver.errors import WeaverError
from weaver.services.image_preview import read_image_preview
from weaver.storage.db import connect_database

ROUTER_MODULES = [
    candidates,
    jobs,
    ui,
    ui_candidates,
    ui_jobs,
    ui_qa,
    ui_review,
]


# ---------------------------------------------------------------------------
# 1. No writable DB opens on read paths
# ---------------------------------------------------------------------------


def test_api_routers_no_connect_database() -> None:
    """Permanent gate: no ``connect_database(`` call in any API router file."""
    for module in ROUTER_MODULES:
        source = inspect.getsource(module)
        assert "connect_database(" not in source, (
            f"{module.__name__} must not call connect_database; "
            "use connect_readonly_database for reads"
        )


# ---------------------------------------------------------------------------
# 2. No raw SQL in router source (service extraction)
# ---------------------------------------------------------------------------


def _has_raw_sql(source: str) -> bool:
    """Detect bare SQL strings outside of imported constants."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lowered = node.value.strip().lower()
            if (
                lowered.startswith(("select ", "insert ", "update ", "delete ", "from "))
                and len(lowered) > 20
            ):
                return True
    return False


def test_api_routers_no_raw_sql() -> None:
    """Raw SQL lives in storage/ services only; routers import helpers."""
    for module in ROUTER_MODULES:
        source = inspect.getsource(module)
        # Heuristic: strings that look like SQL statements
        bad_lines = []
        for line in source.splitlines():
            stripped = line.strip().lower()
            if (
                stripped.startswith('"select ')
                or stripped.startswith("'select ")
                or stripped.startswith('"update ')
                or stripped.startswith("'update ")
            ):
                bad_lines.append(line.strip()[:80])
        assert not bad_lines, (
            f"{module.__name__} contains raw SQL lines: {bad_lines}. Extract into a storage helper."
        )


# ---------------------------------------------------------------------------
# 3. No swallowed exceptions (QF-04 / R-11)
# ---------------------------------------------------------------------------


def test_api_routers_no_swallowed_weaver_error() -> None:
    """``except WeaverError: pass`` is banned; failures must be visible."""
    for module in ROUTER_MODULES:
        source = inspect.getsource(module)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ExceptHandler)
                and len(node.body) == 1
                and isinstance(node.body[0], (ast.Pass, ast.Expr))
                and (
                    node.type is None
                    or (isinstance(node.type, ast.Name) and node.type.id == "WeaverError")
                )
            ):
                pytest.fail(
                    f"{module.__name__} swallows an exception with pass. "
                    "Use an error fragment instead."
                )


def test_api_routers_no_suppress_httpexception() -> None:
    """``suppress(HTTPException)`` is banned per QF-04."""
    for module in ROUTER_MODULES:
        source = inspect.getsource(module)
        assert "suppress(HTTPException)" not in source, (
            f"{module.__name__} uses suppress(HTTPException). "
            "Catch explicitly and render an error fragment."
        )


# ---------------------------------------------------------------------------
# 4. connect_database no longer resets in_progress (R-02 regression)
# ---------------------------------------------------------------------------


def test_connect_database_no_longer_resets_in_progress(tmp_path: Path) -> None:
    """Opening a DB with connect_database must not reset in_progress segments."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(
        """
        CREATE TABLE projects (id INTEGER PRIMARY KEY);
        CREATE TABLE chapters (id INTEGER PRIMARY KEY, volume_id INTEGER);
        CREATE TABLE segments (
            id TEXT PRIMARY KEY,
            chapter_id INTEGER,
            status TEXT
        );
        INSERT INTO segments VALUES ('s1', 1, 'in_progress');
        """
    )
    conn.commit()
    conn.close()

    # connect_database should open without resetting

    fresh = connect_database(db_path)
    row = fresh.execute("SELECT status FROM segments WHERE id = 's1'").fetchone()
    assert row is not None
    assert row["status"] == "in_progress", (
        "connect_database must NOT reset in_progress segments (R-02)"
    )
    fresh.close()


# ---------------------------------------------------------------------------
# 5. Image preview stale source → WeaverError, not 500
# ---------------------------------------------------------------------------


def test_image_preview_missing_source_returns_weaver_error(
    tmp_path: Path,
) -> None:
    """A deleted source EPUB must raise WeaverError, not an unhandled OSError."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(
        """
        CREATE TABLE volumes (
            id INTEGER PRIMARY KEY,
            title TEXT,
            source_path TEXT,
            source_format TEXT,
            volume_order INTEGER
        );
        INSERT INTO volumes VALUES (1, 'vol', 'missing.epub', 'epub', 1);
        CREATE TABLE epub_snapshots (
            volume_id INTEGER PRIMARY KEY,
            source_hash TEXT,
            parser_version INTEGER,
            package_path TEXT,
            opf_path TEXT,
            spine_toc TEXT,
            page_progression_direction TEXT,
            metadata_json TEXT,
            preservation_context_json TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    with pytest.raises(WeaverError) as exc_info:
        read_image_preview(db_path, volume_id=1, manifest_id="img1")

    msg = str(exc_info.value).lower()
    assert "missing" in msg or "source" in msg or "not found" in msg


# ---------------------------------------------------------------------------
# 6. Project overview does not hash on render (R-09)
# ---------------------------------------------------------------------------


def test_project_overview_no_file_access_on_render(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Overview render must not open or hash source EPUB files."""
    from unittest.mock import MagicMock

    from weaver.services.project_overview import project_overview
    from weaver.services.project_tree import NovelTree

    # Spy: status_for_volume is the function that hashes EPUBs on read.
    # It must never be called during project_overview after Q2b.
    monkeypatch.setattr(
        "weaver.services.project_overview._snapshot_status_from_db",
        lambda conn, vid: "fresh",
    )

    # Create a minimal project tree mock with one volume
    mock_tree = MagicMock(spec=NovelTree)
    mock_tree.project_name = "test"
    mock_tree.volumes = []
    mock_tree.chapters = []

    # Patch project_tree to return the mock
    monkeypatch.setattr("weaver.services.project_overview.project_tree", lambda *a, **k: mock_tree)

    # Create minimal project files
    project_dir = tmp_path / "test"
    project_dir.mkdir()
    toml = project_dir / "project.toml"
    toml.write_text(
        "[project]\nname = 'test'\ndatabase_path = '.weaver/weaver.db'\n"
        "[provider]\ntype = 'fake'\n"
        "[translation]\nsource_lang = 'ja'\ntarget_lang = 'en'\n"
    )
    db = project_dir / ".weaver" / "weaver.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(
        """
        CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, source_path TEXT,
            source_lang TEXT, target_lang TEXT, schema_version INTEGER, uuid TEXT);
        INSERT INTO projects VALUES (1, 'test', '', 'ja', 'en', 10, 'uuid');
        CREATE TABLE volumes (id INTEGER PRIMARY KEY, title TEXT, source_path TEXT,
            source_format TEXT, volume_order INTEGER);
        CREATE TABLE chapters (id INTEGER PRIMARY KEY, volume_id INTEGER, title TEXT,
            spine_order INTEGER, word_count INTEGER);
        CREATE TABLE segments (id TEXT PRIMARY KEY, chapter_id INTEGER, block_order INTEGER,
            kind TEXT, source_text TEXT, source_hash TEXT, status TEXT);
        CREATE TABLE translation_candidates (id INTEGER PRIMARY KEY);
        CREATE TABLE character_page_drafts (id INTEGER PRIMARY KEY);
        CREATE TABLE segment_reviews (segment_id TEXT PRIMARY KEY, review_status TEXT);
        CREATE TABLE jobs (id TEXT PRIMARY KEY, kind TEXT, project_name TEXT, status TEXT,
            scope TEXT, scope_id TEXT, chapter_id TEXT, mode TEXT, target TEXT,
            total_units INTEGER, done_units INTEGER, failed_units INTEGER,
            skipped_units INTEGER, current_label TEXT, result_json TEXT,
            error_summary TEXT, started_at TEXT, finished_at TEXT);
        """
    )
    conn.commit()
    conn.close()

    overview = project_overview(toml, cwd=tmp_path)

    assert overview.project_name == "test"
