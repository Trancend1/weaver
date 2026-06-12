"""Prompt rendering tests."""

from __future__ import annotations

from weaver.providers.prompts import (
    GLOSSARY_SUGGEST_PROMPT_VERSION,
    load_repair_prompt,
    load_system_prompt,
    render_glossary_suggestion_prompt,
    render_user_message,
)
from weaver.providers.types import GlossaryTerm, TranslationContext


def test_glossary_suggestion_prompt_is_grounded_and_jsonmode_safe() -> None:
    prompt = render_glossary_suggestion_prompt(
        source="魔王",
        category="title",
        examples=["その時、魔王が現れた。"],
        source_lang="ja",
        target_lang="en",
    )
    assert "魔王" in prompt
    assert "その時、魔王が現れた。" in prompt
    assert "json" in prompt.lower()  # json-mode-strict endpoints require it
    assert '{"target"' in prompt  # the strict shape is requested
    assert isinstance(GLOSSARY_SUGGEST_PROMPT_VERSION, str)


def test_glossary_suggestion_prompt_handles_no_examples() -> None:
    prompt = render_glossary_suggestion_prompt(
        source="勇者", category=None, examples=[], source_lang="ja", target_lang="en"
    )
    assert "勇者" in prompt
    assert "json" in prompt.lower()


def test_system_prompt_includes_jp_to_en_role() -> None:
    prompt = load_system_prompt()

    assert "Japanese to English" in prompt
    assert "JSON" in prompt


def test_repair_prompt_demands_json_only() -> None:
    prompt = load_repair_prompt()

    assert "JSON" in prompt
    assert "translation" in prompt


def test_user_message_omits_glossary_when_no_terms() -> None:
    context = TranslationContext(
        previous_segments=(),
        glossary_terms=(),
        honorific_policy="preserve",
    )

    rendered = render_user_message(context, source_text="テスト")

    assert "<glossary>" not in rendered
    assert "<context>" not in rendered
    assert "<source>" in rendered
    assert "テスト" in rendered
    assert "honorifics: preserve" in rendered


def test_user_message_includes_glossary_when_terms_present() -> None:
    context = TranslationContext(
        previous_segments=(),
        glossary_terms=(
            GlossaryTerm(source="護衛", target="bodyguard", category="role", notes="use bodyguard"),
        ),
        honorific_policy="preserve",
    )

    rendered = render_user_message(context, source_text="彼は護衛だ。")

    assert "<glossary>" in rendered
    assert "護衛\tbodyguard\trole\tuse bodyguard" in rendered


def test_user_message_renders_context_with_prev_markers() -> None:
    context = TranslationContext(
        previous_segments=(
            ("彼は剣を鞘に収めた。", "He sheathed his sword."),
            ("「まだ終わりじゃない」とカイは言った。", '"It\'s not over yet," Kai said.'),
        ),
        glossary_terms=(),
        honorific_policy="preserve",
    )

    rendered = render_user_message(context, source_text="次の場面。")

    assert "<context>" in rendered
    assert "[PREV-2] 彼は剣を鞘に収めた。" in rendered
    assert "[PREV-1] 「まだ終わりじゃない」とカイは言った。" in rendered
    assert "→ He sheathed his sword." in rendered
