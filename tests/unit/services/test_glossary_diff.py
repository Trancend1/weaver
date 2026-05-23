"""Unit tests for services/glossary_diff.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.services.glossary_diff import GlossaryDiffResult, glossary_diff

FIXTURE_EPUB = Path(__file__).parents[3] / "tests" / "fixtures" / "aozora_sample.epub"


def test_glossary_diff_result_is_frozen() -> None:
    result = GlossaryDiffResult(
        chapter_a=1,
        chapter_b=2,
        only_in_a=("term-a",),
        only_in_b=("term-b",),
        in_both=(),
    )
    with pytest.raises(AttributeError):
        result.chapter_a = 99  # type: ignore[misc]


def test_glossary_diff_result_fields() -> None:
    result = GlossaryDiffResult(
        chapter_a=1,
        chapter_b=2,
        only_in_a=("alpha",),
        only_in_b=("beta",),
        in_both=("gamma",),
    )
    assert result.chapter_a == 1
    assert result.chapter_b == 2
    assert "alpha" in result.only_in_a
    assert "beta" in result.only_in_b
    assert "gamma" in result.in_both


def test_glossary_diff_out_of_range_chapter_raises_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from weaver.cli.main import app
    from weaver.errors import ConfigError

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _fixture = Path(__file__).parents[3] / "tests" / "fixtures" / "aozora_sample.epub"
    init_result = runner.invoke(app, ["init", str(_fixture)])
    assert init_result.exit_code == 0, init_result.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    with pytest.raises(ConfigError, match="out of range"):
        glossary_diff(project_toml, 99, 1)


def test_glossary_diff_empty_glossary_returns_all_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from weaver.cli.main import app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _fixture = Path(__file__).parents[3] / "tests" / "fixtures" / "aozora_sample.epub"
    init_result = runner.invoke(app, ["init", str(_fixture)])
    assert init_result.exit_code == 0, init_result.output
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"

    result = glossary_diff(project_toml, 1, 2)

    assert result.only_in_a == ()
    assert result.only_in_b == ()
    assert result.in_both == ()
