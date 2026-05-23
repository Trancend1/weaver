"""Integration tests for weaver validate --epub."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from weaver.cli.main import app
from weaver.services.epubcheck import EpubCheckResult

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def _init_project(tmp_path: Path) -> Path:
    runner = CliRunner()
    result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert result.exit_code == 0, result.output
    return tmp_path / ".weaver" / "aozora_sample" / "project.toml"


def _epub_output_path(tmp_path: Path) -> Path:
    return (
        tmp_path / ".weaver" / "aozora_sample" / "output" / "epub" / "aozora_sample.translated.epub"
    )


def test_validate_epub_flag_accepted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path)

    epub_path = _epub_output_path(tmp_path)
    epub_path.parent.mkdir(parents=True, exist_ok=True)
    epub_path.touch()

    fake_result = EpubCheckResult(
        epub_path=epub_path,
        passed=True,
        errors=(),
        warnings=(),
        epubcheck_available=True,
        jar_path=Path("/fake/epubcheck.jar"),
    )
    with patch("weaver.services.epubcheck.run_epubcheck", return_value=fake_result):
        result = runner.invoke(app, ["validate", str(project_toml), "--epub"])

    assert result.exit_code == 0


def test_validate_epub_graceful_when_jar_absent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path)

    epub_path = _epub_output_path(tmp_path)
    epub_path.parent.mkdir(parents=True, exist_ok=True)
    epub_path.touch()

    fake_result = EpubCheckResult(
        epub_path=epub_path,
        passed=True,
        errors=(),
        warnings=(),
        epubcheck_available=False,
        jar_path=None,
    )
    with patch("weaver.services.epubcheck.run_epubcheck", return_value=fake_result):
        result = runner.invoke(app, ["validate", str(project_toml), "--epub"])

    assert result.exit_code == 0
    assert "not available" in result.output


def test_validate_epub_missing_file_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_project(tmp_path)

    result = runner.invoke(app, ["validate", str(project_toml), "--epub"])

    assert result.exit_code != 0
    assert "export" in result.output.lower() or "not found" in result.output.lower()
