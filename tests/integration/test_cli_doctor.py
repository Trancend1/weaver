"""CLI integration tests for `weaver doctor`."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_weaver_doctor_no_project_passes_host_checks(monkeypatch) -> None:
    monkeypatch.setenv("EDITOR", "notepad")
    runner = CliRunner()

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "PASS  python" in result.output
    assert "PASS  editor" in result.output


def test_weaver_doctor_missing_editor_exits_with_code_one(monkeypatch) -> None:
    monkeypatch.delenv("EDITOR", raising=False)
    runner = CliRunner()

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1, result.output
    assert "FAIL  editor" in result.output


def test_weaver_doctor_with_project_runs_full_checks(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EDITOR", "notepad")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "stub-key")
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    result = runner.invoke(app, ["doctor", str(project_toml)])

    assert result.exit_code == 0, result.output
    assert "PASS  config" in result.output
    assert "PASS  database" in result.output
    assert "PASS  provider-env" in result.output
