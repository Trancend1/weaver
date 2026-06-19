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
    monkeypatch.setenv("WEAVER_CONNECTION_MODELS_PATH", str(tmp_path / "models.json"))


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


def test_routing_panel_escapes_unknown_project_name(tmp_path: Path) -> None:
    # The unknown-project fallback reflects the route param — it must be escaped,
    # never injected as raw HTML (reflected-XSS guard).
    client = TestClient(create_api_app(tmp_path))
    # Slash-free payload so FastAPI keeps it in the single {name} segment.
    resp = client.get("/ui/projects/<img src=x onerror=alert(1)>/routing")
    assert resp.status_code == 200
    assert "<img src=x onerror=alert(1)>" not in resp.text  # not reflected raw
    assert "&lt;img" in resp.text  # escaped


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

    # The live probe cached the snapshot: cached-models renders it without probing.
    from weaver.core.connection_models import get_cached

    assert get_cached("openrouter") is not None
    cached_resp = client.get(
        "/ui/projects/alpha/routing/cached-models", params={"connection": "openrouter"}
    )
    assert cached_resp.status_code == 200
    assert "m1" in cached_resp.text and "m2" in cached_resp.text


def test_routing_cached_models_reads_cache_without_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init(tmp_path, "alpha")
    _register_openrouter()
    from weaver.core.connection_models import save_cached

    save_cached("openrouter", ["cached-1", "cached-2"])
    # If the route probed, this would raise (no network) — it must read cache only.
    monkeypatch.setattr(
        "weaver.services.connections.list_models",
        lambda **_: (_ for _ in ()).throw(AssertionError("must not probe on cached-models")),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.get(
        "/ui/projects/alpha/routing/cached-models", params={"connection": "openrouter"}
    )
    assert resp.status_code == 200
    assert "cached-1" in resp.text and "cached-2" in resp.text


def test_routing_add_and_clear_fallback(tmp_path: Path) -> None:
    import tomllib

    _init(tmp_path, "alpha")
    _register_openrouter()
    from weaver.core.connection_registry import Connection, register_connection

    register_connection(Connection(name="backup", base_url="https://b/v1", api_key_env="B_KEY"))
    client = TestClient(create_api_app(tmp_path))
    # set a primary first
    client.post(
        "/ui/projects/alpha/routing/switch",
        data={"connection": "openrouter", "model": "pm", "task": "translate"},
    )
    # add a fallback
    resp = client.post(
        "/ui/projects/alpha/routing/fallback/add",
        data={"connection": "backup", "model": "bm"},
    )
    assert resp.status_code == 200
    assert "backup" in resp.text
    project_toml = tmp_path / ".weaver" / "alpha" / "project.toml"
    data = tomllib.loads(project_toml.read_text(encoding="utf-8"))
    assert data["routing"]["translate"]["fallback"] == [{"connection": "backup", "model": "bm"}]

    # clear it
    client.post("/ui/projects/alpha/routing/fallback/clear")
    data = tomllib.loads(project_toml.read_text(encoding="utf-8"))
    assert "fallback" not in data["routing"]["translate"]


def test_routing_add_fallback_without_primary_is_inline_error(tmp_path: Path) -> None:
    _init(tmp_path, "alpha")
    _register_openrouter()
    client = TestClient(create_api_app(tmp_path))
    # no primary routing set (legacy provider) -> adding a fallback is rejected
    resp = client.post(
        "/ui/projects/alpha/routing/fallback/add", data={"connection": "openrouter", "model": "m"}
    )
    assert resp.status_code == 200
    assert 'role="alert"' in resp.text
    assert "Set a primary AI first" in resp.text


def test_routing_panel_shows_cached_models_for_active_connection(tmp_path: Path) -> None:
    _init(tmp_path, "alpha")
    _register_openrouter()
    from weaver.core.connection_models import save_cached

    save_cached("openrouter", ["panel-model"])
    client = TestClient(create_api_app(tmp_path))
    # point the project at the connection so it is the active connection
    client.post(
        "/ui/projects/alpha/routing/switch",
        data={"connection": "openrouter", "model": "panel-model", "task": "translate"},
    )
    resp = client.get("/ui/projects/alpha/routing")
    assert resp.status_code == 200
    assert "panel-model" in resp.text


def test_routing_panel_shows_grouped_models_across_connections(tmp_path: Path) -> None:
    _init(tmp_path, "alpha")
    _register_openrouter()
    from weaver.core.connection_models import save_cached
    from weaver.core.connection_registry import Connection, register_connection

    register_connection(
        Connection(name="local", base_url="http://localhost:11434/v1", api_key_env="")
    )
    save_cached("openrouter", ["m1", "m2"])
    save_cached("local", ["l1"])
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui/projects/alpha/routing")
    assert resp.status_code == 200
    assert "openrouter" in resp.text
    assert "local" in resp.text
    assert "m1" in resp.text
    assert "m2" in resp.text
    assert "l1" in resp.text


def test_routing_panel_stale_badge_on_expired_cache(tmp_path: Path) -> None:
    _init(tmp_path, "alpha")
    _register_openrouter()
    from datetime import UTC, datetime, timedelta

    from weaver.core.connection_models import DEFAULT_TTL_SECONDS, save_cached

    past = (datetime.now(UTC) - timedelta(seconds=DEFAULT_TTL_SECONDS + 1)).isoformat()
    save_cached("openrouter", ["old-model"], now=datetime.fromisoformat(past))
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui/projects/alpha/routing")
    assert resp.status_code == 200
    assert "stale" in resp.text
