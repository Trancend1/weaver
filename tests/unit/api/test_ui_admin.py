"""Tests for the FastAPI consistency/admin UI (Stage 11C).

Glossary CRUD + candidate review, character DB, translation memory, provider/secret
config. The secret store and global config are isolated to tmp so no real
``~/.weaver`` files are touched and no real key can leak into assertions.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app


@pytest.fixture
def admin_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from weaver.services.project import initialize_project

    home = tmp_path / "home"
    (home / ".weaver").mkdir(parents=True)
    monkeypatch.setenv("WEAVER_SECRETS_PATH", str(home / ".weaver" / "secrets.toml"))
    monkeypatch.setattr(Path, "home", lambda: home)

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    init = initialize_project(epubs[0], cwd=tmp_path)
    toml = Path(init.project_toml)
    toml.write_text(
        toml.read_text(encoding="utf-8").replace('type = "deepseek"', 'type = "fake"'),
        encoding="utf-8",
    )
    return TestClient(create_api_app(tmp_path))


def _name(client: TestClient) -> str:
    return client.get("/projects").json()["projects"][0]["name"]


# --- glossary terms ---------------------------------------------------------


def test_glossary_add_edit_delete(admin_client: TestClient) -> None:
    name = _name(admin_client)
    assert admin_client.get(f"/ui/projects/{name}/glossary").status_code == 200

    add = admin_client.post(
        f"/ui/projects/{name}/glossary/terms", data={"source": "魔王", "target": "Demon Lord"}
    )
    assert add.status_code == 200 and "Demon Lord" in add.text

    edit = admin_client.post(
        f"/ui/projects/{name}/glossary/terms/魔王/update", data={"target": "Dark Lord"}
    )
    assert edit.status_code == 200 and "Dark Lord" in edit.text

    delete = admin_client.post(f"/ui/projects/{name}/glossary/terms/魔王/delete")
    assert delete.status_code == 200 and "Dark Lord" not in delete.text


def test_glossary_add_invalid_shows_error(admin_client: TestClient) -> None:
    name = _name(admin_client)
    r = admin_client.post(
        f"/ui/projects/{name}/glossary/terms", data={"source": "  ", "target": "x"}
    )
    assert r.status_code == 200
    assert "error" in r.text.lower()


# --- glossary candidate review ----------------------------------------------


def _candidate_ids(client: TestClient, name: str) -> list[int]:
    body = client.get(f"/projects/{name}/glossary/candidates").json()
    return [c["id"] for c in body["candidates"]]


def test_candidate_actions_are_unambiguous(admin_client: TestClient) -> None:
    name = _name(admin_client)
    page = admin_client.get(f"/ui/projects/{name}/glossary/candidates").text

    assert "Approve existing target" in page
    assert "Edit target" in page
    assert "Translate target with AI" in page
    assert "Edit + approve" not in page
    assert ">Approve</button>" not in page


def test_candidate_approve(admin_client: TestClient) -> None:
    name = _name(admin_client)
    ids = _candidate_ids(admin_client, name)
    if not ids:
        pytest.skip("fixture produced no glossary candidates")
    r = admin_client.post(
        f"/ui/projects/{name}/glossary/candidates/{ids[0]}/approve", data={"offset": "0"}
    )
    assert r.status_code == 200
    # approved term lands in the same glossary_terms table
    assert admin_client.get(f"/projects/{name}/glossary").json()["count"] >= 1


def test_candidate_edit_then_reject(admin_client: TestClient) -> None:
    name = _name(admin_client)
    ids = _candidate_ids(admin_client, name)
    if len(ids) < 2:
        pytest.skip("need two candidates")
    edited = admin_client.post(
        f"/ui/projects/{name}/glossary/candidates/{ids[0]}/edit",
        data={"target": "EditedTerm", "offset": "0"},
    )
    assert edited.status_code == 200
    rejected = admin_client.post(
        f"/ui/projects/{name}/glossary/candidates/{ids[1]}/reject", data={"offset": "0"}
    )
    assert rejected.status_code == 200


def test_candidate_ai_translate_skeleton_does_not_approve(admin_client: TestClient) -> None:
    name = _name(admin_client)
    ids = _candidate_ids(admin_client, name)
    if not ids:
        pytest.skip("fixture produced no glossary candidates")

    response = admin_client.post(
        f"/ui/projects/{name}/glossary/candidates/{ids[0]}/translate", data={"offset": "0"}
    )

    assert response.status_code == 200
    assert "not wired yet" in response.text
    remaining_ids = _candidate_ids(admin_client, name)
    assert ids[0] in remaining_ids


def test_candidate_unknown_404(admin_client: TestClient) -> None:
    name = _name(admin_client)
    r = admin_client.post(
        f"/ui/projects/{name}/glossary/candidates/999999/approve", data={"offset": "0"}
    )
    assert r.status_code == 404


def test_conflicts_and_diff_render(admin_client: TestClient) -> None:
    name = _name(admin_client)
    page = admin_client.get(f"/ui/projects/{name}/glossary").text
    assert "Conflicts" in page and "Coverage diff" in page
    diff = admin_client.get(f"/ui/projects/{name}/glossary/diff", params={"a": 1, "b": 2})
    assert diff.status_code == 200
    assert "Only in 1" in diff.text


# --- characters -------------------------------------------------------------


def test_characters_add_edit_delete(admin_client: TestClient) -> None:
    name = _name(admin_client)
    assert admin_client.get(f"/ui/projects/{name}/characters").status_code == 200

    add = admin_client.post(
        f"/ui/projects/{name}/characters", data={"jp_name": "エリナ", "en_name": "Elina"}
    )
    assert add.status_code == 200 and "Elina" in add.text

    edit = admin_client.post(
        f"/ui/projects/{name}/characters/エリナ/update",
        data={"en_name": "Erina", "role": "knight"},
    )
    assert edit.status_code == 200 and "Erina" in edit.text and "knight" in edit.text

    delete = admin_client.post(f"/ui/projects/{name}/characters/エリナ/delete")
    assert delete.status_code == 200 and "Erina" not in delete.text


def test_character_missing_fields_error(admin_client: TestClient) -> None:
    name = _name(admin_client)
    r = admin_client.post(f"/ui/projects/{name}/characters", data={"jp_name": "X", "en_name": "  "})
    assert r.status_code == 200
    assert "error" in r.text.lower()


# --- translation memory -----------------------------------------------------


def _translate_to_seed_tm(client: TestClient, name: str) -> None:
    cid = client.get(f"/projects/{name}/tree").json()["volumes"][0]["chapters"][0]["id"]
    client.post(f"/ui/projects/{name}/chapters/{cid}/translate")
    job_id = next(iter(client.app.state.jobs._jobs))  # type: ignore[attr-defined]
    for _ in range(200):
        if client.get(f"/projects/{name}/jobs/{job_id}").json()["status"] != "running":
            break
        time.sleep(0.02)


def test_memory_list_and_delete(admin_client: TestClient) -> None:
    name = _name(admin_client)
    assert admin_client.get(f"/ui/projects/{name}/memory").status_code == 200
    _translate_to_seed_tm(admin_client, name)

    overview = admin_client.get(f"/projects/{name}/memory").json()
    if overview["total_entries"] == 0:
        pytest.skip("no TM entries produced")
    source_hash = overview["entries"][0]["source_hash"]

    page = admin_client.get(f"/ui/projects/{name}/memory").text
    assert "entries" in page

    delete = admin_client.post(f"/ui/projects/{name}/memory/{source_hash}/delete")
    assert delete.status_code == 200
    after = admin_client.get(f"/projects/{name}/memory").json()["total_entries"]
    assert after == overview["total_entries"] - 1


def test_memory_delete_unknown_shows_error(admin_client: TestClient) -> None:
    name = _name(admin_client)
    r = admin_client.post(f"/ui/projects/{name}/memory/deadbeef/delete")
    assert r.status_code == 200
    assert "error" in r.text.lower()


# --- provider / secret config -----------------------------------------------


def test_config_page_and_save(admin_client: TestClient) -> None:
    name = _name(admin_client)
    assert admin_client.get("/ui/config").status_code == 200
    assert admin_client.get("/ui/config", params={"project": name}).status_code == 200

    r = admin_client.post(
        "/ui/config",
        data={"scope": "project", "project": name, "provider_type": "fake", "model": "fake-9"},
    )
    assert r.status_code == 200 and "Saved" in r.text
    # persisted
    view = admin_client.get(f"/config?project={name}").json()
    assert view["model"] == "fake-9"


def test_config_invalid_provider_error(admin_client: TestClient) -> None:
    name = _name(admin_client)
    r = admin_client.post(
        "/ui/config",
        data={"scope": "project", "project": name, "provider_type": "not-real"},
    )
    assert r.status_code == 200
    assert "error" in r.text.lower()


def test_secret_set_and_delete_without_exposing_value(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/ui/config/secrets", data={"env_name": "MY_KEY", "value": "sk-LEAKCHECK"}
    )
    assert r.status_code == 200
    assert "MY_KEY" in r.text
    assert "sk-LEAKCHECK" not in r.text  # value never rendered
    # and not in the page either
    assert "sk-LEAKCHECK" not in admin_client.get("/ui/config").text

    delete = admin_client.post("/ui/config/secrets/MY_KEY/delete")
    assert delete.status_code == 200
    assert "MY_KEY" not in delete.text


def test_secret_invalid_name_error(admin_client: TestClient) -> None:
    r = admin_client.post("/ui/config/secrets", data={"env_name": "bad name!", "value": "x"})
    assert r.status_code == 200
    assert "error" in r.text.lower()


# --- nav links --------------------------------------------------------------


def test_project_page_links_admin_sections(admin_client: TestClient) -> None:
    name = _name(admin_client)
    page = admin_client.get(f"/ui/projects/{name}").text
    assert f"/ui/projects/{name}/glossary" in page
    assert f"/ui/projects/{name}/characters" in page
    assert f"/ui/projects/{name}/memory" in page
    assert "/ui/config" in admin_client.get("/ui").text


# --- A2-5 admin usability ---------------------------------------------------


def test_memory_search_filters_entries(admin_client: TestClient) -> None:
    name = _name(admin_client)
    _translate_to_seed_tm(admin_client, name)
    overview = admin_client.get(f"/projects/{name}/memory").json()
    if overview["total_entries"] == 0:
        pytest.skip("no TM entries produced")

    needle = overview["entries"][0]["source_text"][:2]
    hit = admin_client.get(f"/ui/projects/{name}/memory/entries", params={"find": needle})
    assert hit.status_code == 200
    assert "matching" in hit.text  # the meta line shows a match count when filtering

    miss = admin_client.get(
        f"/ui/projects/{name}/memory/entries", params={"find": "ZZ_NO_SUCH_TEXT_QQ"}
    )
    assert miss.status_code == 200
    assert "No entries match" in miss.text


def test_candidate_search_param_is_echoed(admin_client: TestClient) -> None:
    name = _name(admin_client)
    r = admin_client.get(f"/ui/projects/{name}/glossary/candidates", params={"find": "zzz"})
    assert r.status_code == 200
    assert 'value="zzz"' in r.text  # the search box keeps the query


def test_config_and_new_expose_provider_selects(admin_client: TestClient) -> None:
    cfg = admin_client.get("/ui/config").text
    assert '<select name="provider_type"' in cfg
    assert ">fake<" in cfg  # a known provider type is offered as an option

    new = admin_client.get("/ui/new").text
    assert '<select name="provider"' in new
    assert ">fake<" in new
