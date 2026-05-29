"""Unit tests for the provider/model config writer (ADR ``0018``)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from weaver.errors import ConfigError
from weaver.services import config_writer
from weaver.services.config_writer import set_provider

PROJECT_TOML = """\
[project]
name = "novel"

# provider section below
[provider]
type = "deepseek"
model = "deepseek-chat"

[translation]
honorifics = "preserve"
"""


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_set_provider_project_scope_updates_and_preserves(tmp_path: Path) -> None:
    toml = _write(tmp_path / "project.toml", PROJECT_TOML)

    set_provider(toml, provider_type="gemini", model="gemini-1.5-flash")

    data = tomllib.loads(toml.read_text(encoding="utf-8"))
    assert data["provider"]["type"] == "gemini"
    assert data["provider"]["model"] == "gemini-1.5-flash"
    # Unrelated tables/keys preserved.
    assert data["project"]["name"] == "novel"
    assert data["translation"]["honorifics"] == "preserve"
    # Comment preserved (line-based edit, exceeds ADR minimum).
    assert "# provider section below" in toml.read_text(encoding="utf-8")


def test_set_provider_inserts_missing_key(tmp_path: Path) -> None:
    toml = _write(tmp_path / "project.toml", PROJECT_TOML)

    set_provider(toml, base_url="http://localhost:11434")

    data = tomllib.loads(toml.read_text(encoding="utf-8"))
    assert data["provider"]["base_url"] == "http://localhost:11434"
    assert data["provider"]["type"] == "deepseek"  # untouched


def test_set_provider_global_scope_writes_defaults(tmp_path: Path, monkeypatch) -> None:
    global_path = tmp_path / ".weaver" / "config.toml"
    monkeypatch.setattr(config_writer, "default_global_config_path", lambda: global_path)

    set_provider(global_path, provider_type="ollama", model="llama3")

    data = tomllib.loads(global_path.read_text(encoding="utf-8"))
    assert data["defaults"]["default_provider"] == "ollama"
    assert data["defaults"]["default_model"] == "llama3"


def test_set_provider_custom_writes_endpoint_fields(tmp_path: Path) -> None:
    toml = _write(tmp_path / "project.toml", PROJECT_TOML)

    set_provider(
        toml,
        provider_type="custom",
        model="some-model",
        base_url="https://api.example.com/v1",
        api_key_env="MY_API_KEY",
    )

    raw = toml.read_text(encoding="utf-8")
    data = tomllib.loads(raw)
    assert data["provider"]["type"] == "custom"
    assert data["provider"]["base_url"] == "https://api.example.com/v1"
    assert data["provider"]["api_key_env"] == "MY_API_KEY"
    # Only the env-var NAME is written — never an actual key value.
    assert "api_key " not in raw and 'api_key"' not in raw


def test_set_provider_rejects_unknown_provider(tmp_path: Path) -> None:
    toml = _write(tmp_path / "project.toml", PROJECT_TOML)
    with pytest.raises(ConfigError):
        set_provider(toml, provider_type="not-a-provider")


def test_set_provider_missing_project_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        set_provider(tmp_path / "nope.toml", model="x")
