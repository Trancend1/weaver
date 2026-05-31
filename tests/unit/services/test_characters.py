"""Character database service tests (Sprint 5B)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import CharacterNotFoundError
from weaver.services.characters import add_character, delete, list_all, update_character
from weaver.services.project import initialize_project

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB_A = FIXTURES / "aozora_sample.epub"


def test_add_list_update_delete_roundtrip(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")

    add_character(
        init.project_toml,
        jp_name="エリナ",
        en_name="Elina",
        gender="Female",
        role="Main Heroine",
        notes="protagonist",
        cwd=tmp_path,
    )
    chars = list_all(init.project_toml, cwd=tmp_path)
    assert [c.jp_name for c in chars] == ["エリナ"]
    assert chars[0].en_name == "Elina"
    assert chars[0].gender == "Female"
    assert chars[0].role == "Main Heroine"

    update_character(init.project_toml, jp_name="エリナ", en_name="Erina", cwd=tmp_path)
    assert list_all(init.project_toml, cwd=tmp_path)[0].en_name == "Erina"

    delete(init.project_toml, jp_name="エリナ", cwd=tmp_path)
    assert list_all(init.project_toml, cwd=tmp_path) == ()


def test_add_same_jp_name_upserts(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    add_character(init.project_toml, jp_name="魔王", en_name="Demon King", cwd=tmp_path)
    add_character(init.project_toml, jp_name="魔王", en_name="Demon Lord", cwd=tmp_path)
    chars = list_all(init.project_toml, cwd=tmp_path)
    assert len(chars) == 1
    assert chars[0].en_name == "Demon Lord"


def test_optional_fields_default_none(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    add_character(init.project_toml, jp_name="猫", en_name="Cat", cwd=tmp_path)
    char = list_all(init.project_toml, cwd=tmp_path)[0]
    assert char.gender is None
    assert char.role is None
    assert char.notes is None


def test_update_missing_raises(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    with pytest.raises(CharacterNotFoundError):
        update_character(init.project_toml, jp_name="未登録", en_name="x", cwd=tmp_path)


def test_delete_missing_raises(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    with pytest.raises(CharacterNotFoundError):
        delete(init.project_toml, jp_name="未登録", cwd=tmp_path)


def test_empty_names_rejected(tmp_path) -> None:
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    with pytest.raises(ValueError):
        add_character(init.project_toml, jp_name="  ", en_name="x", cwd=tmp_path)
    with pytest.raises(ValueError):
        add_character(init.project_toml, jp_name="猫", en_name="  ", cwd=tmp_path)
