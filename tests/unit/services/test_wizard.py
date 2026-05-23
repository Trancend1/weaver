"""Unit tests for services/wizard.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from weaver.errors import ConfigError
from weaver.services.wizard import run_new_wizard


def test_questionary_absent_raises_config_error() -> None:
    with patch.dict("sys.modules", {"questionary": None}):  # noqa: SIM117
        with pytest.raises(ConfigError, match="weaver\\[wizard\\]"):
            run_new_wizard()


def test_wizard_returns_answers_with_correct_fields(tmp_path: Path) -> None:
    fake_epub = tmp_path / "novel.epub"
    fake_epub.touch()

    mock_q = MagicMock()
    mock_q.path.return_value.ask.side_effect = [str(fake_epub), ""]
    mock_q.select.return_value.ask.side_effect = ["fake", "light-novel"]

    with patch.dict("sys.modules", {"questionary": mock_q}):
        answers = run_new_wizard()

    assert answers.epub_path == fake_epub
    assert answers.provider == "fake"
    assert answers.template == "light-novel"
    assert answers.working_dir is None


def test_wizard_template_none_when_none_selected(tmp_path: Path) -> None:
    fake_epub = tmp_path / "book.epub"
    fake_epub.touch()

    mock_q = MagicMock()
    mock_q.path.return_value.ask.side_effect = [str(fake_epub), ""]
    mock_q.select.return_value.ask.side_effect = ["gemini", "none"]

    with patch.dict("sys.modules", {"questionary": mock_q}):
        answers = run_new_wizard()

    assert answers.template is None
