"""Candidate-apply service (Sprint L5 safety boundary).

Explicit user action promotes a ``pending`` or ``approved`` candidate to the
segment's active translation. The candidate text is written as a new
``translations`` row (normal history entry) and the segment status is set to
``translated`` (or ``manual`` if the user edited before applying). The candidate
status becomes ``applied``, and any other pending/approved candidates for the
same segment are marked ``superseded``.

**Invariants:**
- Manual text is never overwritten except when the user explicitly approves+applies.
- Provider errors create a ``failed`` candidate state, not partial mutation.
- Apply always goes through ``record_translation()`` and ``save_translation_memory()``
  — same path as manual saves and AI translations.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

from weaver.core.segment import normalize_japanese_text
from weaver.errors import CandidateNotFoundError, SegmentNotFoundError
from weaver.services.project_paths import resolve_database_path
from weaver.storage.candidates import (
    CandidateRecord,
    get_candidate,
    supersede_candidates_for_segment,
    update_candidate_status,
)
from weaver.storage.db import connect_database, transaction
from weaver.storage.segments import get_segment, update_segment_status
from weaver.storage.translation_memory import save_translation_memory
from weaver.storage.translations import record_translation

APPLIED_PROVIDER_PREFIX = "candidate:"


def apply_candidate(
    project_toml: Path,
    candidate_id: str,
    *,
    cwd: Path | None = None,
    edited_text: str | None = None,
) -> CandidateRecord:
    """Apply a translation candidate to its segment.

    The candidate text is recorded as a new translation attempt (normal history
    entry). The segment status becomes ``translated`` (or ``manual`` if
    ``edited_text`` is provided). The candidate status becomes ``applied``.
    Other pending/approved candidates for the same segment are marked
    ``superseded``.

    Args:
        project_toml: Path to the project's ``project.toml``.
        candidate_id: Candidate id to apply.
        cwd: Working directory for path resolution.
        edited_text: Optional user edit to the candidate text before applying.
            When provided, the segment status becomes ``manual``.

    Returns:
        The updated CandidateRecord with status ``applied``.

    Raises:
        CandidateNotFoundError: If the candidate does not exist.
        SegmentNotFoundError: If the candidate's segment does not exist or
            the source hash has changed since generation.
    """

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        try:
            candidate = get_candidate(connection, candidate_id=candidate_id)
        except LookupError as exc:
            raise CandidateNotFoundError(
                f"Translation candidate '{candidate_id}' was not found. "
                "Likely cause: the candidate id is wrong or was deleted. "
                "Next command: list candidates for the segment to find valid ids."
            ) from exc

        if candidate.status not in ("pending", "approved"):
            raise CandidateNotFoundError(
                f"Candidate '{candidate_id}' has status '{candidate.status}', "
                "cannot apply. Only 'pending' or 'approved' candidates can be applied. "
                "Likely cause: the candidate was already applied, rejected, or superseded."
            )

        segment = get_segment(connection, candidate.segment_id)
        if segment is None:
            raise SegmentNotFoundError(
                f"Segment '{candidate.segment_id}' referenced by candidate '{candidate_id}' "
                "was not found. Likely cause: the segment was deleted. "
                "Next command: verify the chapter still has this segment."
            )

        apply_text = (edited_text or candidate.candidate_text).strip()
        if not apply_text:
            raise ValueError(
                "Cannot apply a candidate with empty text. "
                "Likely cause: the candidate has no candidate_text. "
                "Next command: generate a new candidate for this segment."
            )

        with transaction(connection):
            record_translation(
                connection,
                segment_id=candidate.segment_id,
                text=apply_text,
                source_hash=segment.source_hash,
                provider=f"{APPLIED_PROVIDER_PREFIX}{candidate.provider}",
                model=candidate.model,
            )

            if edited_text is not None:
                update_segment_status(connection, segment_id=candidate.segment_id, status="manual")
            else:
                update_segment_status(
                    connection, segment_id=candidate.segment_id, status="translated"
                )

            save_translation_memory(
                connection,
                project_id=candidate.project_id,
                source_text=normalize_japanese_text(candidate.source_text),
                source_hash=segment.source_hash,
                target_text=apply_text,
                provider=f"{APPLIED_PROVIDER_PREFIX}{candidate.provider}",
                model=candidate.model,
                protect_manual=True,
            )

            supersede_candidates_for_segment(
                connection,
                segment_id=candidate.segment_id,
                exclude_id=candidate_id,
            )

            updated = update_candidate_status(
                connection,
                candidate_id=candidate_id,
                status="applied",
            )

    return updated


def approve_candidate(
    project_toml: Path,
    candidate_id: str,
    *,
    cwd: Path | None = None,
) -> CandidateRecord:
    """Approve a candidate without immediately applying it.

    The candidate status becomes ``approved``. The user can later apply it
    explicitly. No mutation of the active translation.

    Args:
        project_toml: Path to the project's ``project.toml``.
        candidate_id: Candidate id to approve.
        cwd: Working directory for path resolution.

    Returns:
        The updated CandidateRecord with status ``approved``.
    """

    return _transition_candidate(project_toml, candidate_id, "approved", cwd=cwd)


def reject_candidate(
    project_toml: Path,
    candidate_id: str,
    *,
    cwd: Path | None = None,
) -> CandidateRecord:
    """Reject a candidate.

    The candidate status becomes ``rejected``. The record is retained for audit
    unless the user intentionally deletes it.

    Args:
        project_toml: Path to the project's ``project.toml``.
        candidate_id: Candidate id to reject.
        cwd: Working directory for path resolution.

    Returns:
        The updated CandidateRecord with status ``rejected``.
    """

    return _transition_candidate(project_toml, candidate_id, "rejected", cwd=cwd)


def _transition_candidate(
    project_toml: Path,
    candidate_id: str,
    new_status: str,
    *,
    cwd: Path | None = None,
) -> CandidateRecord:
    """Generic status transition for a candidate (approve or reject).

    Does not mutate the active translation. Rejected candidates are retained
    for audit.
    """

    db_path = resolve_database_path(project_toml, cwd=cwd)
    with closing(connect_database(db_path)) as connection:
        try:
            get_candidate(connection, candidate_id=candidate_id)
        except LookupError as exc:
            raise CandidateNotFoundError(
                f"Translation candidate '{candidate_id}' was not found. "
                "Likely cause: the candidate id is wrong or was deleted."
            ) from exc
        with transaction(connection):
            updated = update_candidate_status(
                connection,
                candidate_id=candidate_id,
                status=new_status,
            )
    return updated
