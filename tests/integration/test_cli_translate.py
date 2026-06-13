"""CLI integration tests for `weaver translate`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_weaver_translate_runs_fake_provider_project(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init_result = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init_result.exit_code == 0, init_result.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    _set_fake_provider(project_toml)

    translate_result = runner.invoke(app, ["translate", str(project_toml)])

    assert translate_result.exit_code == 0, translate_result.output
    assert "Translated: 6" in translate_result.output
    assert "Failed: 0" in translate_result.output
    with sqlite3.connect(tmp_path / ".weaver" / "aozora_sample" / "weaver.db") as connection:
        translated = connection.execute(
            "SELECT COUNT(*) FROM segments WHERE status = 'translated'"
        ).fetchone()[0]
    assert translated == 6


def _set_fake_provider(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = ""', 'type = "fake"')
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = ""', 'model = "fake-1"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    if 'pattern = "EN: {source}"' not in text:
        text = text.replace('model = "fake-1"', 'model = "fake-1"\npattern = "EN: {source}"')
    project_toml.write_text(text, encoding="utf-8")
