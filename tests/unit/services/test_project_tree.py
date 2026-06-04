"""Project tree read-model tests (Sprint 1c)."""

from __future__ import annotations

from pathlib import Path

from weaver.services.import_source import import_volume
from weaver.services.project import initialize_project
from weaver.services.project_tree import project_tree

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB = FIXTURES / "aozora_sample.epub"


def test_project_tree_lists_volumes_with_chapters(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    txt = tmp_path / "vol2.txt"
    txt.write_text("第一章 はじまり\n本文。\n", encoding="utf-8")
    import_volume(init.project_toml, txt, cwd=tmp_path)

    tree = project_tree(init.project_toml, cwd=tmp_path)

    assert tree.project_name == "aozora_sample"
    assert [v.source_format for v in tree.volumes] == ["epub", "txt"]
    assert [v.volume_order for v in tree.volumes] == [0, 1]
    assert tree.volumes[0].chapter_count > 0
    assert tree.volumes[0].chapters[0].segment_count >= 1
    # nothing translated yet
    assert all(c.translated_count == 0 for v in tree.volumes for c in v.chapters)
    assert all(c.done_count == 0 for v in tree.volumes for c in v.chapters)


def test_done_count_includes_manual_edits(tmp_path) -> None:
    from weaver.services.chapter_workspace import chapter_workspace
    from weaver.services.workspace_edit import save_segment_translation

    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    chapter = project_tree(init.project_toml, cwd=tmp_path).volumes[0].chapters[0]
    assert chapter.done_count == 0

    ws = chapter_workspace(init.project_toml, chapter.id, cwd=tmp_path)
    save_segment_translation(
        init.project_toml, chapter.id, ws.segments[0].id, "MANUAL EN", cwd=tmp_path
    )

    refreshed = next(
        c
        for v in project_tree(init.project_toml, cwd=tmp_path).volumes
        for c in v.chapters
        if c.id == chapter.id
    )
    # a manual edit counts as "done" but not as auto-"translated"
    assert refreshed.done_count == 1
    assert refreshed.translated_count == 0
