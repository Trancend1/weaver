"""Tests for the on-demand AI glossary-target suggestion endpoint (Sprint R).

The provider is patched at the router boundary so these tests never call a live model;
the focus is the endpoint contract: editable pre-fill + cost line, visible failure,
Gate B1 (no provider on render), and no secret leak.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import weaver.api.routers.ui_admin as ui_admin
from weaver.api.app import create_api_app
from weaver.services.glossary_suggestion import GlossarySuggestion
from weaver.services.project import initialize_project


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path)
    return TestClient(create_api_app(tmp_path))


def _name(c: TestClient) -> str:
    return c.get("/projects").json()["projects"][0]["name"]


def _cid(c: TestClient, name: str) -> int:
    page = c.get(f"/projects/{name}/glossary/candidates").json()
    if not page["candidates"]:
        pytest.skip("fixture produced no glossary candidates")
    return page["candidates"][0]["id"]


def test_suggest_fills_target_and_shows_cost(client: TestClient, monkeypatch) -> None:
    name = _name(client)
    cid = _cid(client, name)
    monkeypatch.setattr(
        ui_admin,
        "suggest_glossary_target",
        lambda *a, **k: GlossarySuggestion("Demon King", "deepseek", "deepseek-chat", 11, 3),
    )
    r = client.post(f"/ui/projects/{name}/glossary/candidates/{cid}/suggest")
    assert r.status_code == 200
    assert 'value="Demon King"' in r.text  # editable field pre-filled (gate 4)
    assert "deepseek" in r.text and "deepseek-chat" in r.text  # cost/provenance (gate 6)
    assert "14 tokens" in r.text


def test_suggest_failure_is_visible_not_silent(client: TestClient, monkeypatch) -> None:
    from weaver.errors import GlossarySuggestionError

    name = _name(client)
    cid = _cid(client, name)

    def _boom(*a, **k):
        raise GlossarySuggestionError("AI returned no usable suggestion: empty.")

    monkeypatch.setattr(ui_admin, "suggest_glossary_target", _boom)
    r = client.post(f"/ui/projects/{name}/glossary/candidates/{cid}/suggest")
    assert r.status_code == 200  # fragment swap, error shown in-place
    assert "no usable suggestion" in r.text
    assert 'value=""' in r.text  # no garbage pre-fill on failure


def test_gate_b1_glossary_render_calls_no_provider(client: TestClient, monkeypatch) -> None:
    name = _name(client)
    called = {"n": 0}

    def _spy(*a, **k):
        called["n"] += 1
        return GlossarySuggestion("X", "fake", "fake-1", None, None)

    monkeypatch.setattr(ui_admin, "suggest_glossary_target", _spy)
    client.get(f"/ui/projects/{name}/glossary")  # render
    client.get(f"/ui/projects/{name}/glossary/candidates")  # fragment
    client.get(f"/ui/projects/{name}/glossary/terms")  # fragment
    assert called["n"] == 0  # Gate B1: zero on render
    client.post(f"/ui/projects/{name}/glossary/candidates/{_cid(client, name)}/suggest")
    assert called["n"] == 1  # only on explicit POST


def test_suggest_response_leaks_no_secret_value(client: TestClient, monkeypatch) -> None:
    name = _name(client)
    cid = _cid(client, name)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-SECRET-should-never-render")
    monkeypatch.setattr(
        ui_admin,
        "suggest_glossary_target",
        lambda *a, **k: GlossarySuggestion("Hero", "deepseek", "deepseek-chat", 1, 1),
    )
    r = client.post(f"/ui/projects/{name}/glossary/candidates/{cid}/suggest")
    assert "sk-SECRET-should-never-render" not in r.text
