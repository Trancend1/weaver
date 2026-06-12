"""Tests for the glossary admin UI routes (term CRUD + candidate review).

Candidate review uses an optimistic scheme: the action POSTs in the background
(``hx-swap="none"``) and the row/counts/Approved-terms update client-side. The
endpoint therefore returns ``204`` on success and ``404``/``422`` on failure (no
silent success), and a dedicated GET fragment refreshes the Approved-terms table.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.project import initialize_project


@pytest.fixture
def gloss_client(tmp_path: Path) -> TestClient:
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path)
    return TestClient(create_api_app(tmp_path))


def _name(client: TestClient) -> str:
    return client.get("/projects").json()["projects"][0]["name"]


def _candidates(client: TestClient, name: str) -> list[dict]:
    page = client.get(f"/projects/{name}/glossary/candidates").json()
    if not page["candidates"]:
        pytest.skip("fixture produced no glossary candidates")
    return page["candidates"]


def _pending_ids(client: TestClient, name: str) -> list[int]:
    page = client.get(f"/projects/{name}/glossary/candidates").json()
    return [c["id"] for c in page["candidates"]]


def test_glossary_page_has_no_dead_ai_stub(gloss_client: TestClient) -> None:
    """The always-erroring 'Translate target with AI' CTA must be gone."""
    name = _name(gloss_client)
    page = gloss_client.get(f"/ui/projects/{name}/glossary").text
    assert "Translate target with AI" not in page
    assert "not wired yet" not in page
    # optimistic scheme markers: counts spans + per-row ids + background POST
    assert 'id="glossary-candidate-counts"' in page
    assert 'data-count="pending"' in page
    assert 'id="cand-' in page
    assert 'data-gc-action="approve"' in page
    assert 'hx-swap="none"' in page
    # bulk + keyboard affordances for power-user review at scale
    assert 'data-gc-bulk="approve"' in page
    assert 'data-gc-bulk="reject"' in page
    assert "data-gc-selectall" in page
    assert 'class="gc-select"' in page


def test_candidate_reject_returns_204_and_removes_from_pending(gloss_client: TestClient) -> None:
    name = _name(gloss_client)
    cands = _candidates(gloss_client, name)
    cid = cands[0]["id"]
    r = gloss_client.post(f"/ui/projects/{name}/glossary/candidates/{cid}/reject")
    assert r.status_code == 204
    assert cid not in _pending_ids(gloss_client, name)


def test_candidate_edit_204_then_term_appears_in_terms_fragment(gloss_client: TestClient) -> None:
    name = _name(gloss_client)
    cands = _candidates(gloss_client, name)
    cid = cands[0]["id"]
    r = gloss_client.post(
        f"/ui/projects/{name}/glossary/candidates/{cid}/edit", data={"target": "My EN Term"}
    )
    assert r.status_code == 204
    # the Approved-terms fragment (used for the live refresh) now shows the term
    frag = gloss_client.get(f"/ui/projects/{name}/glossary/terms")
    assert frag.status_code == 200
    assert "My EN Term" in frag.text
    assert 'id="glossary-terms"' in frag.text


def test_candidate_unknown_action_fails_with_422_not_silent(gloss_client: TestClient) -> None:
    """The removed 'translate' action (or any unknown one) must fail loudly (non-2xx)."""
    name = _name(gloss_client)
    cands = _candidates(gloss_client, name)
    cid = cands[0]["id"]
    r = gloss_client.post(f"/ui/projects/{name}/glossary/candidates/{cid}/translate")
    assert r.status_code == 422
    assert r.text  # carries an explanatory message HTMX can surface
    # candidate was not acted on
    assert cid in _pending_ids(gloss_client, name)


def test_candidate_missing_id_returns_404(gloss_client: TestClient) -> None:
    name = _name(gloss_client)
    r = gloss_client.post(f"/ui/projects/{name}/glossary/candidates/999999/approve")
    assert r.status_code == 404


# --- #2 approved-terms search + pagination ----------------------------------


def _add_term(client: TestClient, name: str, *, source: str, target: str) -> None:
    r = client.post(
        f"/ui/projects/{name}/glossary/terms", data={"source": source, "target": target}
    )
    assert r.status_code == 200


def test_terms_fragment_has_search_form(gloss_client: TestClient) -> None:
    name = _name(gloss_client)
    frag = gloss_client.get(f"/ui/projects/{name}/glossary/terms").text
    assert 'name="find"' in frag
    assert "search source or target" in frag


def test_terms_search_filters_by_source_or_target(gloss_client: TestClient) -> None:
    name = _name(gloss_client)
    _add_term(gloss_client, name, source="魔王", target="Demon King")
    _add_term(gloss_client, name, source="勇者", target="Hero")

    by_target = gloss_client.get(f"/ui/projects/{name}/glossary/terms?find=king").text
    assert "魔王" in by_target
    assert "勇者" not in by_target

    none = gloss_client.get(f"/ui/projects/{name}/glossary/terms?find=ZZZ").text
    assert "No approved terms match" in none


def test_terms_pagination_pages_through(gloss_client: TestClient) -> None:
    name = _name(gloss_client)
    # TERMS_PAGE is 20; seed enough to force a second page.
    for i in range(22):
        _add_term(gloss_client, name, source=f"語{i:02d}", target=f"Word{i:02d}")

    first = gloss_client.get(f"/ui/projects/{name}/glossary/terms").text
    assert "next →" in first
    assert "showing 1–20" in first

    second = gloss_client.get(f"/ui/projects/{name}/glossary/terms?offset=20").text
    assert "← prev" in second
    assert "語20" in second  # 21st term, only on page 2


def test_term_delete_keeps_search_context(gloss_client: TestClient) -> None:
    name = _name(gloss_client)
    _add_term(gloss_client, name, source="魔王", target="Demon King")
    _add_term(gloss_client, name, source="魔法", target="Magic")

    # Delete one term while a search is active; the re-render keeps the filter.
    r = gloss_client.post(
        f"/ui/projects/{name}/glossary/terms/魔法/delete", data={"find": "魔", "offset": "0"}
    )
    assert r.status_code == 200
    assert 'value="魔"' in r.text  # search box retains the needle
    assert "魔王" in r.text
    assert "魔法" not in r.text


def test_term_search_needle_with_quote_is_safe(gloss_client: TestClient) -> None:
    """A needle containing a double quote must not break the threaded find context."""
    name = _name(gloss_client)
    _add_term(gloss_client, name, source="魔王", target='The "Demon King"')

    frag = gloss_client.get(f"/ui/projects/{name}/glossary/terms", params={"find": 'King"'})
    assert frag.status_code == 200
    # the term is found and the quoted needle round-trips into the hidden inputs
    assert "魔王" in frag.text
    assert "&#34;" in frag.text or "&quot;" in frag.text  # autoescaped, never raw-broken


# --- #3 lazy example sentences ----------------------------------------------


def test_glossary_page_does_not_inline_examples(gloss_client: TestClient) -> None:
    """Gate B1: the page render exposes the lazy button + empty slot, no examples."""
    name = _name(gloss_client)
    page = gloss_client.get(f"/ui/projects/{name}/glossary").text
    assert "glossary/examples?source=" in page  # the lazy trigger exists
    assert 'class="cand-examples"' in page  # the (empty) slot exists
    # The example fragment marker is only emitted by the lazy endpoint, never on render.
    assert "Example sentences using" not in page


def test_examples_fragment_returns_source_sentences(gloss_client: TestClient) -> None:
    name = _name(gloss_client)
    cands = _candidates(gloss_client, name)
    source = cands[0]["source"]

    frag = gloss_client.get(
        f"/ui/projects/{name}/glossary/examples", params={"source": source}
    )
    assert frag.status_code == 200
    assert source in frag.text
    assert "Example sentences using" in frag.text


def test_examples_fragment_unknown_source_is_empty_not_error(gloss_client: TestClient) -> None:
    name = _name(gloss_client)
    frag = gloss_client.get(
        f"/ui/projects/{name}/glossary/examples", params={"source": "存在しない語句XYZ"}
    )
    assert frag.status_code == 200
    assert "No source sentences found" in frag.text
