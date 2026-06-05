"""QA report UI pages (Stage B4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import weaver.api.routers.ui_qa as ui_qa
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


def _ids_and_segments(database_path: Path) -> tuple[str, int, list[tuple[str, str]]]:
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
def ctx(tmp_path: Path) -> tuple[TestClient, str, int]:
    # "issues": one translated, one failed, the rest pending.
    issues_src = tmp_path / "issues.txt"
    issues_src.write_text(SOURCE_TXT, encoding="utf-8")
    issues = initialize_project(issues_src, cwd=tmp_path, provider="fake")
    chapter_id, volume_id, segments = _ids_and_segments(issues.database_path)
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

    # "clean": every segment translated with valid English.
    clean_src = tmp_path / "clean.txt"
    clean_src.write_text(SOURCE_TXT, encoding="utf-8")
    clean = initialize_project(clean_src, cwd=tmp_path, provider="fake")
    with connect_database(clean.database_path) as connection, transaction(connection):
        for index, (segment_id, source_hash) in enumerate(
            _ids_and_segments(clean.database_path)[2]
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

    return TestClient(create_api_app(tmp_path)), chapter_id, volume_id


def test_clean_report_renders_empty_state(ctx) -> None:
    client, _, _ = ctx
    response = client.get("/ui/projects/clean/qa")
    assert response.status_code == 200
    body = response.text
    assert "No QA issues found" in body
    assert ">Clean<" in body


def test_novel_report_renders_counts_issues_and_chapter_links(ctx) -> None:
    client, chapter_id, _ = ctx
    response = client.get("/ui/projects/issues/qa")
    assert response.status_code == 200
    body = response.text
    assert "failed_segment" in body  # a critical rule
    assert ">Errors<" in body  # badge label
    # project QA page links to the affected chapter's QA + its workspace
    assert f"/ui/projects/issues/chapters/{chapter_id}/qa" in body
    assert f'/ui/projects/issues/chapters/{chapter_id}"' in body


def test_chapter_report_links_back_to_workspace(ctx) -> None:
    client, chapter_id, _ = ctx
    response = client.get(f"/ui/projects/issues/chapters/{chapter_id}/qa")
    assert response.status_code == 200
    body = response.text
    assert "Back to workspace" in body
    assert f'href="/ui/projects/issues/chapters/{chapter_id}"' in body


def test_volume_report_renders(ctx) -> None:
    client, _, volume_id = ctx
    response = client.get(f"/ui/projects/issues/volumes/{volume_id}/qa")
    assert response.status_code == 200
    assert "Issues" in response.text


def test_severity_filter_narrows_issues(ctx) -> None:
    client, chapter_id, _ = ctx
    response = client.get(f"/ui/projects/issues/chapters/{chapter_id}/qa?severity=critical")
    assert response.status_code == 200
    body = response.text
    assert "failed_segment" in body  # critical kept
    assert "untranslated_segment" not in body  # warning filtered out


def test_project_and_workspace_link_to_qa(ctx) -> None:
    client, chapter_id, _ = ctx
    project_page = client.get("/ui/projects/issues").text
    assert "/ui/projects/issues/qa" in project_page
    workspace_page = client.get(f"/ui/projects/issues/chapters/{chapter_id}").text
    assert f"/ui/projects/issues/chapters/{chapter_id}/qa" in workspace_page


def test_unknown_targets_return_404(ctx) -> None:
    client, _, _ = ctx
    assert client.get("/ui/projects/ghost/qa").status_code == 404
    assert client.get("/ui/projects/issues/volumes/999999/qa").status_code == 404
    assert client.get("/ui/projects/issues/chapters/no-such-chapter/qa").status_code == 404


def test_tree_render_does_not_run_qa(ctx, monkeypatch) -> None:
    client, _, _ = ctx
    calls: list[str] = []
    monkeypatch.setattr(ui_qa, "analyze_novel", lambda *a, **k: calls.append("novel"))
    monkeypatch.setattr(ui_qa, "analyze_volume", lambda *a, **k: calls.append("volume"))
    monkeypatch.setattr(ui_qa, "analyze_chapter", lambda *a, **k: calls.append("chapter"))

    assert client.get("/ui").status_code == 200
    assert client.get("/ui/projects/issues").status_code == 200

    assert calls == []


def test_project_tree_has_badge_slots_and_button(ctx) -> None:
    client, chapter_id, volume_id = ctx
    page = client.get("/ui/projects/issues").text
    assert "Load QA badges" in page
    assert "/ui/projects/issues/qa/tree-badges" in page
    assert f'id="qa-badge-ch-{chapter_id}"' in page
    assert f'id="qa-badge-vol-{volume_id}"' in page


def test_tree_badges_lazy_loads_and_runs_qa_once(ctx, monkeypatch) -> None:
    client, chapter_id, volume_id = ctx
    calls = {"n": 0}
    real = ui_qa.analyze_novel

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(ui_qa, "analyze_novel", counting)

    # Rendering the tree triggers no QA …
    assert client.get("/ui/projects/issues").status_code == 200
    assert calls["n"] == 0

    # … but explicitly loading badges runs the novel QA exactly once and returns
    # out-of-band spans targeting the tree slots.
    badges = client.get("/ui/projects/issues/qa/tree-badges")
    assert badges.status_code == 200
    assert calls["n"] == 1
    body = badges.text
    assert 'hx-swap-oob="true"' in body
    assert f'id="qa-badge-ch-{chapter_id}"' in body
    assert f'id="qa-badge-vol-{volume_id}"' in body
    assert ">Errors<" in body  # the "issues" project has a failed segment
    assert "QA badges loaded" in body


def test_tree_badges_missing_project_is_non_fatal(ctx) -> None:
    client, _, _ = ctx
    response = client.get("/ui/projects/ghost/qa/tree-badges")
    assert response.status_code == 200
    assert "No project named" in response.text
    assert 'hx-swap-oob="true"' not in response.text
