"""Translation candidate generation service (Sprint L2).

Grounds candidate generation in the same context a normal translation uses:
source segment, glossary, character DB, translation memory, and existing
chapter context. The result is stored as a ``pending`` candidate in the
``translation_candidates`` table — **never** auto-mutating the current
translation.

Every AI artifact carries full provenance (provider, model, prompt version,
context version, source segments, timestamp).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weaver.core.config import load_project_config
from weaver.core.segment import normalize_japanese_text
from weaver.errors import (
    ConfigError,
    ProviderError,
    ProviderUnavailable,
    SegmentNotFoundError,
)
from weaver.providers import LLMProvider, build_provider
from weaver.providers.types import (
    CharacterContext,
    GlossaryTerm,
    TranslationContext,
    TranslationRequest,
)
from weaver.services.glossary import raise_on_glossary_conflicts
from weaver.services.project_paths import resolve_database_path
from weaver.storage.candidates import (
    CandidateRecord,
    insert_candidate,
    supersede_candidates_for_segment,
)
from weaver.storage.characters import list_characters
from weaver.storage.db import connect_database, transaction
from weaver.storage.glossary import list_glossary_terms
from weaver.storage.projects import ProjectRecord, get_project
from weaver.storage.segments import SegmentRecord, get_segment
from weaver.storage.translations import list_previous_translated_segments

PROMPT_VERSION = "balanced-1.0"

VALID_HONORIFIC_POLICIES = frozenset({"preserve", "localize", "hybrid"})


def _load_project_record(connection: sqlite3.Connection) -> ProjectRecord:
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ConfigError(
            "Project database has no project row. "
            "Likely cause: database was not initialized by `weaver init`. "
            "Next command: run `weaver init <input.epub>`."
        )
    return get_project(connection, int(row["id"]))


def _resolve_volume_id(
    connection: sqlite3.Connection, *, project_id: int, segment: SegmentRecord
) -> int | None:
    """Resolve volume id from a segment's chapter."""
    row = connection.execute(
        "SELECT volume_id FROM chapters WHERE id = ?",
        (segment.chapter_id,),
    ).fetchone()
    if row is None or row["volume_id"] is None:
        return None
    return int(row["volume_id"])


def generate_candidate(
    project_toml: Path,
    chapter_id: str,
    segment_id: str,
    *,
    cwd: Path | None = None,
    provider_override: dict[str, str] | None = None,
    provider: LLMProvider | None = None,
) -> CandidateRecord:
    """Generate one translation candidate for a single segment.

    The candidate is grounded in the same context as a normal translation:
    source text, glossary, characters, translation memory, and preceding
    segment context. The result is persisted as ``pending`` — **never**
    auto-applied.

    Args:
        project_toml: Path to the project's ``project.toml``.
        chapter_id: Chapter the segment belongs to.
        segment_id: Target segment id.
        cwd: Working directory for path resolution.
        provider_override: Optional dict to override provider config
            (``{"type": ..., "model": ...}``).
        provider: Optional pre-built provider (for tests).

    Returns:
        The persisted CandidateRecord with status ``pending``.

    Raises:
        ChapterNotFoundError: If the chapter does not exist.
        SegmentNotFoundError: If the segment does not exist or is not in the chapter.
        ProviderError: If the provider call fails.
    """

    base_dir = cwd or Path.cwd()
    data = load_project_config(project_toml)
    provider_config = _merge_provider_config(data["provider"], provider_override)
    translation_config = data["translation"]
    db_path = resolve_database_path(project_toml, cwd=base_dir)

    active_provider = build_provider(provider_config) if provider is None else provider
    status = active_provider.healthcheck()
    if not status.healthy:
        detail = status.message or "no detail returned"
        raise ProviderUnavailable(
            f"Provider {active_provider.name} is unavailable: {detail}. "
            "Likely cause: API key missing/invalid, network unreachable. "
            "Next command: run `weaver inspect --healthcheck <project.toml>`."
        )
    provider_model = str(provider_config["model"])
    honorific_policy = str(translation_config.get("honorifics", "preserve"))
    if honorific_policy not in VALID_HONORIFIC_POLICIES:
        valid = ", ".join(sorted(VALID_HONORIFIC_POLICIES))
        raise ConfigError(
            f"Invalid honorifics value `{honorific_policy}`. "
            f"Likely cause: project.toml [translation] honorifics must be one of: {valid}. "
            "Next command: edit project.toml and correct the value."
        )

    with closing(connect_database(db_path)) as connection:
        project = _load_project_record(connection)
        raise_on_glossary_conflicts(connection, project_id=project.id)

        segment = get_segment(connection, segment_id)
        if segment is None:
            raise SegmentNotFoundError(
                f"Segment '{segment_id}' was not found. "
                "Likely cause: the segment id is wrong. "
                "Next command: open the chapter workspace to list segment ids."
            )
        if segment.chapter_id != chapter_id:
            raise SegmentNotFoundError(
                f"Segment '{segment_id}' is not in chapter '{chapter_id}'. "
                "Likely cause: segment belongs to a different chapter."
            )

        # Build the same context as a normal translation
        glossary_terms = list_glossary_terms(connection, project_id=project.id)
        characters = _load_character_contexts(connection, project_id=project.id)
        normalized_source = normalize_japanese_text(segment.source_text)

        previous_segments = list_previous_translated_segments(
            connection,
            chapter_id=chapter_id,
            before_block_order=segment.block_order,
            limit=5,
        )

        context = TranslationContext(
            previous_segments=tuple(previous_segments),
            glossary_terms=_filter_glossary(glossary_terms, normalized_source),
            honorific_policy=honorific_policy,
            characters=_filter_characters(characters, normalized_source),
        )

        request = TranslationRequest(
            segment_id=segment.id,
            source_text=segment.source_text,
            normalized_source_text=normalized_source,
            source_language=project.source_lang,
            target_language=project.target_lang,
            context=context,
            provider_model=provider_model,
        )

        try:
            response = active_provider.translate(request)
        except ProviderError:
            volume_id = _resolve_volume_id(connection, project_id=project.id, segment=segment)
            provenance = _build_provenance(
                provider=active_provider.name,
                model=provider_model,
                chapter_id=chapter_id,
                segment_id=segment_id,
                error="provider_error",
            )
            with transaction(connection):
                return insert_candidate(
                    connection,
                    project_id=project.id,
                    volume_id=volume_id,
                    chapter_id=chapter_id,
                    segment_id=segment_id,
                    source_text=segment.source_text,
                    candidate_text="",
                    provider=active_provider.name,
                    model=provider_model,
                    provenance_json=json.dumps(provenance, ensure_ascii=False),
                )

        volume_id = _resolve_volume_id(connection, project_id=project.id, segment=segment)
        provenance = _build_provenance(
            provider=active_provider.name,
            model=provider_model,
            chapter_id=chapter_id,
            segment_id=segment_id,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )

        with transaction(connection):
            # Supersede any existing pending/approved candidates for this segment
            supersede_candidates_for_segment(connection, segment_id=segment_id)
            record = insert_candidate(
                connection,
                project_id=project.id,
                volume_id=volume_id,
                chapter_id=chapter_id,
                segment_id=segment_id,
                source_text=segment.source_text,
                candidate_text=response.translation,
                provider=active_provider.name,
                model=provider_model,
                provenance_json=json.dumps(provenance, ensure_ascii=False),
            )

    return record


def _build_provenance(
    *,
    provider: str,
    model: str,
    chapter_id: str,
    segment_id: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build the provenance dict for one AI artifact."""
    prov: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "chapter_id": chapter_id,
        "source_segments": [segment_id],
        "created_at": datetime.now(UTC).isoformat(),
    }
    if input_tokens is not None:
        prov["input_tokens"] = input_tokens
    if output_tokens is not None:
        prov["output_tokens"] = output_tokens
    if error is not None:
        prov["error"] = error
    return prov


def _filter_glossary(
    terms: Iterable[GlossaryTerm], normalized_source: str
) -> tuple[GlossaryTerm, ...]:
    matches: list[GlossaryTerm] = []
    for term in terms:
        if not term.source:
            continue
        haystack = normalized_source if term.case_sensitive else normalized_source.casefold()
        needle = term.source if term.case_sensitive else term.source.casefold()
        if needle in haystack:
            matches.append(term)
        if len(matches) >= 20:
            break
    return tuple(matches)


def _filter_characters(
    characters: Iterable[CharacterContext], normalized_source: str
) -> tuple[CharacterContext, ...]:
    matches: list[CharacterContext] = []
    for character in characters:
        if not character.jp_name:
            continue
        if character.jp_name in normalized_source:
            matches.append(character)
        if len(matches) >= 20:
            break
    return tuple(matches)


def _load_character_contexts(
    connection: sqlite3.Connection, *, project_id: int
) -> tuple[CharacterContext, ...]:
    return tuple(
        CharacterContext(
            jp_name=record.jp_name,
            en_name=record.en_name,
            gender=record.gender,
            role=record.role,
            notes=record.notes,
        )
        for record in list_characters(connection, project_id=project_id)
    )


def _merge_provider_config(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return base
    return {**base, **{k: v for k, v in override.items() if v is not None}}
