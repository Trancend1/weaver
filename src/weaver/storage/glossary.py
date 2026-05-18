"""Glossary repository functions."""

from __future__ import annotations

import sqlite3

from weaver.providers.types import GlossaryTerm


def list_glossary_terms(connection: sqlite3.Connection, *, project_id: int) -> list[GlossaryTerm]:
    """Load approved glossary terms for a project.

    Args:
        connection: Open SQLite connection.
        project_id: Project row id.

    Returns:
        Glossary terms in stable id order. Empty list when no terms are
        approved yet (the glossary review workflow ships in Phase 5).
    """

    rows = connection.execute(
        """
        SELECT source, target, category, notes, case_sensitive
        FROM glossary_terms
        WHERE project_id = ?
        ORDER BY id
        """,
        (project_id,),
    ).fetchall()
    return [
        GlossaryTerm(
            source=str(row["source"]),
            target=str(row["target"]),
            category=_optional_str(row["category"]),
            notes=_optional_str(row["notes"]),
            case_sensitive=bool(row["case_sensitive"]),
        )
        for row in rows
    ]


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
