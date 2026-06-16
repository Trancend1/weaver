"""Jinja2 prompt template loader."""

from __future__ import annotations

from collections.abc import Sequence
from functools import cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from weaver.providers.types import TranslationContext

_TEMPLATES_DIR = Path(__file__).with_name("templates")


@cache
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=False,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )


@cache
def load_system_prompt() -> str:
    """Return the balanced-mode system prompt."""

    return (_TEMPLATES_DIR / "balanced_system.txt").read_text(encoding="utf-8")


@cache
def load_repair_prompt() -> str:
    """Return the JSON repair follow-up prompt."""

    return (_TEMPLATES_DIR / "repair.txt").read_text(encoding="utf-8")


def render_user_message(context: TranslationContext, *, source_text: str) -> str:
    """Render the balanced-mode user message for one segment.

    Args:
        context: Pre-filtered glossary + rolling window from `build_context()`.
        source_text: Normalized source text for the current segment.

    Returns:
        Rendered prompt body with `<policy>`, optional `<glossary>`,
        optional `<context>`, and `<source>` sections per PROMPT_DESIGN.md.
    """

    template = _environment().get_template("balanced_user.jinja2")
    return template.render(
        honorific_policy=context.honorific_policy,
        glossary_terms=context.glossary_terms,
        characters=context.characters,
        previous_segments=context.previous_segments,
        source_text=source_text,
    )


GLOSSARY_SUGGEST_PROMPT_VERSION = "glossary-suggest-1.0"


def render_glossary_suggestion_prompt(
    *,
    source: str,
    category: str | None,
    examples: list[str],
    source_lang: str,
    target_lang: str,
) -> str:
    """Build the term-suggestion prompt (domain content; the provider sees an opaque string).

    Requests a strict minimal JSON object so the service can parse + validate. The literal
    word "json" is present so OpenAI-compatible json-mode endpoints accept the request.
    """

    lines = [
        f"You are a translation-glossary assistant for {source_lang} to {target_lang}.",
        f"Propose a concise {target_lang} glossary target for this {source_lang} term.",
        'Return ONLY a strict JSON object of the form {"target": "..."} and nothing else.',
        "The target must be a short term or noun phrase, not a sentence, not multiline.",
        "",
        f"Term: {source}",
    ]
    if category:
        lines.append(f"Category: {category}")
    if examples:
        lines.append("Example sentences (for context):")
        lines.extend(f"- {example}" for example in examples)
    return "\n".join(lines)


ENFORCEMENT_REPAIR_PROMPT_VERSION = "enforcement-repair-1.0"

ENFORCEMENT_REPAIR_SYSTEM = (
    "You are a professional literary translator revising your own translation to "
    "satisfy specific glossary, character-name, and quality constraints. "
    "Respond ONLY with a valid JSON object. No explanation, no markdown, no prose "
    "outside the JSON."
)


def render_enforcement_repair_prompt(
    *,
    source_text: str,
    previous_translation: str,
    violations: Sequence[str],
    source_language: str,
    target_language: str,
) -> str:
    """Build the targeted enforcement-repair message (ADR 019 E2; domain content).

    Enumerates the deterministic violations and asks for a corrected translation
    that fixes every one and changes nothing else. The provider sees an opaque
    string (ADR 014). The literal word "json" is present so OpenAI-compatible
    json-mode endpoints accept the request.
    """

    lines = [
        f"Revise this {source_language} to {target_language} translation.",
        "The previous translation broke the constraints listed below. Produce a "
        "corrected translation that fixes every listed problem and changes nothing "
        "else (do not paraphrase unaffected text).",
        "Respond ONLY with a strict JSON object of the form "
        '{"translation": "...", "notes": [], "uncertain_terms": []} and nothing else.',
        "",
        "Constraints that were violated:",
    ]
    lines.extend(f"- {violation}" for violation in violations)
    lines += [
        "",
        f"Source ({source_language}):",
        source_text,
        "",
        "Previous translation (fix only what the constraints require):",
        previous_translation,
    ]
    return "\n".join(lines)
