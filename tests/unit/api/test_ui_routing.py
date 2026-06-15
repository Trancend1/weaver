"""Active AI / Switch AI route tests (ADR 018 D7/D8)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app


def _init(tmp_path: Path, name: str, provider: str | None = "deepseek") -> None:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path, project_name=name, provider=provider)


@pytest.fixture(autouse=True)
def isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEAVER_CONNECTIONS_PATH", str(tmp_path / "connections.toml"))
    monkeypatch.setenv("WEAVER_SECRETS_PATH", str(tmp_path / "secrets.toml"))


def _register_openrouter() -> None:
    from weaver.core.connection_registry import Connection, register_connection

    register_connection(
        Connection(
            name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            default_model="deepseek/deepseek-chat",
        )
    )


def test_routing_panel_renders_active_ai(tmp_path: Path) -> None:
    _init(tmp_path, "alpha")
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui/projects/alpha/routing")
    assert resp.status_code == 200
    assert "Active AI" in resp.text
    # no connections yet → prompts to add one
    assert "No connections yet" in resp.text


def test_routing_panel_lists_connections(tmp_path: Path) -> None:
    _init(tmp_path, "alpha")
    _register_openrouter()
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui/projects/alpha/routing")
    assert resp.status_code == 200
    assert "openrouter" in resp.text
    assert "Switch AI" in resp.text


def test_routing_switch_writes_routing_block(tmp_path: Path) -> None:
    _init(tmp_path, "alpha")
    _register_openrouter()
    client = TestClient(create_api_app(tmp_path))
    resp = client.post(
        "/ui/projects/alpha/routing/switch",
        data={"connection": "openrouter", "model": "chosen-model", "task": "translate"},
    )
    assert resp.status_code == 200
    assert "Saved" in resp.text
    assert "chosen-model" in resp.text
    project_toml = tmp_path / ".weaver" / "alpha" / "project.toml"
    data = tomllib.loads(project_toml.read_text(encoding="utf-8"))
    assert data["routing"]["translate"]["connection"] == "openrouter"
    assert data["routing"]["translate"]["model"] == "chosen-model"


def test_routing_switch_unknown_connection_is_inline_error(tmp_path: Path) -> None:
    _init(tmp_path, "alpha")
    client = TestClient(create_api_app(tmp_path))
    # the switch writes the block; the error surfaces when the panel resolves it
    resp = client.post(
        "/ui/projects/alpha/routing/switch",
        data={"connection": "ghost", "model": "m", "task": "translate"},
    )
    assert resp.status_code == 200
    assert "connection missing" in resp.text


def test_routing_models_probe_renders_datalist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init(tmp_path, "alpha")
    _register_openrouter()
    from weaver.providers.discovery import DiscoveryResult

    monkeypatch.setattr(
        "weaver.services.connections.list_models",
        lambda **_: DiscoveryResult(models=("m1", "m2"), latency_ms=5),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.post("/ui/projects/alpha/routing/models", data={"connection": "openrouter"})
    assert resp.status_code == 200
    assert "m1" in resp.text and "m2" in resp.text
    assert "2 models found" in resp.text
