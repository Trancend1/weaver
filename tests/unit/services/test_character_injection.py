"""Character context injection proof (Sprint 5C).

The real integration point is ``build_context().characters`` and the rendered
``<characters>`` prompt block. Also proves a managed character flows from the
character service through translation planning into the prompt.
"""

from __future__ import annotations

from pathlib import Path

from weaver.providers.prompts import render_user_message
from weaver.providers.types import CharacterContext
from weaver.services.characters import add_character
from weaver.services.project import initialize_project
from weaver.services.translation import build_context
from weaver.services.workspace_translate import prepare_chapter_translation

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_EPUB_A = FIXTURES / "aozora_sample.epub"


def test_matching_character_enters_context_and_prompt() -> None:
    """エリナ → Elina: matching character reaches context + rendered prompt."""
    context = build_context(
        normalized_source_text="その時、エリナが笑った。",
        glossary_terms=[],
        previous_segments=[],
        characters=[CharacterContext(jp_name="エリナ", en_name="Elina", role="Heroine")],
    )

    jp_names = [c.jp_name for c in context.characters]
    assert "エリナ" in jp_names

    rendered = render_user_message(context, source_text="その時、エリナが笑った。")
    assert "<characters>" in rendered
    assert "エリナ" in rendered
    assert "Elina" in rendered


def test_absent_character_filtered_out() -> None:
    """A character whose jp_name is absent from the segment is filtered out."""
    context = build_context(
        normalized_source_text="こんにちは。",
        glossary_terms=[],
        previous_segments=[],
        characters=[CharacterContext(jp_name="エリナ", en_name="Elina")],
    )
    assert context.characters == ()

    rendered = render_user_message(context, source_text="こんにちは。")
    assert "<characters>" not in rendered


def test_managed_character_flows_into_plan(tmp_path) -> None:
    """A character added via the service is carried in the translation plan."""
    init = initialize_project(FIXTURE_EPUB_A, cwd=tmp_path, provider="fake")
    add_character(init.project_toml, jp_name="エリナ", en_name="Elina", cwd=tmp_path)

    from weaver.storage.db import connect_readonly_database

    with connect_readonly_database(init.database_path) as connection:
        chapter_id = str(
            connection.execute("SELECT id FROM chapters ORDER BY spine_order LIMIT 1").fetchone()[
                "id"
            ]
        )

    plan = prepare_chapter_translation(
        init.project_toml,
        chapter_id,
        provider_override={"type": "fake", "model": "fake-1"},
        cwd=tmp_path,
    )
    assert any(c.jp_name == "エリナ" for c in plan.characters)
