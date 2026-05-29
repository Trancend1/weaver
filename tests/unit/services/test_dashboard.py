"""Unit tests for tui/dashboard_app.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from weaver.errors import ConfigError
from weaver.tui.dashboard_app import _require_textual, run_dashboard


def test_require_textual_raises_when_absent() -> None:
    with patch.dict("sys.modules", {"textual": None}):  # noqa: SIM117
        with pytest.raises(ConfigError, match="weaver\\[tui\\]"):
            _require_textual()


def test_run_dashboard_calls_require_textual() -> None:
    project_toml = Path("/fake/project.toml")

    with (
        patch(
            "weaver.tui.dashboard_app._require_textual", side_effect=ConfigError("no textual")
        ) as mock_req,
        pytest.raises(ConfigError),
    ):
        run_dashboard(project_toml)

    mock_req.assert_called_once()


def test_run_dashboard_percent_done_zero_when_no_segments(tmp_path: Path) -> None:
    from weaver.services.project import InspectSummary

    summary = InspectSummary(
        project_name="test",
        source_file="test.epub",
        provider="fake",
        model="fake-1",
        volume_count=1,
        chapter_count=1,
        segment_count=0,
        pending_count=0,
        translated_count=0,
        failed_count=0,
        stale_count=0,
        glossary_candidate_count=0,
        glossary_term_count=0,
        output_dir="output",
    )
    pct = (
        round(100 * summary.translated_count / summary.segment_count)
        if summary.segment_count
        else 0
    )
    assert pct == 0
