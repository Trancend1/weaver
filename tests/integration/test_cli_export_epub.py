"""CLI tests for Phase 8 EPUB export."""

from __future__ import annotations

from pathlib import Path

from ebooklib import epub
from typer.testing import CliRunner

from weaver.cli.main import app

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_weaver_export_epub_writes_translated_epub_that_reads_back(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    project_toml = _init_fake_and_translate(runner, tmp_path)

    result = runner.invoke(app, ["export", str(project_toml), "--mode", "epub"])

    assert result.exit_code == 0, result.output
    output_path = (
        tmp_path / ".weaver" / "aozora_sample" / "output" / "epub" / "aozora_sample.translated.epub"
    )
    assert output_path.exists()
    assert "Translated blocks: 6" in result.output
    assert "Fallback blocks: 0" in result.output

    book = epub.read_epub(str(output_path))
    chapter01 = next(item for item in book.get_items() if item.get_name() == "text/chapter01.xhtml")
    body = chapter01.get_content().decode("utf-8")
    assert "EN: " in body


def test_weaver_export_epub_falls_back_to_source_for_pending_segments(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    result = runner.invoke(app, ["export", str(project_toml), "--mode", "epub"])

    assert result.exit_code == 0, result.output
    output_path = (
        tmp_path / ".weaver" / "aozora_sample" / "output" / "epub" / "aozora_sample.translated.epub"
    )
    assert output_path.exists()
    assert "Translated blocks: 0" in result.output
    assert "Fallback blocks: 6" in result.output
    book = epub.read_epub(str(output_path))
    chapter01 = next(item for item in book.get_items() if item.get_name() == "text/chapter01.xhtml")
    body = chapter01.get_content().decode("utf-8")
    assert "吾輩は猫である" in body


def test_weaver_export_epub_rejects_translation_only_flag(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    result = runner.invoke(
        app, ["export", str(project_toml), "--mode", "epub", "--translation-only"]
    )

    assert result.exit_code != 0, result.output
    assert "translation-only" in result.output.lower() or "translation_only" in result.output


def _init_fake_and_translate(runner: CliRunner, tmp_path: Path) -> Path:
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    _set_fake_provider(project_toml)
    translate = runner.invoke(app, ["translate", str(project_toml)])
    assert translate.exit_code == 0, translate.output
    return project_toml


def _set_fake_provider(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    text = text.replace('base_url = "http://localhost:11434"', 'pattern = "EN: {source}"')
    project_toml.write_text(text, encoding="utf-8")
