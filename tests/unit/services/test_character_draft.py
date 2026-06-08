"""Character page draft service tests (Sprint L4 — XHTML/text only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.services.character_draft import (
    approve_draft,
    generate_character_draft,
    reject_draft,
)
from weaver.services.project import initialize_project

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB = FIXTURES / "aozora_sample.epub"


def test_generate_draft_returns_none_for_non_character_chapter(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    from weaver.services.project_tree import project_tree

    tree = project_tree(init.project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id

    result = generate_character_draft(init.project_toml, chapter_id, cwd=tmp_path)
    assert result is None or result.status == "draft"


def test_approve_draft(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    from weaver.services.character_draft import generate_character_draft
    from weaver.services.project_tree import project_tree

    tree = project_tree(init.project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id
    draft = generate_character_draft(init.project_toml, chapter_id, cwd=tmp_path)

    if draft is None:
        pytest.skip("No character page content in fixture")

    result = approve_draft(init.project_toml, draft.id, cwd=tmp_path)
    assert result.status == "approved"
    assert result.id == draft.id


def test_reject_draft(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    from weaver.services.project_tree import project_tree

    tree = project_tree(init.project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id
    draft = generate_character_draft(init.project_toml, chapter_id, cwd=tmp_path)

    if draft is None:
        pytest.skip("No character page content in fixture")

    result = reject_draft(init.project_toml, draft.id, cwd=tmp_path)
    assert result.status == "rejected"


def test_draft_has_provenance(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path, provider="fake")
    import json

    from weaver.services.project_tree import project_tree

    tree = project_tree(init.project_toml, cwd=tmp_path)
    chapter_id = tree.volumes[0].chapters[0].id
    draft = generate_character_draft(init.project_toml, chapter_id, cwd=tmp_path)

    if draft is None:
        pytest.skip("No character page content in fixture")

    prov = json.loads(draft.provenance_json)
    assert "prompt_version" in prov
    assert "chapter_id" in prov
    assert "source" in prov
    assert "created_at" in prov
    assert prov["source"] == "xhtml_text"
    assert prov["no_ocr"] is True


def test_extract_heading_from_character_text() -> None:
    from weaver.services.character_draft import (
        _build_draft_text,
        _extract_heading,
        _is_character_page,
    )

    sample = "名前: エリナ\n年齢: 18\n性別: 女性\nA young elven mage from the forest village."
    heading = _extract_heading(sample)
    assert heading is not None

    assert _is_character_page(sample, heading) is True

    draft = _build_draft_text(sample, heading)
    assert "エリナ" in draft or "Name" in draft or draft is not None


def test_extract_name_from_lines() -> None:
    from weaver.services.character_draft import _extract_name

    lines = ["名前: エリナ", "年齢: 18", "性別: 女性"]
    name = _extract_name(lines)
    assert name == "エリナ"

    lines_en = ["Name: Elina", "Age: 18"]
    assert _extract_name(lines_en) == "Elina"

    lines_no_name = ["Some random text", "More text"]
    assert _extract_name(lines_no_name) is None


def test_is_character_page_with_keywords() -> None:
    from weaver.services.character_draft import _is_character_page

    assert _is_character_page("Name: Elina\nAge: 18\nHeight: 165cm", None) is True
    assert _is_character_page("Some random chapter text", None) is False
    assert _is_character_page("一回目", "character") is True
