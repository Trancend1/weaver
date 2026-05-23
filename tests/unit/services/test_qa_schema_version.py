"""Tests for QA schema versioning."""

from __future__ import annotations

import json

from weaver.services.qa import (
    QA_SCHEMA_VERSION,
    ValidationReport,
    format_report_json,
    qa_report_schema,
)


def test_format_report_json_includes_schema_version() -> None:
    report = ValidationReport(
        project_name="test",
        total_segments=0,
        findings=(),
        counts={"info": 0, "warning": 0, "critical": 0},
    )
    payload = json.loads(format_report_json(report))
    assert payload["schema_version"] == QA_SCHEMA_VERSION
    assert payload["schema_version"] == 1


def test_qa_report_schema_includes_version_metadata() -> None:
    schema = qa_report_schema()
    assert schema["current_version"] == QA_SCHEMA_VERSION
    fields = schema["fields"]
    assert isinstance(fields, dict)
    assert fields["schema_version"] == "integer"
