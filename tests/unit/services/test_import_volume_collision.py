"""Regression: importing the same source twice must not re-parent chapters.

Before Stage 11B-1.5, chapter/segment ids were content-derived but not
volume-scoped, so importing a source whose chapters collide with an existing
volume's re-parented the first volume's rows (it dropped to 0 chapters). Ids are
now scoped per volume at every read→persist boundary.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from weaver.core.ir import scope_document_to_volume
from weaver.core.segment import scope_id_to_volume
from weaver.readers import read_source
from weaver.services.batch_translate import prepare_batch_translation, run_batch_translation
from weaver.services.export_book import export_novel
from weaver.services.import_source import import_volume
from weaver.services.project import initialize_project
from weaver.services.project_tree import project_tree

FIXTURE_EPUB = Path(__file__).parent.parent.parent / "fixtures" / "aozora_sample.epub"


def _set_fake_provider(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = "deepseek"', 'type = "fake"')
    project_toml.write_text(text, encoding="utf-8")


# --- core scoping primitives ------------------------------------------------


def test_scope_id_is_deterministic_and_volume_unique() -> None:
    assert scope_id_to_volume(1, "abc") == scope_id_to_volume(1, "abc")
    assert scope_id_to_volume(1, "abc") != scope_id_to_volume(2, "abc")
    # 16-hex format preserved
    assert len(scope_id_to_volume(1, "abc")) == 16


def test_scope_document_distinct_per_volume_preserves_content() -> None:
    document = read_source(FIXTURE_EPUB)
    a = scope_document_to_volume(document, 1)
    b = scope_document_to_volume(document, 2)
    a_ids = {block.id for ch in a.chapters for block in ch.blocks}
    b_ids = {block.id for ch in b.chapters for block in ch.blocks}
    assert a_ids.isdisjoint(b_ids)  # no shared ids across volumes
    # block back-reference matches its (scoped) chapter; text unchanged
    for ch in a.chapters:
        for block in ch.blocks:
            assert block.chapter_id == ch.id
    assert [b.source_text for ch in a.chapters for b in ch.blocks] == [
        b.source_text for ch in document.chapters for b in ch.blocks
    ]


# --- duplicate import -------------------------------------------------------


def test_duplicate_import_keeps_both_volumes_chapters(tmp_path: Path) -> None:
    res = initialize_project(FIXTURE_EPUB, cwd=tmp_path)
    toml = Path(res.project_toml)

    before = project_tree(toml, cwd=tmp_path)
    assert [(v.chapter_count, v.segment_count) for v in before.volumes] == [(2, 6)]

    import_volume(toml, FIXTURE_EPUB, cwd=tmp_path)

    after = project_tree(toml, cwd=tmp_path)
    # both volumes keep their own chapters/segments — no re-parenting
    assert [(v.chapter_count, v.segment_count) for v in after.volumes] == [(2, 6), (2, 6)]
    # the two volumes own disjoint chapter ids
    ids_v1 = {c.id for c in after.volumes[0].chapters}
    ids_v2 = {c.id for c in after.volumes[1].chapters}
    assert ids_v1 and ids_v2 and ids_v1.isdisjoint(ids_v2)


def test_translate_and_export_work_on_both_duplicate_volumes(tmp_path: Path) -> None:
    res = initialize_project(FIXTURE_EPUB, cwd=tmp_path)
    toml = Path(res.project_toml)
    _set_fake_provider(toml)
    import_volume(toml, FIXTURE_EPUB, cwd=tmp_path)

    # Volume-aware (cockpit) batch translate over the whole novel — DB-text based,
    # so it covers both volumes' chapters via their distinct volume-scoped ids.
    plan = prepare_batch_translation(toml, scope="novel", cwd=tmp_path)
    result = run_batch_translation(plan)
    assert result.chapters_total == 4  # 2 volumes x 2 chapters
    assert result.translated > 0
    assert result.failed == 0

    # Volume-aware export writes one artifact per volume; each carries translations
    # (proves the EPUB write-back joins re-read source ids to scoped stored ids).
    export = export_novel(toml, target="epub", cwd=tmp_path)
    assert export.volumes_exported == 2
    assert len(export.artifacts) == 2
    for artifact in export.artifacts:
        assert artifact.output_path.exists()
        assert artifact.translated_segments > 0


def test_project_toml_is_valid_after_import(tmp_path: Path) -> None:
    res = initialize_project(FIXTURE_EPUB, cwd=tmp_path)
    toml = Path(res.project_toml)
    import_volume(toml, FIXTURE_EPUB, cwd=tmp_path)
    # sanity: project.toml still parses (no collision corruption)
    assert tomllib.loads(toml.read_text(encoding="utf-8"))["project"]["name"]
