"""Integration tests for `weaver secrets` (ADR ``0020``)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from weaver.cli.main import app
from weaver.core.secret_store import load_secrets

runner = CliRunner()


def test_secrets_set_list_rm_roundtrip(tmp_path: Path, monkeypatch) -> None:
    store = tmp_path / "secrets.toml"
    monkeypatch.setenv("WEAVER_SECRETS_PATH", str(store))

    set_result = runner.invoke(app, ["secrets", "set", "DEEPSEEK_API_KEY", "--value", "sk-1"])
    assert set_result.exit_code == 0
    assert load_secrets(store)["DEEPSEEK_API_KEY"] == "sk-1"
    assert "sk-1" not in set_result.output  # value never echoed

    list_result = runner.invoke(app, ["secrets", "list"])
    assert list_result.exit_code == 0
    assert "DEEPSEEK_API_KEY" in list_result.output
    assert "sk-1" not in list_result.output  # names only

    rm_result = runner.invoke(app, ["secrets", "rm", "DEEPSEEK_API_KEY"])
    assert rm_result.exit_code == 0
    assert load_secrets(store) == {}


def test_secrets_set_rejects_bad_name(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEAVER_SECRETS_PATH", str(tmp_path / "secrets.toml"))
    result = runner.invoke(app, ["secrets", "set", "1 BAD", "--value", "x"])
    assert result.exit_code != 0


def test_secrets_list_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEAVER_SECRETS_PATH", str(tmp_path / "secrets.toml"))
    result = runner.invoke(app, ["secrets", "list"])
    assert result.exit_code == 0
    assert "No secrets stored" in result.output
