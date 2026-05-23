"""Tests for global config loading and value resolution."""

from __future__ import annotations

import os
from pathlib import Path

from weaver.core.global_config import load_global_config, resolve_config_value


def test_missing_config_file_returns_empty(tmp_path: Path) -> None:
    result = load_global_config(tmp_path / "nonexistent" / "config.toml")
    assert result == {}


def test_empty_config_file_returns_empty(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    result = load_global_config(config_path)
    assert result == {}


def test_valid_toml_loads(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'default_provider = "gemini"\ndefault_model = "gemini-2.0-flash"\n',
        encoding="utf-8",
    )
    result = load_global_config(config_path)
    assert result["default_provider"] == "gemini"
    assert result["default_model"] == "gemini-2.0-flash"


def test_malformed_toml_returns_empty(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("this is not = valid [ toml", encoding="utf-8")
    result = load_global_config(config_path)
    assert result == {}


def test_resolve_cli_wins_over_all() -> None:
    result = resolve_config_value(
        "type",
        cli_value="ollama",
        env_var="WEAVER_DEFAULT_PROVIDER",
        project_config={"type": "deepseek"},
        global_config={"type": "gemini"},
        default="fake",
    )
    assert result == "ollama"


def test_resolve_env_wins_over_project_and_global(monkeypatch: object) -> None:
    os.environ["_TEST_WEAVER_PROVIDER"] = "gemini"
    try:
        result = resolve_config_value(
            "type",
            cli_value=None,
            env_var="_TEST_WEAVER_PROVIDER",
            project_config={"type": "deepseek"},
            global_config={"type": "fake"},
            default="ollama",
        )
        assert result == "gemini"
    finally:
        del os.environ["_TEST_WEAVER_PROVIDER"]


def test_resolve_project_wins_over_global() -> None:
    result = resolve_config_value(
        "type",
        cli_value=None,
        env_var=None,
        project_config={"type": "deepseek"},
        global_config={"type": "gemini"},
        default="fake",
    )
    assert result == "deepseek"


def test_resolve_global_wins_over_default() -> None:
    result = resolve_config_value(
        "type",
        cli_value=None,
        env_var=None,
        project_config=None,
        global_config={"type": "gemini"},
        default="fake",
    )
    assert result == "gemini"


def test_resolve_falls_through_to_default() -> None:
    result = resolve_config_value(
        "type",
        cli_value=None,
        env_var=None,
        project_config=None,
        global_config=None,
        default="deepseek",
    )
    assert result == "deepseek"
