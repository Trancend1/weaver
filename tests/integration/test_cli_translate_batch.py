"""Tests for Phase A12: weaver translate accepts multiple project_toml paths."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def _init_two_projects(tmp_path: Path) -> tuple[Path, Path]:
    """Create two independent weaver projects from copies of the fixture EPUB."""

    runner = CliRunner()
    epub_a = tmp_path / "alpha.epub"
    epub_b = tmp_path / "beta.epub"
    shutil.copy(FIXTURE_EPUB, epub_a)
    shutil.copy(FIXTURE_EPUB, epub_b)
    runner.invoke(app, ["init", str(epub_a)])
    runner.invoke(app, ["init", str(epub_b)])
    return (
        tmp_path / ".weaver" / "alpha" / "project.toml",
        tmp_path / ".weaver" / "beta" / "project.toml",
    )


def test_translate_processes_two_projects_sequentially(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    proj_a, proj_b = _init_two_projects(tmp_path)

    result = runner.invoke(
        app,
        [
            "translate",
            str(proj_a),
            str(proj_b),
            "--provider",
            "fake",
            "--model",
            "fake-1",
        ],
    )

    assert result.exit_code == 0, result.output
    # Both project banners appear with index/count.
    assert "[1/2]" in result.output
    assert "[2/2]" in result.output
    assert result.output.count("Translated: 6") == 2

    with sqlite3.connect(tmp_path / ".weaver" / "alpha" / "weaver.db") as connection:
        translated_a = connection.execute(
            "SELECT COUNT(*) FROM segments WHERE status = 'translated'"
        ).fetchone()[0]
    with sqlite3.connect(tmp_path / ".weaver" / "beta" / "weaver.db") as connection:
        translated_b = connection.execute(
            "SELECT COUNT(*) FROM segments WHERE status = 'translated'"
        ).fetchone()[0]
    assert translated_a == 6
    assert translated_b == 6


def test_translate_single_project_does_not_show_batch_banner(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    result = runner.invoke(
        app,
        [
            "translate",
            str(project_toml),
            "--provider",
            "fake",
            "--model",
            "fake-1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "[1/1]" not in result.output
    assert "Translated: 6" in result.output
