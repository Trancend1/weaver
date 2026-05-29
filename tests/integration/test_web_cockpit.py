"""Integration tests for the web cockpit app + serve command (Phase 12a/12b)."""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from weaver.cli.main import app
from weaver.services.project import initialize_project
from weaver.storage.db import connect_readonly_database
from weaver.web.app import create_app
from weaver.web.job_manager import JobManager

FIXTURE_EPUB = Path(__file__).parents[1] / "fixtures" / "aozora_sample.epub"


def _set_fake_provider(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    text = text.replace('model = "fake-1"', 'model = "fake-1"\npattern = "EN: {source}"')
    project_toml.write_text(text, encoding="utf-8")


@pytest.fixture()
def cockpit(tmp_path: Path):
    initialize_project(FIXTURE_EPUB, cwd=tmp_path)
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    _set_fake_provider(project_toml)
    flask_app = create_app(tmp_path, job_manager=JobManager())
    return flask_app.test_client()


@pytest.fixture()
def web_env(tmp_path: Path):
    """Return (client, books_dir) for tests needing filesystem assertions."""

    initialize_project(FIXTURE_EPUB, cwd=tmp_path)
    project_toml = tmp_path / ".weaver" / "aozora_sample" / "project.toml"
    _set_fake_provider(project_toml)
    flask_app = create_app(tmp_path, job_manager=JobManager())
    return flask_app.test_client(), tmp_path


def test_dashboard_lists_discovered_project(cockpit) -> None:
    response = cockpit.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "aozora_sample" in body


def test_cockpit_view_shows_status(cockpit) -> None:
    response = cockpit.get("/project/aozora_sample")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Segments" in body
    assert "fake" in body


def test_cockpit_missing_project_404(cockpit) -> None:
    assert cockpit.get("/project/nope").status_code == 404


def test_translate_start_redirects_to_cockpit(cockpit) -> None:
    response = cockpit.post("/project/aozora_sample/translate")
    assert response.status_code == 302
    assert "/project/aozora_sample" in response.headers["Location"]


def test_translate_progress_streams_to_completion(cockpit) -> None:
    cockpit.post("/project/aozora_sample/translate", data={"first_n": "3"})
    response = cockpit.get("/project/aozora_sample/events")
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    body = response.get_data(as_text=True)
    assert "event: progress" in body
    assert "event: done" in body


def test_events_404_when_no_active_job(cockpit) -> None:
    assert cockpit.get("/project/aozora_sample/events").status_code == 404


def test_serve_command_help_mentions_loopback() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "127.0.0.1" in result.output


# --- Phase 12b: write actions -------------------------------------------------


def test_new_page_renders(cockpit) -> None:
    response = cockpit.get("/new")
    assert response.status_code == 200
    assert "New project" in response.get_data(as_text=True)


def test_api_browse_lists_epub(web_env) -> None:
    client, books_dir = web_env
    shutil.copy(FIXTURE_EPUB, books_dir / "book.epub")
    response = client.get("/api/browse?dir=")
    assert response.status_code == 200
    payload = response.get_json()
    names = {e["name"] for e in payload["entries"]}
    assert "book.epub" in names
    assert payload["parent"] is None


def test_api_browse_rejects_traversal(cockpit) -> None:
    assert cockpit.get("/api/browse?dir=..").status_code == 400


def test_new_init_from_browsed_path_sets_provider(web_env) -> None:
    client, books_dir = web_env
    shutil.copy(FIXTURE_EPUB, books_dir / "book.epub")
    response = client.post("/new/init", data={"epub_path": "book.epub", "provider": "fake"})
    assert response.status_code == 302
    assert "/project/book" in response.headers["Location"]
    toml = (books_dir / ".weaver" / "book" / "project.toml").read_text(encoding="utf-8")
    assert 'type = "fake"' in toml  # PP2: wizard/web provider no longer discarded


def test_new_init_default_provider_has_no_stray_base_url(web_env) -> None:
    client, books_dir = web_env
    shutil.copy(FIXTURE_EPUB, books_dir / "book.epub")
    client.post("/new/init", data={"epub_path": "book.epub"})
    toml = (books_dir / ".weaver" / "book" / "project.toml").read_text(encoding="utf-8")
    assert 'type = "deepseek"' in toml
    assert "base_url" not in toml  # PP2: stray ollama base_url removed


def test_new_init_from_upload(web_env) -> None:
    client, books_dir = web_env
    data = {
        "provider": "fake",
        "epub_file": (io.BytesIO(FIXTURE_EPUB.read_bytes()), "uploaded.epub"),
    }
    response = client.post("/new/init", data=data, content_type="multipart/form-data")
    assert response.status_code == 302
    assert (books_dir / ".weaver" / "_uploads" / "uploaded.epub").is_file()
    assert (books_dir / ".weaver" / "uploaded" / "project.toml").is_file()


def test_config_updates_provider_project_scope(web_env) -> None:
    client, books_dir = web_env
    response = client.post(
        "/project/aozora_sample/config",
        data={"provider_type": "gemini", "model": "gemini-1.5-flash", "scope": "project"},
    )
    assert response.status_code == 302
    toml = (books_dir / ".weaver" / "aozora_sample" / "project.toml").read_text(encoding="utf-8")
    assert 'type = "gemini"' in toml
    assert 'model = "gemini-1.5-flash"' in toml


def test_config_custom_provider_writes_secret_not_config(web_env, tmp_path, monkeypatch) -> None:
    from weaver.core.secret_store import load_secrets

    client, books_dir = web_env
    secrets = tmp_path / "secrets.toml"
    monkeypatch.setenv("WEAVER_SECRETS_PATH", str(secrets))

    response = client.post(
        "/project/aozora_sample/config",
        data={
            "provider_type": "custom",
            "model": "some-model",
            "base_url": "https://api.example.com/v1",
            "api_key_env": "MY_API_KEY",
            "api_key": "sk-secret-value",
            "scope": "project",
        },
    )
    assert response.status_code == 302

    toml = _project_toml(books_dir).read_text(encoding="utf-8")
    assert 'type = "custom"' in toml
    assert 'api_key_env = "MY_API_KEY"' in toml
    assert "sk-secret-value" not in toml  # key value never in config

    assert load_secrets(secrets)["MY_API_KEY"] == "sk-secret-value"  # only in store
    page = client.get("/project/aozora_sample").get_data(as_text=True)
    assert "sk-secret-value" not in page  # never rendered


def test_export_markdown_redirects(web_env) -> None:
    client, books_dir = web_env
    client.post("/project/aozora_sample/translate", data={"first_n": "2"})
    client.get("/project/aozora_sample/events")  # drain job to completion
    response = client.post("/project/aozora_sample/export", data={"mode": "markdown"})
    assert response.status_code == 302
    assert "exported=markdown" in response.headers["Location"]
    assert (books_dir / ".weaver" / "aozora_sample" / "output" / "markdown" / "review.md").is_file()


def test_translate_stop_redirects_when_idle(cockpit) -> None:
    response = cockpit.post("/project/aozora_sample/translate/stop")
    assert response.status_code == 302
    assert "/project/aozora_sample" in response.headers["Location"]


# --- Phase 12c: glossary review UI -------------------------------------------


def _project_toml(books_dir: Path) -> Path:
    return books_dir / ".weaver" / "aozora_sample" / "project.toml"


def test_glossary_page_renders(cockpit) -> None:
    response = cockpit.get("/project/aozora_sample/glossary")
    assert response.status_code == 200
    assert "Glossary review" in response.get_data(as_text=True)


def test_glossary_approve_decrements_pending(web_env) -> None:
    from weaver.services.glossary_review import list_pending

    client, books_dir = web_env
    project_toml = _project_toml(books_dir)
    before = list_pending(project_toml, cwd=books_dir, limit=100)
    candidate = before.items[0]

    response = client.post(
        f"/project/aozora_sample/glossary/{candidate.id}",
        data={"action": "approve", "offset": "0"},
    )
    assert response.status_code == 302
    after = list_pending(project_toml, cwd=books_dir, limit=100)
    assert after.total_pending == before.total_pending - 1


def test_glossary_find_filters(web_env) -> None:
    from weaver.services.glossary_review import list_pending

    client, books_dir = web_env
    project_toml = _project_toml(books_dir)
    candidate = list_pending(project_toml, cwd=books_dir, limit=1).items[0]
    needle = candidate.source[:1]

    response = client.get(f"/project/aozora_sample/glossary?find={needle}")
    assert response.status_code == 200
    assert "matching" in response.get_data(as_text=True)


def test_glossary_diff_renders(cockpit) -> None:
    response = cockpit.get("/project/aozora_sample/glossary?diff_a=1&diff_b=1")
    assert response.status_code == 200
    assert "In both" in response.get_data(as_text=True)


# --- Sprint 1c: project tree + multi-format import ---------------------------


def test_cockpit_shows_volume_tree(cockpit) -> None:
    response = cockpit.get("/project/aozora_sample")
    body = response.get_data(as_text=True)
    assert "Volumes" in body
    assert "[epub]" in body
    assert "Import volume" in body


def test_new_init_from_txt_upload_creates_novel(web_env) -> None:
    client, books_dir = web_env
    data = {
        "provider": "fake",
        "epub_file": (io.BytesIO("第一章 はじまり\n本文。\n".encode()), "story.txt"),
    }
    response = client.post("/new/init", data=data, content_type="multipart/form-data")
    assert response.status_code == 302
    assert "/project/story" in response.headers["Location"]
    assert (books_dir / ".weaver" / "story" / "project.toml").is_file()


def test_import_volume_route_adds_txt_volume(web_env) -> None:
    client, books_dir = web_env
    data = {"epub_file": (io.BytesIO("第二巻\n続き。\n".encode()), "vol2.txt")}
    response = client.post(
        "/project/aozora_sample/import", data=data, content_type="multipart/form-data"
    )
    assert response.status_code == 302
    assert "imported=vol2.txt" in response.headers["Location"]

    db_path = books_dir / ".weaver" / "aozora_sample" / "weaver.db"
    with connect_readonly_database(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) AS n FROM volumes").fetchone()["n"]
    assert count == 2


def test_import_volume_route_missing_project_404(cockpit) -> None:
    data = {"epub_file": (io.BytesIO(b"x"), "v.txt")}
    response = cockpit.post("/project/nope/import", data=data, content_type="multipart/form-data")
    assert response.status_code == 404


def test_api_browse_lists_txt_source(web_env) -> None:
    client, books_dir = web_env
    (books_dir / "extra.txt").write_text("本文。\n", encoding="utf-8")
    payload = client.get("/api/browse?dir=").get_json()
    entries = {e["name"]: e["kind"] for e in payload["entries"]}
    assert entries.get("extra.txt") == "txt"


def test_glossary_conflicts_surfaced(web_env) -> None:
    from weaver.storage.db import connect_database, transaction
    from weaver.storage.glossary import insert_glossary_candidate

    client, books_dir = web_env
    db_path = books_dir / ".weaver" / "aozora_sample" / "weaver.db"
    with connect_database(db_path) as connection, transaction(connection):
        project_id = connection.execute("SELECT id FROM projects LIMIT 1").fetchone()["id"]
        for target in ("Kai", "Kye"):
            insert_glossary_candidate(
                connection,
                project_id=project_id,
                source="カイ",
                target=target,
                category="katakana",
                notes=None,
                status="approved",
                frequency=2,
            )

    response = client.get("/project/aozora_sample/glossary")
    body = response.get_data(as_text=True)
    assert "Conflicts" in body
    assert "カイ" in body
