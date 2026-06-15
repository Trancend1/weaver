"""Q6 tests: Global Providers hub.

Verifies:
- Providers route renders ws-hub layout with workspace sidebar (active entry)
- Provider/model + token usage show across projects
- Explicit health-check POST returns a status fragment (healthy + failing cases)
- No secret VALUE is ever rendered (only the env-var name)
- Zero provider instantiation on the hub GET (render path)
- Degraded projects do not blank the hub
- Router GET is thin (no direct DB access)
- Existing routes still render
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.workspace_providers import (
    ProjectProviderSummary,
    ProviderDegradedProject,
    WorkspaceProviders,
)


def _init(tmp_path: Path, name: str, provider: str | None = None) -> None:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path, project_name=name, provider=provider)


@pytest.fixture
def providers_client(tmp_path: Path) -> TestClient:
    _init(tmp_path, "alpha", provider="deepseek")
    _init(tmp_path, "beta", provider="deepseek")
    return TestClient(create_api_app(tmp_path))


@pytest.fixture
def empty_providers_client(tmp_path: Path) -> TestClient:
    return TestClient(create_api_app(tmp_path))


# ---------------------------------------------------------------------------
# 1. Layout
# ---------------------------------------------------------------------------


def test_providers_uses_ws_hub_layout(providers_client: TestClient) -> None:
    html = providers_client.get("/ui/providers").text
    assert "layout--ws-hub" in html
    assert "app-shell--ws-hub" in html


def test_providers_has_workspace_sidebar(providers_client: TestClient) -> None:
    html = providers_client.get("/ui/providers").text
    assert 'class="sidebar sidebar--ws-hub"' in html


def test_providers_sidebar_entry_is_active(providers_client: TestClient) -> None:
    html = providers_client.get("/ui/providers").text
    assert 'href="/ui/providers"' in html
    link = html.split('href="/ui/providers"')[1].split("</a>")[0]
    assert 'aria-current="page"' in link or "active" in link


# ---------------------------------------------------------------------------
# 2. Content
# ---------------------------------------------------------------------------


def test_providers_shows_project_and_model(providers_client: TestClient) -> None:
    html = providers_client.get("/ui/providers").text
    assert "alpha" in html
    assert "beta" in html
    assert "deepseek" in html
    assert "deepseek-chat" in html


def test_providers_shows_key_env_name(providers_client: TestClient) -> None:
    html = providers_client.get("/ui/providers").text
    assert "DEEPSEEK_API_KEY" in html


# ---------------------------------------------------------------------------
# 3. Health check (explicit, on demand)
# ---------------------------------------------------------------------------


def test_healthcheck_fake_provider_is_healthy(tmp_path: Path) -> None:
    _init(tmp_path, "fakeproj", provider="fake")
    client = TestClient(create_api_app(tmp_path))
    resp = client.post("/ui/providers/fakeproj/healthcheck")
    assert resp.status_code == 200
    assert "healthy" in resp.text.lower()


def test_healthcheck_missing_key_reports_unhealthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    _init(tmp_path, "alpha")
    client = TestClient(create_api_app(tmp_path))
    resp = client.post("/ui/providers/alpha/healthcheck")
    assert resp.status_code == 200
    # Either an unhealthy badge or an error badge — never a crash.
    assert "unhealthy" in resp.text.lower() or "error" in resp.text.lower()


def test_healthcheck_unknown_project_is_handled(providers_client: TestClient) -> None:
    resp = providers_client.post("/ui/providers/nope/healthcheck")
    assert resp.status_code == 200
    assert "error" in resp.text.lower() or "no project" in resp.text.lower()


# ---------------------------------------------------------------------------
# 4. Secret-leak regression — value never rendered
# ---------------------------------------------------------------------------


def test_secret_value_never_rendered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_value = "sk-SUPER-SECRET-DO-NOT-RENDER-9999"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret_value)
    _init(tmp_path, "alpha", provider="deepseek")
    client = TestClient(create_api_app(tmp_path))
    html = client.get("/ui/providers").text
    assert secret_value not in html
    assert "DEEPSEEK_API_KEY" in html  # name shown, value not


# ---------------------------------------------------------------------------
# 5. No provider instantiation on render
# ---------------------------------------------------------------------------


def test_no_provider_call_on_hub_get(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init(tmp_path, "alpha")
    client = TestClient(create_api_app(tmp_path))

    calls = {"n": 0}

    def _spy(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        calls["n"] += 1
        raise AssertionError("provider must not be built on hub GET")

    monkeypatch.setattr("weaver.providers.registry.build_provider", _spy)
    resp = client.get("/ui/providers")
    assert resp.status_code == 200
    assert calls["n"] == 0


def test_legacy_config_page_redirects_to_providers_editor(
    providers_client: TestClient,
) -> None:
    resp = providers_client.get("/ui/config", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/ui/providers#connections"


def test_legacy_config_page_redirect_preserves_project_query(
    providers_client: TestClient,
) -> None:
    resp = providers_client.get("/ui/config", params={"project": "alpha"}, follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/ui/providers?project=alpha#connections"


def test_legacy_config_redirect_does_not_build_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init(tmp_path, "alpha")
    client = TestClient(create_api_app(tmp_path))
    calls = {"n": 0}

    def _spy(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        calls["n"] += 1
        raise AssertionError("legacy config redirect must not build providers")

    monkeypatch.setattr("weaver.api.routers.ui_providers.build_workspace_providers", _spy)
    resp = client.get("/ui/config", follow_redirects=False)
    assert resp.status_code == 307
    assert calls["n"] == 0


# ---------------------------------------------------------------------------
# 6. Empty + degraded
# ---------------------------------------------------------------------------


def test_empty_providers_renders_empty_state(empty_providers_client: TestClient) -> None:
    html = empty_providers_client.get("/ui/providers").text
    assert "No providers to show" in html


def test_degraded_project_does_not_blank_hub(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    good = ProjectProviderSummary(
        project_name="good",
        project_uuid="uuid-good",
        state="ready",
        provider_type="deepseek",
        model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        requires_key=True,
        secret_present=False,
        input_tokens=10,
        output_tokens=5,
        failed_job_count=0,
        recent_failures=[],
    )
    degraded = [ProviderDegradedProject("bad", None, "error", "DB locked")]

    def _fake(*args: object, **kwargs: object) -> WorkspaceProviders:
        _ = (args, kwargs)
        return WorkspaceProviders(projects=[good], degraded=degraded, generated_at=0.0)

    monkeypatch.setattr("weaver.api.routers.ui_providers.build_workspace_providers", _fake)
    client = TestClient(create_api_app(tmp_path))
    resp = client.get("/ui/providers")
    assert resp.status_code == 200
    assert "good" in resp.text
    assert "bad" in resp.text
    assert "DB locked" in resp.text


# ---------------------------------------------------------------------------
# 7. Structural gate — router is thin, no direct DB access
# ---------------------------------------------------------------------------


def test_providers_get_route_is_thin() -> None:
    from weaver.api.routers import ui_providers

    source = inspect.getsource(ui_providers.providers_page)
    assert "build_workspace_providers" in source
    assert "connect_database" not in source
    assert "connect_readonly_database" not in source


# ---------------------------------------------------------------------------
# 8. Regression
# ---------------------------------------------------------------------------


def test_dashboard_still_renders(providers_client: TestClient) -> None:
    assert providers_client.get("/ui").status_code == 200


def test_resources_still_renders(providers_client: TestClient) -> None:
    resp = providers_client.get("/ui/resources")
    assert resp.status_code == 200
    assert "layout--ws-hub" in resp.text


# ---------------------------------------------------------------------------
# 9. Provider config editor (moved from /ui/config)
# ---------------------------------------------------------------------------


def test_providers_secret_set_and_delete_without_exposing_value(
    providers_client: TestClient,
) -> None:
    r = providers_client.post(
        "/ui/providers/secrets", data={"env_name": "MY_KEY", "value": "sk-LEAKCHECK"}
    )
    assert r.status_code == 200
    assert "MY_KEY" in r.text
    assert "sk-LEAKCHECK" not in r.text  # value never rendered
    assert "sk-LEAKCHECK" not in providers_client.get("/ui/providers").text

    delete = providers_client.post("/ui/providers/secrets/MY_KEY/delete")
    assert delete.status_code == 200
    assert "MY_KEY" not in delete.text


def test_providers_secret_invalid_name_error(providers_client: TestClient) -> None:
    r = providers_client.post("/ui/providers/secrets", data={"env_name": "bad name!", "value": "x"})
    assert r.status_code == 200
    assert "error" in r.text.lower()


# ---------------------------------------------------------------------------
# 10. Connection-first surface (legacy provider editor removed)
# ---------------------------------------------------------------------------


def test_providers_hub_has_no_legacy_provider_editor(providers_client: TestClient) -> None:
    html = providers_client.get("/ui/providers").text
    # the pre-0.7.2 [provider] editor is gone
    assert 'name="provider_type"' not in html
    assert 'hx-post="/ui/providers/config"' not in html
    assert "Per-project provider (legacy)" not in html


def test_providers_hub_explains_connection_first_surface(
    providers_client: TestClient,
) -> None:
    html = providers_client.get("/ui/providers").text
    assert "Register AI endpoints once and reuse them across projects." in html
    assert "never shown" in html
    assert "Legacy aliases remain supported" not in html
    assert "Secret values are stored but never rendered." in html


def _isolate_connection_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEAVER_CONNECTIONS_PATH", str(tmp_path / "connections.toml"))
    monkeypatch.setenv("WEAVER_SECRETS_PATH", str(tmp_path / "secrets.toml"))


def test_connection_add_registers_and_never_echoes_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_connection_files(tmp_path, monkeypatch)
    from weaver.core.connection_registry import get_connection

    client = TestClient(create_api_app(tmp_path))
    resp = client.post(
        "/ui/providers/connections",
        data={"name": "openrouter", "base_url": "https://o/v1", "api_key": "sk-SECRET"},
    )
    assert resp.status_code == 200
    assert "openrouter" in resp.text
    assert "sk-SECRET" not in resp.text  # key value never echoed
    conn = get_connection("openrouter")
    assert conn is not None
    assert conn.api_key_env == "WEAVER_CONN_OPENROUTER"


def test_connection_add_records_default_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_connection_files(tmp_path, monkeypatch)
    from weaver.core.connection_registry import get_connection

    client = TestClient(create_api_app(tmp_path))
    resp = client.post(
        "/ui/providers/connections",
        data={
            "name": "openrouter",
            "base_url": "https://o/v1",
            "api_key": "sk-x",
            "default_model": "deepseek/deepseek-chat",
        },
    )
    assert resp.status_code == 200
    conn = get_connection("openrouter")
    assert conn is not None
    assert conn.default_model == "deepseek/deepseek-chat"
    assert "deepseek/deepseek-chat" in resp.text  # shown on the card


def test_connection_add_without_key_shows_inline_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_connection_files(tmp_path, monkeypatch)
    client = TestClient(create_api_app(tmp_path))
    resp = client.post("/ui/providers/connections", data={"name": "c", "base_url": "https://o/v1"})
    assert resp.status_code == 200
    assert 'role="alert"' in resp.text
    assert "needs an API key" in resp.text


def test_connection_test_probe_renders_model_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_connection_files(tmp_path, monkeypatch)
    from weaver.providers.discovery import DiscoveryResult

    monkeypatch.setattr(
        "weaver.services.connections.list_models",
        lambda **_: DiscoveryResult(models=("m1", "m2"), latency_ms=12),
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.post(
        "/ui/providers/connections/test",
        data={"name": "c", "base_url": "https://o/v1", "api_key": "sk-x"},
    )
    assert resp.status_code == 200
    assert "Connected" in resp.text
    assert "2 models" in resp.text


def test_providers_table_shows_active_ai_and_switch_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_connection_files(tmp_path, monkeypatch)
    _init(tmp_path, "alpha", provider="deepseek")
    client = TestClient(create_api_app(tmp_path))
    html = client.get("/ui/providers").text
    assert "Active AI" in html
    assert "deepseek-chat" in html  # legacy [provider] model shown as active AI
    assert "legacy provider" in html
    assert "Switch AI" in html


def test_providers_switch_writes_routing_and_updates_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tomllib

    from weaver.core.connection_registry import Connection, register_connection

    _isolate_connection_files(tmp_path, monkeypatch)
    _init(tmp_path, "alpha", provider="deepseek")
    register_connection(
        Connection(name="openrouter", base_url="https://o/v1", api_key_env="OPENROUTER_API_KEY")
    )
    client = TestClient(create_api_app(tmp_path))
    resp = client.post(
        "/ui/providers/alpha/switch", data={"connection": "openrouter", "model": "gpt-5"}
    )
    assert resp.status_code == 200
    assert "gpt-5" in resp.text
    assert "via openrouter" in resp.text
    project_toml = tmp_path / ".weaver" / "alpha" / "project.toml"
    data = tomllib.loads(project_toml.read_text(encoding="utf-8"))
    assert data["routing"]["translate"]["connection"] == "openrouter"
    assert data["routing"]["translate"]["model"] == "gpt-5"


def test_connection_delete_removes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_connection_files(tmp_path, monkeypatch)
    from weaver.core.connection_registry import get_connection

    client = TestClient(create_api_app(tmp_path))
    client.post(
        "/ui/providers/connections",
        data={"name": "c", "base_url": "https://o/v1", "api_key": "sk-x"},
    )
    resp = client.post("/ui/providers/connections/c/delete")
    assert resp.status_code == 200
    assert get_connection("c") is None


