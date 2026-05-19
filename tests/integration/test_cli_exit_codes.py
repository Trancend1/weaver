"""CLI exit-code AC-9 tests (PRD_v2.md §10 AC-9)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app
from weaver.providers import fake as fake_module
from weaver.providers.base import ProviderStatus

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def test_weaver_init_on_non_epub_exits_code_four(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    bogus = tmp_path / "not-an-epub.epub"
    bogus.write_bytes(b"this is not an EPUB archive")
    runner = CliRunner()

    result = runner.invoke(app, ["init", str(bogus)])

    assert result.exit_code == 4, result.output


def test_weaver_inspect_on_malformed_toml_exits_code_seven(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    bad_toml = tmp_path / "broken.toml"
    bad_toml.write_text("not = valid = toml", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(app, ["inspect", str(bad_toml)])

    assert result.exit_code == 7, result.output
    assert "expected" in result.output.lower() or "toml" in result.output.lower()


def test_weaver_inspect_missing_required_table_exits_code_seven(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    bad_toml = tmp_path / "missing-table.toml"
    bad_toml.write_text('[project]\nname = "x"\n', encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(app, ["inspect", str(bad_toml)])

    assert result.exit_code == 7, result.output
    assert "missing" in result.output.lower()


def test_weaver_translate_provider_unhealthy_exits_code_three(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    init = runner.invoke(app, ["init", str(FIXTURE_EPUB)])
    assert init.exit_code == 0, init.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    text = project_toml.read_text(encoding="utf-8")
    text = (
        text.replace('type = "deepseek"', 'type = "fake"')
        .replace('model = "deepseek-chat"', 'model = "fake-1"')
        .replace('base_url = "http://localhost:11434"', 'pattern = "EN translation."')
    )
    project_toml.write_text(text, encoding="utf-8")

    def unhealthy(self: fake_module.FakeProvider) -> ProviderStatus:
        return ProviderStatus(
            healthy=False,
            provider_name=self.name,
            model=self._model,
            message="forced unhealthy for test",
            latency_ms=0,
        )

    monkeypatch.setattr(fake_module.FakeProvider, "healthcheck", unhealthy)

    result = runner.invoke(app, ["translate", str(project_toml)])

    assert result.exit_code == 3, result.output
    assert "unavailable" in result.output.lower()
