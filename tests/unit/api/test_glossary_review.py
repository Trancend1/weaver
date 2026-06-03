"""Tests for the FastAPI glossary candidate-review API (Sprint 10D)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app


@pytest.fixture
def review_client(tmp_path: Path) -> TestClient:
    """An initialised project; the fixture EPUB yields pending candidates."""
    from weaver.services.project import initialize_project

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path)
    return TestClient(create_api_app(tmp_path))


def _name(client: TestClient) -> str:
    return client.get("/projects").json()["projects"][0]["name"]


def _first_candidate_id(client: TestClient, name: str) -> int:
    page = client.get(f"/projects/{name}/glossary/candidates").json()
    if not page["candidates"]:
        pytest.skip("fixture produced no glossary candidates")
    return page["candidates"][0]["id"]


# --- list -------------------------------------------------------------------


def test_list_candidates_shape(review_client: TestClient) -> None:
    name = _name(review_client)
    body = review_client.get(f"/projects/{name}/glossary/candidates").json()
    assert {"candidates", "total_pending", "offset", "limit", "find", "counts"} <= body.keys()
    assert {"pending", "approved", "rejected"} <= body["counts"].keys()
    assert body["counts"]["pending"] == body["total_pending"]


def test_list_candidates_pagination_params(review_client: TestClient) -> None:
    name = _name(review_client)
    body = review_client.get(
        f"/projects/{name}/glossary/candidates", params={"offset": 0, "limit": 1}
    ).json()
    assert body["limit"] == 1
    assert len(body["candidates"]) <= 1


def test_list_candidates_unknown_project_404(review_client: TestClient) -> None:
    assert review_client.get("/projects/ghost/glossary/candidates").status_code == 404


# --- actions ----------------------------------------------------------------


def test_approve_moves_pending_to_approved(review_client: TestClient) -> None:
    name = _name(review_client)
    cid = _first_candidate_id(review_client, name)
    before = review_client.get(f"/projects/{name}/glossary/candidates").json()["counts"]

    r = review_client.post(f"/projects/{name}/glossary/candidates/{cid}/approve")
    assert r.status_code == 200
    body = r.json()
    assert body["candidate_id"] == cid
    assert body["action"] == "approve"
    assert body["counts"]["pending"] == before["pending"] - 1
    assert body["counts"]["approved"] == before["approved"] + 1

    # approved term landed in the SAME glossary_terms table (direct CRUD reads it)
    terms = review_client.get(f"/projects/{name}/glossary").json()["terms"]
    assert any(t["source"] for t in terms)


def test_edit_then_approve(review_client: TestClient) -> None:
    name = _name(review_client)
    cid = _first_candidate_id(review_client, name)
    r = review_client.post(
        f"/projects/{name}/glossary/candidates/{cid}/edit",
        json={"target": "Edited Term", "notes": "n"},
    )
    assert r.status_code == 200
    assert r.json()["action"] == "edit"
    terms = review_client.get(f"/projects/{name}/glossary").json()["terms"]
    assert any(t["target"] == "Edited Term" for t in terms)


def test_edit_empty_target_422(review_client: TestClient) -> None:
    name = _name(review_client)
    cid = _first_candidate_id(review_client, name)
    r = review_client.post(
        f"/projects/{name}/glossary/candidates/{cid}/edit", json={"target": "  "}
    )
    assert r.status_code == 422


def test_reject_moves_pending_to_rejected(review_client: TestClient) -> None:
    name = _name(review_client)
    cid = _first_candidate_id(review_client, name)
    before = review_client.get(f"/projects/{name}/glossary/candidates").json()["counts"]
    r = review_client.post(f"/projects/{name}/glossary/candidates/{cid}/reject")
    assert r.status_code == 200
    assert r.json()["counts"]["rejected"] == before["rejected"] + 1


def test_action_unknown_candidate_404(review_client: TestClient) -> None:
    name = _name(review_client)
    assert (
        review_client.post(f"/projects/{name}/glossary/candidates/999999/approve").status_code
        == 404
    )


# --- conflicts + diff -------------------------------------------------------


def test_conflicts_ok(review_client: TestClient) -> None:
    name = _name(review_client)
    r = review_client.get(f"/projects/{name}/glossary/conflicts")
    assert r.status_code == 200
    assert "conflicts" in r.json()


def test_diff_ok(review_client: TestClient) -> None:
    name = _name(review_client)
    r = review_client.get(f"/projects/{name}/glossary/diff", params={"a": 1, "b": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["chapter_a"] == 1 and body["chapter_b"] == 1
    # a chapter vs itself: nothing is exclusive to either side
    assert body["only_in_a"] == [] and body["only_in_b"] == []


def test_diff_out_of_range_422(review_client: TestClient) -> None:
    name = _name(review_client)
    r = review_client.get(f"/projects/{name}/glossary/diff", params={"a": 1, "b": 99999})
    assert r.status_code == 422


def test_diff_missing_params_422(review_client: TestClient) -> None:
    name = _name(review_client)
    assert review_client.get(f"/projects/{name}/glossary/diff").status_code == 422


def test_does_not_shadow_direct_crud(review_client: TestClient) -> None:
    """Direct glossary CRUD list endpoint still resolves (not captured by review routes)."""
    name = _name(review_client)
    assert review_client.get(f"/projects/{name}/glossary").status_code == 200
