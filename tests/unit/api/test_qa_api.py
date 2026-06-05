"""FastAPI QA report endpoints (Stage B3)."""

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


def _chapter_and_segments(database_path: Path) -> tuple[str, int, list[tuple[str, str]]]:
    with connect_readonly_database(database_path) as connection:
        volume_id = int(
            connection.execute("SELECT id FROM volumes ORDER BY volume_order").fetchone()["id"]
        )
        chapter_id = str(
            connection.execute("SELECT id FROM chapters ORDER BY spine_order").fetchone()["id"]
        )
        segments = [
            (str(row["id"]), str(row["source_hash"]))
            for row in connection.execute(
                "SELECT id, source_hash FROM segments WHERE chapter_id = ? ORDER BY block_order",
                (chapter_id,),
            ).fetchall()
        ]
    return chapter_id, volume_id, segments


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    # "issues" project: one translated, one failed, the rest pending.
    issues_src = tmp_path / "issues.txt"
    issues_src.write_text(SOURCE_TXT, encoding="utf-8")
    issues = initialize_project(issues_src, cwd=tmp_path, provider="fake")
    _, _, segments = _chapter_and_segments(issues.database_path)
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

    # "clean" project: every segment translated with valid English.
    clean_src = tmp_path / "clean.txt"
    clean_src.write_text(SOURCE_TXT, encoding="utf-8")
    clean = initialize_project(clean_src, cwd=tmp_path, provider="fake")
    with connect_database(clean.database_path) as connection, transaction(connection):
        for index, (segment_id, source_hash) in enumerate(
            _chapter_and_segments(clean.database_path)[2]
        ):
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


def _assert_counts_consistent(report: dict) -> None:
    assert (
        report["info_count"] + report["warning_count"] + report["critical_count"]
        == report["total_issues"]
    )
    assert len(report["issues"]) == report["total_issues"]
    assert sum(report["summary_by_category"].values()) == report["total_issues"]
    for issue in report["issues"]:
        assert issue["severity"] in {"info", "warning", "critical"}  # never "error"


def test_novel_qa_report(client: TestClient) -> None:
    response = client.get("/projects/issues/qa")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["schema_version"] == 2
    assert report["scope"] == "novel"
    assert report["critical_count"] >= 1  # the failed segment
    assert report["badge"] == "errors"
    assert len(report["summary_by_volume"]) == 1
    assert len(report["summary_by_chapter"]) >= 1
    _assert_counts_consistent(report)


def test_volume_qa_report(client: TestClient) -> None:
    # The novel report's per-volume roll-up gives us a real volume id.
    vid = client.get("/projects/issues/qa").json()["summary_by_volume"][0]["id"]

    response = client.get(f"/projects/issues/volumes/{vid}/qa")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["scope"] == "volume"
    assert report["scope_id"] == vid
    assert report["summary_by_volume"] == []
    assert len(report["summary_by_chapter"]) >= 1
    assert report["badge"] == "errors"
    _assert_counts_consistent(report)


def test_chapter_qa_report(client: TestClient) -> None:
    chapter_id = client.get("/projects/issues/qa").json()["summary_by_chapter"][0]["id"]

    response = client.get(f"/projects/issues/chapters/{chapter_id}/qa")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["scope"] == "chapter"
    assert report["scope_id"] == chapter_id
    assert report["summary_by_chapter"] == []
    assert report["summary_by_volume"] == []
    _assert_counts_consistent(report)


def test_clean_report_has_no_issues(client: TestClient) -> None:
    report = client.get("/projects/clean/qa").json()
    assert report["total_issues"] == 0
    assert report["info_count"] == 0
    assert report["warning_count"] == 0
    assert report["critical_count"] == 0
    assert report["badge"] == "clean"
    assert report["issues"] == []


def test_unknown_project_returns_404(client: TestClient) -> None:
    assert client.get("/projects/ghost/qa").status_code == 404
    assert client.get("/projects/ghost/volumes/1/qa").status_code == 404
    assert client.get("/projects/ghost/chapters/nope/qa").status_code == 404


def test_unknown_volume_and_chapter_return_404(client: TestClient) -> None:
    assert client.get("/projects/issues/volumes/999999/qa").status_code == 404
    assert client.get("/projects/issues/chapters/no-such-chapter/qa").status_code == 404


def test_non_integer_volume_id_returns_422(client: TestClient) -> None:
    assert client.get("/projects/issues/volumes/not-an-int/qa").status_code == 422
