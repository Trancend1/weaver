"""Jinja2 prompt template loader."""

from __future__ import annotations

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
