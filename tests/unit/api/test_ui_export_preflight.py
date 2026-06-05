"""Advisory pre-export QA warning (Stage B5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weaver.api.app import create_api_app
from weaver.services.project import initialize_project
from weaver.storage.db import connect_database, connect_readonly_database, transaction
from weaver.storage.segments import update_segment_status
from weaver.storage.translations import record_translation

SOURCE_TXT = """第一章 テスト

最初の段落の説明文。

二番目の段落の説明文。

三番目の段落の説明文。

四番目の段落の説明文。

五番目の段落の説明文。

六番目の段落の説明文。
"""


def _segments(database_path: Path) -> list[tuple[str, str]]:
    with connect_readonly_database(database_path) as connection:
        chapter_id = str(
            connection.execute("SELECT id FROM chapters ORDER BY spine_order").fetchone()["id"]
        )
        return [
            (str(row["id"]), str(row["source_hash"]))
            for row in connection.execute(
                "SELECT id, source_hash FROM segments WHERE chapter_id = ? ORDER BY block_order",
                (chapter_id,),
            ).fetchall()
        ]


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    issues_src = tmp_path / "issues.txt"
    issues_src.write_text(SOURCE_TXT, encoding="utf-8")
    issues = initialize_project(issues_src, cwd=tmp_path, provider="fake")
    segments = _segments(issues.database_path)
    with connect_database(issues.database_path) as connection, transaction(connection):
        record_translation(
            connection,
            segment_id=segments[0][0],
            text="A clean English sentence.",
            source_hash=segments[0][1],
            provider="fake",
            model="fake",
        )
        update_segment_status(connection, segment_id=segments[0][0], status="translated")
        update_segment_status(connection, segment_id=segments[1][0], status="failed")

    clean_src = tmp_path / "clean.txt"
    clean_src.write_text(SOURCE_TXT, encoding="utf-8")
    clean = initialize_project(clean_src, cwd=tmp_path, provider="fake")
    with connect_database(clean.database_path) as connection, transaction(connection):
        for index, (segment_id, source_hash) in enumerate(_segments(clean.database_path)):
            record_translation(
                connection,
                segment_id=segment_id,
                text=f"A clean English sentence number {index}.",
                source_hash=source_hash,
                provider="fake",
                model="fake",
            )
            update_segment_status(connection, segment_id=segment_id, status="translated")

    return TestClient(create_api_app(tmp_path))


def test_preflight_clean_state(client: TestClient) -> None:
    response = client.get("/ui/projects/clean/export/preflight?target=epub")
    assert response.status_code == 200
    body = response.text
    assert "No QA issues found" in body
    assert ">Clean<" in body
    assert 'id="export-panel"' in body
    # the action still posts to the real export route
    assert 'hx-post="/ui/projects/clean/export"' in body
    assert ">Export<" in body  # clean → plain "Export"


def test_preflight_warning_state(client: TestClient) -> None:
    response = client.get("/ui/projects/issues/export/preflight?target=epub")
    assert response.status_code == 200
    body = response.text
    assert ">Errors<" in body  # badge
    assert "critical issue" in body
    assert "failed / stale" in body
    assert "Review QA report" in body
    assert "/ui/projects/issues/qa" in body
    assert "Export anyway" in body
    assert 'hx-post="/ui/projects/issues/export"' in body


def test_export_still_starts_after_warning(client: TestClient) -> None:
    # "Export anyway" posts to the unchanged export route — no hard block.
    response = client.post("/ui/projects/issues/export", data={"target": "epub"})
    assert response.status_code == 200
    assert 'id="export-panel"' in response.text


def test_qa_report_link_resolves(client: TestClient) -> None:
    assert client.get("/ui/projects/issues/qa").status_code == 200


def test_project_page_export_form_uses_preflight(client: TestClient) -> None:
    page = client.get("/ui/projects/issues").text
    assert "/ui/projects/issues/export/preflight" in page
    for target in ("epub", "txt", "html"):
        assert f'value="{target}"' in page


def test_preflight_missing_project_is_non_fatal(client: TestClient) -> None:
    # Even when QA can't run, the panel renders and still offers an export action.
    response = client.get("/ui/projects/ghost/export/preflight")
    assert response.status_code == 200
    assert "QA check unavailable" in response.text
    assert 'hx-post="/ui/projects/ghost/export"' in response.text
