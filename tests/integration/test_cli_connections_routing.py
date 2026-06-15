"""CLI parity for connections + routing (ADR 018 S5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from weaver.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEAVER_CONNECTIONS_PATH", str(tmp_path / "connections.toml"))
    monkeypatch.setenv("WEAVER_SECRETS_PATH", str(tmp_path / "secrets.toml"))
    monkeypatch.setenv("WEAVER_CONNECTION_MODELS_PATH", str(tmp_path / "models.json"))


def test_connections_add_list_rm_never_prints_key(runner: CliRunner) -> None:
    added = runner.invoke(
        app,
        ["connections", "add", "openrouter", "--endpoint", "https://o/v1", "--key", "sk-SECRET"],
    )
    assert added.exit_code == 0, added.output
    assert "Saved connection openrouter" in added.output

    listed = runner.invoke(app, ["connections", "list"])
    assert listed.exit_code == 0, listed.output
    assert "openrouter" in listed.output
    assert "sk-SECRET" not in listed.output  # key value never printed

    removed = runner.invoke(app, ["connections", "rm", "openrouter"])
    assert "Removed connection openrouter" in removed.output


def test_connections_list_empty(runner: CliRunner) -> None:
    result = runner.invoke(app, ["connections", "list"])
    assert result.exit_code == 0
    assert "No connections" in result.output


def test_connections_add_keyless(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        ["connections", "add", "ollama", "--endpoint", "http://localhost:11434/v1", "--keyless"],
    )
    assert result.exit_code == 0, result.output
    listed = runner.invoke(app, ["connections", "list"])
    assert "keyless" in listed.output


def test_connections_test_probes_and_reports(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner.invoke(
        app, ["connections", "add", "openrouter", "--endpoint", "https://o/v1", "--key", "sk-x"]
    )
    from weaver.providers.discovery import DiscoveryResult

    monkeypatch.setattr(
        "weaver.services.connections.list_models",
        lambda **_: DiscoveryResult(models=("m1", "m2"), latency_ms=12),
    )
    result = runner.invoke(app, ["connections", "test", "openrouter"])
    assert result.exit_code == 0, result.output
    assert "2 models" in result.output


def test_routing_set_and_show(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    from weaver.services.project import initialize_project

    fixture = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"
    init = initialize_project(fixture)
    runner.invoke(
        app, ["connections", "add", "openrouter", "--endpoint", "https://o/v1", "--key", "sk-x"]
    )

    set_result = runner.invoke(
        app,
        [
            "routing",
            "set",
            str(init.project_toml),
            "--connection",
            "openrouter",
            "--model",
            "gpt-5",
        ],
    )
    assert set_result.exit_code == 0, set_result.output

    show = runner.invoke(app, ["routing", "show", str(init.project_toml)])
    assert show.exit_code == 0, show.output
    assert "translate: gpt-5 via openrouter" in show.output


def test_routing_set_unknown_task_errors(runner: CliRunner, tmp_path: Path) -> None:
    project = tmp_path / "project.toml"
    project.write_text("", encoding="utf-8")
    result = runner.invoke(
        app, ["routing", "set", str(project), "--connection", "x", "--task", "bogus"]
    )
    assert result.exit_code != 0
