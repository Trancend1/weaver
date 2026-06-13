"""Phase 3 CLI healthcheck flag integration tests."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_inspect_healthcheck_flag_reports_fake_provider_as_healthy(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    init_result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init_result.exit_code == 0, init_result.output

    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    _rewrite_provider_to_fake(project_toml)

    healthcheck_result = runner.invoke(app, ["inspect", str(project_toml), "--healthcheck"])

    assert healthcheck_result.exit_code == 0, healthcheck_result.output
    assert "Healthcheck" in healthcheck_result.output
    assert "healthy" in healthcheck_result.output


def test_inspect_without_healthcheck_flag_omits_healthcheck_row(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    init_result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init_result.exit_code == 0, init_result.output

    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    inspect_result = runner.invoke(app, ["inspect", str(project_toml)])

    assert inspect_result.exit_code == 0, inspect_result.output
    assert "Healthcheck" not in inspect_result.output


def _rewrite_provider_to_fake(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = ""', 'type = "fake"')
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = ""', 'model = "fake-1"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    project_toml.write_text(text, encoding="utf-8")
