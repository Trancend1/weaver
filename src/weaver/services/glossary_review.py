"""Interactive glossary review session service.

Owns SQLite connection lifecycle for the `weaver glossary review` and
`weaver glossary conflicts` surfaces so the CLI never touches storage
directly (see CLAUDE.md §4.2 layering rule).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from weaver.core.config import load_project_config
from weaver.errors import ConfigError
from weaver.storage.db import connect_database, connect_readonly_database, transaction
from weaver.storage.glossary import (
    GlossaryCandidateRecord,
    approve_glossary_candidate,
    count_glossary_candidates_by_status,
    count_pending_glossary_candidates,
    edit_glossary_candidate,
    get_pending_glossary_candidate,
    list_glossary_conflicts,
    list_pending_glossary_candidates,
    reject_glossary_candidate,
    restore_glossary_candidate,
)
from weaver.storage.projects import ProjectRecord, get_project

DEFAULT_EXAMPLE_LIMIT = 2


@dataclass(frozen=True)
class GlossaryReviewState:
    """Snapshot of glossary review queue counts."""

    pending: int
    approved: int
    rejected: int


@dataclass(frozen=True)
class PendingPage:
    """One page of pending candidates plus queue counts (web review).

    ``total_pending`` reflects the current filter (matched count when ``find`` is
    set, else the full pending queue) so pagination is correct; ``counts`` always
    carries the unfiltered queue totals for display.
    """

    items: tuple[GlossaryCandidateRecord, ...]
    total_pending: int
    offset: int
    limit: int
    counts: GlossaryReviewState
    find: str | None = None


VALID_REVIEW_ACTIONS = frozenset({"approve", "edit", "reject"})


class GlossaryReviewSession:
    """Stateful glossary review session.

    Each mutating call commits in its own transaction so an interrupted
    session leaves a consistent database. A single-step undo snapshot is
    retained per session; it is cleared once consumed.
    """

    def __init__(self, connection: sqlite3.Connection, project: ProjectRecord) -> None:
        self._connection = connection
        self._project = project
        self._undo_snapshot: GlossaryCandidateRecord | None = None

    @property
    def project_id(self) -> int:
        return self._project.id

    @property
    def project_name(self) -> str:
        return self._project.name

    def status_counts(self) -> GlossaryReviewState:
        counts = count_glossary_candidates_by_status(self._connection, project_id=self._project.id)
        return GlossaryReviewState(
            pending=counts.get("pending", 0),
            approved=counts.get("approved", 0) + counts.get("edited", 0),
            rejected=counts.get("rejected", 0),
        )

    def next_pending(self) -> GlossaryCandidateRecord | None:
        return get_pending_glossary_candidate(self._connection, project_id=self._project.id)

    def find(self, substring: str) -> GlossaryCandidateRecord | None:
        """Return the first pending candidate whose source contains `substring`.

        Search is case-insensitive and ordered by frequency desc, then source,
        then id (same order as `next_pending`). Returns None when no pending
        candidate matches.
        """

        needle = substring.strip()
        if not needle:
            return None
        row = self._connection.execute(
            """
            SELECT id, project_id, source, target, category, notes, status, frequency
            FROM glossary_candidates
            WHERE project_id = ?
              AND status = 'pending'
              AND source LIKE ?
            ORDER BY frequency DESC, source, id
            LIMIT 1
            """,
            (self._project.id, f"%{needle}%"),
        ).fetchone()
        if row is None:
            return None
        return GlossaryCandidateRecord(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            source=str(row["source"]),
            target=None if row["target"] is None else str(row["target"]),
            category=None if row["category"] is None else str(row["category"]),
            notes=None if row["notes"] is None else str(row["notes"]),
            status=str(row["status"]),
            frequency=int(row["frequency"]),
        )

    def examples_for(self, source: str, *, limit: int = DEFAULT_EXAMPLE_LIMIT) -> list[str]:
        rows = self._connection.execute(
            """
            SELECT s.source_text
            FROM segments s
            JOIN chapters c ON c.id = s.chapter_id
            WHERE c.project_id = ?
              AND s.source_text LIKE ?
            ORDER BY c.spine_order, s.block_order
            LIMIT ?
            """,
            (self._project.id, f"%{source}%", limit),
        ).fetchall()
        return [str(row["source_text"]) for row in rows]

    def approve(self, candidate: GlossaryCandidateRecord) -> None:
        with transaction(self._connection):
            approve_glossary_candidate(self._connection, candidate_id=candidate.id)
        self._undo_snapshot = candidate

    def edit(
        self,
        candidate: GlossaryCandidateRecord,
        *,
        target: str,
        notes: str | None,
    ) -> None:
        with transaction(self._connection):
            edit_glossary_candidate(
                self._connection,
                candidate_id=candidate.id,
                target=target,
                notes=notes,
            )
        self._undo_snapshot = candidate

    def reject(self, candidate: GlossaryCandidateRecord) -> None:
        with transaction(self._connection):
            reject_glossary_candidate(self._connection, candidate_id=candidate.id)
        self._undo_snapshot = candidate

    def undo(self) -> bool:
        if self._undo_snapshot is None:
            return False
        with transaction(self._connection):
            restore_glossary_candidate(self._connection, candidate=self._undo_snapshot)
        self._undo_snapshot = None
        return True


@contextmanager
def open_glossary_review_session(project_toml: Path) -> Iterator[GlossaryReviewSession]:
    """Open a writable glossary review session bound to one project.

    The yielded session owns its SQLite connection for the duration of the
    `with` block; the connection is closed on exit.
    """

    db_path = _resolve_database_path(project_toml)
    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        yield GlossaryReviewSession(connection, project)


def list_project_glossary_conflicts(
    project_toml: Path, *, cwd: Path | None = None
) -> list[tuple[str, tuple[str, ...]]]:
    """Return approved glossary target conflicts for a project (read-only)."""

    db_path = _resolve_database_path(project_toml, cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        project = _load_single_project(connection)
        return list_glossary_conflicts(connection, project_id=project.id)


def list_pending(
    project_toml: Path,
    *,
    cwd: Path | None = None,
    offset: int = 0,
    limit: int = 20,
    find: str | None = None,
) -> PendingPage:
    """Return one page of pending candidates plus queue counts (read-only).

    Stateless counterpart to ``GlossaryReviewSession`` for per-request web use.
    When ``find`` is set, only candidates whose source contains it are returned
    (and ``total_pending`` reflects that filtered count). The CLI interactive
    loop is unchanged.
    """

    offset = max(offset, 0)
    limit = max(limit, 1)
    needle = (find or "").strip() or None
    db_path = _resolve_database_path(project_toml, cwd)
    with closing(connect_readonly_database(db_path)) as connection:
        project = _load_single_project(connection)
        items = list_pending_glossary_candidates(
            connection, project_id=project.id, offset=offset, limit=limit, find=needle
        )
        matched = count_pending_glossary_candidates(connection, project_id=project.id, find=needle)
        counts = count_glossary_candidates_by_status(connection, project_id=project.id)
    state = GlossaryReviewState(
        pending=counts.get("pending", 0),
        approved=counts.get("approved", 0) + counts.get("edited", 0),
        rejected=counts.get("rejected", 0),
    )
    return PendingPage(
        items=tuple(items),
        total_pending=matched,
        offset=offset,
        limit=limit,
        counts=state,
        find=needle,
    )


def act_on_candidate(
    project_toml: Path,
    candidate_id: int,
    action: str,
    *,
    cwd: Path | None = None,
    target: str | None = None,
    notes: str | None = None,
) -> None:
    """Apply one review action to a candidate in its own transaction.

    Args:
        project_toml: Weaver project file.
        candidate_id: Candidate row id.
        action: One of ``approve`` | ``edit`` | ``reject``.
        cwd: Working directory used to resolve the database path.
        target: Required for ``edit`` — the translator-provided wording.
        notes: Optional notes for ``edit``.

    Raises:
        ConfigError: When ``action`` is unknown, ``edit`` lacks a target, or the
            candidate id does not exist.
    """

    if action not in VALID_REVIEW_ACTIONS:
        valid = ", ".join(sorted(VALID_REVIEW_ACTIONS))
        raise ConfigError(
            f"Unknown glossary action `{action}`. "
            f"Likely cause: action must be one of: {valid}. "
            "Next command: use approve, edit, or reject."
        )
    if action == "edit" and not (target and target.strip()):
        raise ConfigError(
            "Edit requires a target. "
            "Likely cause: the edit form was submitted with an empty target. "
            "Next command: enter the translated term and resubmit."
        )

    db_path = _resolve_database_path(project_toml, cwd)
    with closing(connect_database(db_path)) as connection:
        try:
            with transaction(connection):
                if action == "approve":
                    approve_glossary_candidate(connection, candidate_id=candidate_id)
                elif action == "edit":
                    edit_glossary_candidate(
                        connection,
                        candidate_id=candidate_id,
                        target=target,  # type: ignore[arg-type]  # guarded above
                        notes=notes,
                    )
                else:
                    reject_glossary_candidate(connection, candidate_id=candidate_id)
        except LookupError as exc:
            raise ConfigError(
                f"Glossary candidate not found: {candidate_id}. "
                "Likely cause: stale page or the candidate was already actioned. "
                "Next command: reload the glossary page."
            ) from exc


def _resolve_database_path(project_toml: Path, cwd: Path | None = None) -> Path:
    data = load_project_config(project_toml)
    path = Path(str(data["project"]["database_path"]))
    if path.is_absolute():
        return path
    base_dir = cwd or Path.cwd()
    cwd_path = base_dir / path
    if cwd_path.exists():
        return cwd_path
    return project_toml.parent / path


def _load_single_project(connection: sqlite3.Connection) -> ProjectRecord:
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ConfigError(
            "Project database has no project row. "
            "Likely cause: database was not initialized by `weaver init`. "
            "Next command: run `weaver init <input.epub>`."
        )
    return get_project(connection, int(row["id"]))
