"""Project validation service for `weaver validate`."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.config import load_project_config
from weaver.core.segment import normalize_japanese_text
from weaver.errors import ConfigError
from weaver.qa.checks import (
    DEFAULT_MAX_LENGTH_RATIO,
    QAWarning,
    SegmentInput,
    run_all_checks,
)
from weaver.storage.db import connect_readonly_database
from weaver.storage.glossary import list_glossary_terms

DEFAULT_DETECT_EMPTY = True
DEFAULT_DETECT_JAPANESE = True
DEFAULT_DETECT_GLOSSARY_MISMATCH = True
DEFAULT_MINIMUM_LENGTH_RATIO = 0.3
QA_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ValidationReport:
    """Outcome of one `weaver validate` run."""

    project_name: str
    total_segments: int
    findings: tuple[QAWarning, ...]
    counts: dict[str, int]


def validate_project(project_toml: Path, *, cwd: Path | None = None) -> ValidationReport:
    """Run the deterministic QA checks against a project.

    Args:
        project_toml: Weaver project file.
        cwd: Working directory used to resolve relative project paths.

    Returns:
        ValidationReport with ordered findings and severity counts.
    """

    base_dir = cwd or Path.cwd()
    data = load_project_config(project_toml)
    project_config = data["project"]
    qa_config = data.get("qa", {})

    db_path = _resolve_path(str(project_config["database_path"]), base_dir, project_toml.parent)

    detect_empty = bool(qa_config.get("detect_empty_output", DEFAULT_DETECT_EMPTY))
    detect_japanese = bool(qa_config.get("detect_untranslated_japanese", DEFAULT_DETECT_JAPANESE))
    detect_glossary = bool(
        qa_config.get("detect_glossary_mismatch", DEFAULT_DETECT_GLOSSARY_MISMATCH)
    )
    minimum_length_ratio = float(
        qa_config.get("minimum_length_ratio", DEFAULT_MINIMUM_LENGTH_RATIO)
    )
    maximum_length_ratio = float(qa_config.get("maximum_length_ratio", DEFAULT_MAX_LENGTH_RATIO))

    with closing(connect_readonly_database(db_path)) as connection:
        project_id, project_name = _load_single_project(connection)
        glossary_terms = list_glossary_terms(connection, project_id=project_id)
        segments = _load_segments(connection)

    findings: list[QAWarning] = []
    for seg in segments:
        findings.extend(
            run_all_checks(
                seg,
                glossary_terms,
                detect_empty=detect_empty,
                detect_japanese=detect_japanese,
                detect_glossary_mismatch=detect_glossary,
                minimum_length_ratio=minimum_length_ratio,
                maximum_length_ratio=maximum_length_ratio,
            )
        )

    counts: dict[str, int] = {"info": 0, "warning": 0, "critical": 0}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1

    return ValidationReport(
        project_name=project_name,
        total_segments=len(segments),
        findings=tuple(findings),
        counts=counts,
    )


def format_report_json(report: ValidationReport) -> str:
    """Serialize a ValidationReport as stable-shape JSON."""

    payload = {
        "schema_version": QA_SCHEMA_VERSION,
        "project": report.project_name,
        "total_segments": report.total_segments,
        "summary": {
            "info": report.counts.get("info", 0),
            "warning": report.counts.get("warning", 0),
            "critical": report.counts.get("critical", 0),
        },
        "findings": [
            {
                "segment_id": finding.segment_id,
                "check": finding.check_name,
                "severity": finding.severity,
                "message": finding.message,
            }
            for finding in report.findings
        ],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)


def qa_report_schema() -> dict[str, object]:
    """Return a JSON-serializable description of the `weaver validate --json` shape.

    The shape is intentionally minimal — keys, types, and severity enum only.
    Phase A documents the contract; Phase B6 (ADR 0010) will version it via a
    `schema_version` integer included in the payload.
    """

    return {
        "current_version": QA_SCHEMA_VERSION,
        "fields": {
            "schema_version": "integer",
            "project": "string",
            "total_segments": "integer",
            "summary": {
                "info": "integer",
                "warning": "integer",
                "critical": "integer",
            },
            "findings": [
                {
                    "segment_id": "string",
                    "check": "string",
                    "severity": "info | warning | critical",
                    "message": "string",
                }
            ],
        },
        "check_names": [
            "empty_translation",
            "untranslated_japanese",
            "length_ratio",
            "max_length_ratio",
            "punctuation_mismatch",
            "broken_line_breaks",
            "glossary_mismatch",
            "failed_segment",
            "stale_segment",
        ],
        "exit_codes": {
            "0": "no critical findings",
            "1": "at least one critical finding",
        },
    }


def _load_segments(connection: sqlite3.Connection) -> list[SegmentInput]:
    rows = connection.execute(
        """
        WITH latest AS (
          SELECT segment_id, MAX(attempt) AS attempt
          FROM translations
          GROUP BY segment_id
        )
        SELECT
          s.id,
          s.source_text,
          s.source_hash,
          s.status,
          t.text AS translation_text
        FROM segments s
        JOIN chapters c ON c.id = s.chapter_id
        LEFT JOIN latest l ON l.segment_id = s.id
        LEFT JOIN translations t
          ON t.segment_id = l.segment_id
         AND t.attempt = l.attempt
         AND t.source_hash = s.source_hash
        ORDER BY c.spine_order, s.block_order
        """
    ).fetchall()
    inputs: list[SegmentInput] = []
    for row in rows:
        source_text = str(row["source_text"])
        translation_text = None if row["translation_text"] is None else str(row["translation_text"])
        inputs.append(
            SegmentInput(
                segment_id=str(row["id"]),
                source_text=source_text,
                normalized_source_text=normalize_japanese_text(source_text),
                status=str(row["status"]),
                translation_text=translation_text,
            )
        )
    return inputs


def _load_single_project(connection: sqlite3.Connection) -> tuple[int, str]:
    row = connection.execute("SELECT id, name FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ConfigError(
            "Project database has no project row. "
            "Likely cause: database was not initialized by `weaver init`. "
            "Next command: run `weaver init <input.epub>`."
        )
    return int(row["id"]), str(row["name"])


def _resolve_path(path_value: str, cwd: Path, project_toml_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    cwd_path = cwd / path
    if cwd_path.exists():
        return cwd_path
    project_relative = project_toml_dir / path
    if project_relative.exists():
        return project_relative
    return cwd_path
