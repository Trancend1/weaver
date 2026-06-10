"""SQLite schema migrations.

Migrations are tracked via `PRAGMA user_version`. A fresh database created
by `_apply_schema()` already matches the latest schema; in that case
`apply_migrations()` only stamps `user_version` and returns. Existing
databases at an earlier version run sequenced ALTER statements.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from weaver.errors import DatabaseError


def apply_migrations(connection: sqlite3.Connection, *, target_version: int) -> int:
    """Bring the connected database up to `target_version`.

    Args:
        connection: Open writable SQLite connection.
        target_version: Latest schema version known to this build.

    Returns:
        Final `user_version` after migrations are applied.

    Raises:
        DatabaseError: If the database is at a version newer than this build
            knows how to handle, or if an individual migration step fails.
    """

    current = _user_version(connection)
    if current == target_version:
        return current
    if current > target_version:
        raise DatabaseError(
            f"Weaver database is at schema version {current} but this build "
            f"only supports up to {target_version}. "
            "Likely cause: a newer Weaver wrote this project. "
            "Next command: upgrade `weaver` to the version that created this project."
        )
    if current == 0:
        has_schema = (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='projects'"
            ).fetchone()
            is not None
        )
        if not has_schema:
            raise DatabaseError(
                "Weaver database is not initialized. "
                "Likely cause: database file is missing or was never initialized. "
                "Next command: run `weaver init <input.epub>` to create a project first."
            )
        connection.execute(f"PRAGMA user_version = {target_version}")
        return target_version

    for step in range(current + 1, target_version + 1):
        migrator = _MIGRATIONS.get(step)
        if migrator is None:
            raise DatabaseError(
                f"No migration registered for schema version {step}. "
                "Likely cause: build is missing a migration step. "
                "Next command: report this as a Weaver bug."
            )
        migrator(connection)
        connection.execute(f"PRAGMA user_version = {step}")
    return target_version


def _user_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    if row is None:
        return 0
    return int(row[0])


def _migrate_to_v2(connection: sqlite3.Connection) -> None:
    columns = {
        str(row["name"]) for row in connection.execute("PRAGMA table_info(translations)").fetchall()
    }
    if "input_tokens" not in columns:
        connection.execute("ALTER TABLE translations ADD COLUMN input_tokens INTEGER")
    if "output_tokens" not in columns:
        connection.execute("ALTER TABLE translations ADD COLUMN output_tokens INTEGER")


def _migrate_to_v3(connection: sqlite3.Connection) -> None:
    """Introduce the Volume tier (schema v3).

    Adds the ``volumes`` table and ``chapters.volume_id``, then wraps every
    existing project's chapters in one synthesized default volume so legacy
    (project = one EPUB) databases gain a Novel -> Volume -> Chapter shape
    without losing data.
    """

    tables = {
        str(row["name"])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "volumes" not in tables:
        connection.execute(
            """
            CREATE TABLE volumes (
              id INTEGER PRIMARY KEY,
              project_id INTEGER NOT NULL REFERENCES projects(id),
              title TEXT NOT NULL,
              source_path TEXT NOT NULL,
              source_format TEXT NOT NULL CHECK (source_format IN ('epub', 'txt', 'html')),
              volume_order INTEGER NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_volumes_project ON volumes(project_id, volume_order)"
        )

    if "chapters" not in tables:
        # Partial/legacy database without the chapters table; nothing to backfill.
        return

    chapter_columns = {
        str(row["name"]) for row in connection.execute("PRAGMA table_info(chapters)").fetchall()
    }
    if "volume_id" not in chapter_columns:
        connection.execute("ALTER TABLE chapters ADD COLUMN volume_id INTEGER")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chapters_volume ON chapters(volume_id, spine_order)"
        )

    if "projects" not in tables:
        return

    created_at = datetime.now(UTC).isoformat()
    for project in connection.execute("SELECT id, name, source_path FROM projects").fetchall():
        project_id = int(project["id"])
        has_orphan_chapters = connection.execute(
            "SELECT 1 FROM chapters WHERE project_id = ? AND volume_id IS NULL LIMIT 1",
            (project_id,),
        ).fetchone()
        if has_orphan_chapters is None:
            continue
        cursor = connection.execute(
            """
            INSERT INTO volumes (
              project_id, title, source_path, source_format, volume_order, created_at
            )
            VALUES (?, ?, ?, 'epub', 0, ?)
            """,
            (project_id, str(project["name"]), str(project["source_path"]), created_at),
        )
        if cursor.lastrowid is None:
            raise DatabaseError(
                "Default volume insert did not return a row id during v3 migration. "
                "Likely cause: SQLite did not report lastrowid. "
                "Next command: report this as a Weaver bug."
            )
        connection.execute(
            "UPDATE chapters SET volume_id = ? WHERE project_id = ? AND volume_id IS NULL",
            (int(cursor.lastrowid), project_id),
        )


def _migrate_to_v4(connection: sqlite3.Connection) -> None:
    """Add the project-scoped ``characters`` table (schema v4).

    Character database for translation consistency. Idempotent: only creates the
    table and its index when absent, leaving existing project data untouched.
    """

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS characters (
          id INTEGER PRIMARY KEY,
          project_id INTEGER REFERENCES projects(id),
          jp_name TEXT NOT NULL,
          en_name TEXT NOT NULL,
          gender TEXT,
          role TEXT,
          notes TEXT,
          UNIQUE(project_id, jp_name)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_characters_project ON characters(project_id, jp_name)"
    )


def _migrate_to_v5(connection: sqlite3.Connection) -> None:
    """Add the project-scoped ``translation_memory`` table (schema v5).

    Source->target store for lookup-before-AI reuse. Idempotent: only creates the
    table when absent, leaving existing project data untouched.
    """

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS translation_memory (
          id INTEGER PRIMARY KEY,
          project_id INTEGER REFERENCES projects(id),
          source_text TEXT NOT NULL,
          source_hash TEXT NOT NULL,
          target_text TEXT NOT NULL,
          provider TEXT,
          model TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(project_id, source_hash)
        )
        """
    )


def _migrate_to_v6(connection: sqlite3.Connection) -> None:
    """Persistent job core (schema v6, Sprint I, ADR 010).

    Adds the ``jobs`` and ``job_progress_snapshots`` tables and extends the
    pre-existing ``job_events`` table with a nullable ``job_id`` column.
    Existing ``job_events`` rows backfill to ``job_id = NULL``. The SQLite
    layer remains the **durability** layer for the in-process JobRegistry;
    no external worker, no multi-process queue (CLAUDE.md §3, ADR 010).

    Tolerant of databases that pre-date ``job_events`` (legacy v1/v2 paths
    that the migration tests stand up by hand): the table is created on
    demand so the v6 ALTER never targets a missing table.
    """

    tables = {
        str(row["name"])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "job_events" not in tables:
        connection.execute(
            """
            CREATE TABLE job_events (
              id INTEGER PRIMARY KEY,
              project_id INTEGER REFERENCES projects(id),
              job_id TEXT,
              event TEXT NOT NULL,
              data_json TEXT,
              created_at TEXT NOT NULL
            )
            """
        )
    else:
        job_events_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(job_events)").fetchall()
        }
        if "job_id" not in job_events_columns:
            connection.execute("ALTER TABLE job_events ADD COLUMN job_id TEXT")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id, id)")

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY,
          kind TEXT NOT NULL,
          project_name TEXT NOT NULL,
          scope TEXT,
          scope_id TEXT,
          chapter_id TEXT,
          status TEXT NOT NULL CHECK (status IN (
            'queued',
            'running',
            'done',
            'failed',
            'cancelled',
            'processed',
            'finalizing'
          )),
          mode TEXT,
          target TEXT,
          total_units INTEGER NOT NULL DEFAULT 0,
          done_units INTEGER NOT NULL DEFAULT 0,
          failed_units INTEGER NOT NULL DEFAULT 0,
          skipped_units INTEGER NOT NULL DEFAULT 0,
          current_label TEXT,
          result_json TEXT,
          error_summary TEXT,
          started_at TEXT NOT NULL,
          finished_at TEXT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_project_status ON jobs(project_name, status)"
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_kind_status ON jobs(kind, status)")

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS job_progress_snapshots (
          job_id TEXT REFERENCES jobs(id),
          snapshot_at TEXT NOT NULL,
          done_units INTEGER NOT NULL,
          total_units INTEGER NOT NULL,
          PRIMARY KEY (job_id, snapshot_at)
        )
        """
    )


def _migrate_to_v7(connection: sqlite3.Connection) -> None:
    """EPUB preservation snapshot (schema v7, Sprint J1).

    Six additive tables keyed by ``volume_id`` mirror Phase F's
    :class:`ParsedEpub`. Each list-shaped concept (manifest / spine / nav /
    images / validation) lives in its own ``epub_snapshot_*`` table with a
    ``position`` column so reads come back in original order. Metadata and the
    preservation context are serialised onto the header row as JSON for fidelity
    — the contract changes only when ``parser_version`` bumps, at which point
    the snapshot service marks the row stale.

    No existing data is touched: a fresh table set with no rows. Volume delete
    (Sprint H3) cleans these tables in dependency order via ``services/volume``.
    """

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS epub_snapshots (
          volume_id INTEGER PRIMARY KEY REFERENCES volumes(id),
          source_hash TEXT NOT NULL,
          parser_version INTEGER NOT NULL,
          package_path TEXT NOT NULL,
          opf_path TEXT,
          spine_toc TEXT,
          page_progression_direction TEXT,
          metadata_json TEXT NOT NULL,
          preservation_context_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    for table in (
        "epub_snapshot_manifest",
        "epub_snapshot_spine",
        "epub_snapshot_navigation",
        "epub_snapshot_images",
        "epub_snapshot_validation",
    ):
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
              volume_id INTEGER NOT NULL REFERENCES epub_snapshots(volume_id),
              position INTEGER NOT NULL,
              data_json TEXT NOT NULL,
              PRIMARY KEY (volume_id, position)
            )
            """
        )


def _migrate_to_v8(connection: sqlite3.Connection) -> None:
    """Translation candidates + character page drafts (schema v8, Sprint L).

    Two additive tables for the candidate-review workflow: ``translation_candidates``
    stores AI-generated translation suggestions (never auto-mutates the current
    translation), and ``character_page_drafts`` stores XHTML/text-only character
    page extractions (no OCR, no image processing). Both carry full provenance
    records as JSON. Idempotent: only creates tables and indexes when absent.
    """

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS translation_candidates (
          id TEXT PRIMARY KEY,
          project_id INTEGER NOT NULL REFERENCES projects(id),
          volume_id INTEGER REFERENCES volumes(id),
          chapter_id TEXT NOT NULL REFERENCES chapters(id),
          segment_id TEXT NOT NULL REFERENCES segments(id),
          source_text TEXT NOT NULL,
          candidate_text TEXT NOT NULL,
          provider TEXT NOT NULL,
          model TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN (
            'pending',
            'approved',
            'rejected',
            'applied',
            'superseded',
            'failed'
          )),
          provenance_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_candidates_segment "
        "ON translation_candidates(segment_id, status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_candidates_project "
        "ON translation_candidates(project_id, status)"
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS character_page_drafts (
          id TEXT PRIMARY KEY,
          project_id INTEGER NOT NULL REFERENCES projects(id),
          volume_id INTEGER REFERENCES volumes(id),
          chapter_id TEXT NOT NULL REFERENCES chapters(id),
          segment_id TEXT REFERENCES segments(id),
          source_text TEXT NOT NULL,
          draft_text TEXT NOT NULL,
          heading TEXT,
          page_identifier TEXT,
          status TEXT NOT NULL CHECK (status IN (
            'draft',
            'approved',
            'rejected'
          )),
          provenance_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_char_drafts_project "
        "ON character_page_drafts(project_id, status)"
    )


def _migrate_to_v9(connection: sqlite3.Connection) -> None:
    """Add per-segment review status (schema v9, Sprint P3/WV-003).

    The review axis is independent of translation status so a human can
    review a segment even if the translation is machine-generated. The
    default is ``not_reviewed`` so every existing segment starts clean.
    """

    tables = {
        str(row["name"])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "segments" not in tables:
        return

    columns = {
        str(row["name"]) for row in connection.execute("PRAGMA table_info(segments)").fetchall()
    }
    if "review_status" not in columns:
        connection.execute(
            """
            ALTER TABLE segments
            ADD COLUMN review_status TEXT NOT NULL DEFAULT 'not_reviewed'
            CHECK (review_status IN (
              'not_reviewed',
              'needs_review',
              'needs_revision',
              'approved',
              'rejected'
            ))
            """
        )


_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_to_v2,
    3: _migrate_to_v3,
    4: _migrate_to_v4,
    5: _migrate_to_v5,
    6: _migrate_to_v6,
    7: _migrate_to_v7,
    8: _migrate_to_v8,
    9: _migrate_to_v9,
}
