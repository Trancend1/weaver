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
    _init(tmp_path, "alpha")
    _init(tmp_path, "beta")
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


def test_secret_value_never_rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_value = "sk-SUPER-SECRET-DO-NOT-RENDER-9999"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret_value)
    _init(tmp_path, "alpha")
    client = TestClient(create_api_app(tmp_path))
    html = client.get("/ui/providers").text
    assert secret_value not in html
    assert "DEEPSEEK_API_KEY" in html  # name shown, value not


# ---------------------------------------------------------------------------
# 5. No provider instantiation on render
# ---------------------------------------------------------------------------


def test_no_provider_call_on_hub_get(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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

    monkeypatch.setattr(
        "weaver.api.routers.ui_providers.build_workspace_providers", _fake
    )
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
