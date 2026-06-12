"""On-demand AI glossary-target suggestion (Sprint R).

Builds a term-suggestion prompt grounded in the candidate's source term and its
example sentences, calls the user's configured provider via the domain-agnostic
``complete()`` primitive, and parses a strict minimal JSON object ``{"target": "..."}``.

Ephemeral: nothing is persisted here. The human's approve/edit (the existing flow)
is what writes the glossary term. The provider is resolved from the user's
``[provider]`` config via ``build_provider`` — there is no hidden default vendor.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.config import load_project_config
from weaver.errors import ConfigError, GlossarySuggestionError, ProviderUnavailable
from weaver.providers import LLMProvider, build_provider
from weaver.providers.prompts import (
    GLOSSARY_SUGGEST_PROMPT_VERSION,
    render_glossary_suggestion_prompt,
)
from weaver.services.glossary_review import _segment_examples
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_readonly_database
from weaver.storage.glossary import get_glossary_candidate
from weaver.storage.projects import ProjectRecord, get_project

EXAMPLE_LIMIT = 3
MAX_TARGET_CHARS = 80
MAX_OUTPUT_TOKENS = 120
_SENTENCE_END = ".!?。！？"

__all__ = ["GlossarySuggestion", "suggest_glossary_target", "GLOSSARY_SUGGEST_PROMPT_VERSION"]


@dataclass(frozen=True)
class GlossarySuggestion:
    """One ephemeral AI target suggestion plus its provider/cost provenance."""

    target: str
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None


def suggest_glossary_target(
    project_toml: Path,
    candidate_id: int,
    *,
    cwd: Path | None = None,
    provider: LLMProvider | None = None,
) -> GlossarySuggestion:
    """Suggest an EN target for one glossary candidate via the configured provider.

    The provider comes from the project's ``[provider]`` block (no hidden default).
    Read-only: grounding (the candidate + its example sentences) is loaded via a
    read-only connection and nothing is written. The completion is parsed + validated
    into a clean glossary term; an unusable response raises ``GlossarySuggestionError``.
    """

    data = load_project_config(project_toml)
    provider_config = data["provider"]
    configured_model = str(provider_config.get("model", ""))
    db_path = resolve_database_path(project_toml, cwd=cwd)

    active = build_provider(provider_config) if provider is None else provider
    status = active.healthcheck()
    if not status.healthy:
        raise ProviderUnavailable(
            f"Provider {active.name} is unavailable: {status.message or 'no detail'}. "
            "Likely cause: API key missing/invalid or endpoint unreachable. "
            "Next command: run `weaver inspect --healthcheck <project.toml>`."
        )

    with closing(connect_readonly_database(db_path)) as connection:
        project = _load_single_project(connection)
        candidate = get_glossary_candidate(connection, candidate_id=candidate_id)
        examples = _segment_examples(
            connection, project_id=project.id, source=candidate.source, limit=EXAMPLE_LIMIT
        )

    prompt = render_glossary_suggestion_prompt(
        source=candidate.source,
        category=candidate.category,
        examples=examples,
        source_lang=project.source_lang,
        target_lang=project.target_lang,
    )
    completion = active.complete(
        prompt,
        system=f"Glossary assistant ({GLOSSARY_SUGGEST_PROMPT_VERSION}).",
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    target = _parse_target(completion.text)
    return GlossarySuggestion(
        target=target,
        provider=active.name,
        model=status.model or configured_model,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
    )


def _parse_target(text: str) -> str:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise _unusable("the AI response was not valid JSON") from exc
    if not isinstance(data, dict) or "target" not in data or not isinstance(data["target"], str):
        raise _unusable("the AI response had no `target` string")
    target = data["target"].strip()
    if not target:
        raise _unusable("the AI returned an empty target")
    if "\n" in target:
        raise _unusable("the AI returned a multiline target")
    if len(target) > MAX_TARGET_CHARS:
        raise _unusable("the AI returned an over-long target")
    if target[-1] in _SENTENCE_END:
        raise _unusable("the AI returned a sentence, not a glossary term")
    return target


def _unusable(reason: str) -> GlossarySuggestionError:
    return GlossarySuggestionError(
        f"AI returned no usable suggestion: {reason}. "
        "Likely cause: the model did not follow the glossary-target format. "
        "Next command: retry, or type the target manually."
    )


def _load_single_project(connection: sqlite3.Connection) -> ProjectRecord:
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ConfigError(
            "Project database has no project row. "
            "Likely cause: database not initialized by `weaver init`. "
            "Next command: run `weaver init <input.epub>`."
        )
    return get_project(connection, int(row["id"]))
