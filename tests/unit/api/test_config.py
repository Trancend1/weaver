"""Tests for the provider/secret config API (Sprint 10C).

The local secret store and global config are isolated to ``tmp_path`` so no real
user files (``~/.weaver/secrets.toml`` / ``config.toml``) are read or written, and
no real API keys can leak into assertions.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the secret store and Path.home() into tmp_path."""
    home = tmp_path / "home"
    (home / ".weaver").mkdir(parents=True)
    monkeypatch.setenv("WEAVER_SECRETS_PATH", str(home / ".weaver" / "secrets.toml"))
    monkeypatch.setattr(Path, "home", lambda: home)
    # Keep any ambient real key out of the presence check.
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("MY_CUSTOM_KEY", raising=False)
    return tmp_path


def _client(base: Path) -> TestClient:
    return TestClient(create_api_app(base))


def _make_project(base: Path) -> str:
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=base)
    return epubs[0].stem


# --- GET --------------------------------------------------------------------


def test_get_config_global_only(isolated: Path) -> None:
    client = _client(isolated)
    body = client.get("/config").json()
    assert body["project_name"] is None
    assert body["provider_type"] is None
    assert body["secret_names"] == []
    assert "api_key_set" in body


def test_get_config_with_project(isolated: Path) -> None:
    name = _make_project(isolated)
    client = _client(isolated)
    body = client.get("/config", params={"project": name}).json()
    assert body["project_name"] == name
    assert body["provider_type"] is None  # new projects require explicit provider config


def test_get_config_unknown_project_404(isolated: Path) -> None:
    client = _client(isolated)
    assert client.get("/config", params={"project": "ghost"}).status_code == 404


# --- PATCH ------------------------------------------------------------------


def test_patch_project_scope_persists(isolated: Path) -> None:
    name = _make_project(isolated)
    client = _client(isolated)
    r = client.patch(
        "/config",
        json={"scope": "project", "project": name, "provider_type": "fake", "model": "fake-9"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["provider_type"] == "custom"
    assert body["protocol"] == "fake"
    assert body["model"] == "fake-9"
    # persisted: a fresh read reflects it
    again = client.get("/config", params={"project": name}).json()
    assert again["model"] == "fake-9"


def test_patch_global_scope_persists(isolated: Path) -> None:
    client = _client(isolated)
    r = client.patch(
        "/config",
        json={"scope": "global", "provider_type": "gemini", "model": "gemini-x"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["default_provider"] == "gemini"
    assert body["default_model"] == "gemini-x"


def test_patch_freeform_provider_type_persists(isolated: Path) -> None:
    name = _make_project(isolated)
    client = _client(isolated)
    r = client.patch(
        "/config",
        json={"scope": "project", "project": name, "provider_type": "not-real"},
    )
    assert r.status_code == 200
    assert r.json()["provider_type"] == "not-real"


def test_patch_project_scope_without_project_422(isolated: Path) -> None:
    client = _client(isolated)
    r = client.patch("/config", json={"scope": "project", "provider_type": "fake"})
    assert r.status_code == 422


def test_patch_unknown_scope_422(isolated: Path) -> None:
    client = _client(isolated)
    # Pydantic Literal rejects an out-of-set scope before the service runs.
    r = client.patch("/config", json={"scope": "nope", "provider_type": "fake"})
    assert r.status_code == 422


# --- secrets ----------------------------------------------------------------


def test_set_secret_stores_without_echo(isolated: Path) -> None:
    client = _client(isolated)
    r = client.post("/config/secrets/MY_CUSTOM_KEY", json={"value": "sk-super-secret"})
    assert r.status_code == 201
    body = r.json()
    assert body == {"name": "MY_CUSTOM_KEY", "is_set": True}
    # value never appears anywhere in the response
    assert "sk-super-secret" not in r.text
    # and it now shows as a stored name (name only) + presence true
    cfg = client.get("/config").json()
    assert "MY_CUSTOM_KEY" in cfg["secret_names"]
    assert "sk-super-secret" not in client.get("/config").text


def test_set_secret_invalid_name_422(isolated: Path) -> None:
    client = _client(isolated)
    r = client.post("/config/secrets/bad name!", json={"value": "x"})
    assert r.status_code == 422


def test_set_secret_empty_value_422(isolated: Path) -> None:
    client = _client(isolated)
    r = client.post("/config/secrets/MY_CUSTOM_KEY", json={"value": ""})
    assert r.status_code == 422


def test_delete_secret_removes(isolated: Path) -> None:
    client = _client(isolated)
    client.post("/config/secrets/MY_CUSTOM_KEY", json={"value": "v"})
    r = client.delete("/config/secrets/MY_CUSTOM_KEY")
    assert r.status_code == 200
    assert r.json() == {"name": "MY_CUSTOM_KEY", "is_set": False}
    assert "MY_CUSTOM_KEY" not in client.get("/config").json()["secret_names"]


def test_delete_unknown_secret_404(isolated: Path) -> None:
    client = _client(isolated)
    assert client.delete("/config/secrets/NEVER_SET").status_code == 404


def test_api_key_set_reflects_stored_secret(isolated: Path) -> None:
    name = _make_project(isolated)
    client = _client(isolated)
    # point the project's api_key_env at a name, then store that secret
    client.patch(
        "/config",
        json={
            "scope": "project",
            "project": name,
            "provider_type": "custom",
            "api_key_env": "MY_CUSTOM_KEY",
        },
    )
    before = client.get("/config", params={"project": name}).json()
    assert before["api_key_env"] == "MY_CUSTOM_KEY"
    assert before["api_key_set"] is False

    client.post("/config/secrets/MY_CUSTOM_KEY", json={"value": "k"})
    after = client.get("/config", params={"project": name}).json()
    assert after["api_key_set"] is True
