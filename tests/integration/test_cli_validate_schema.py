"""Tests for Phase A10: weaver validate --schema."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from weaver.cli.main import app


def test_validate_schema_prints_json_shape_without_project() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["validate", "--schema"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "fields" in payload
    assert "check_names" in payload
    assert payload["fields"]["findings"][0]["severity"] == "info | warning | critical"
    assert "untranslated_japanese" in payload["check_names"]
    assert payload["current_version"] == 1


def test_validate_without_project_or_schema_exits_with_clear_error() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["validate"])

    assert result.exit_code == 1, result.output
    assert "requires a project file" in result.output
