"""Translation context assembly and Phase 4 orchestration."""

from __future__ import annotations

import sqlite3
import tomllib
from collections.abc import Callable, Iterable, Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.ir import BlockIR, DocumentIR
from weaver.errors import ConfigError, ProviderError
from weaver.providers import LLMProvider, build_provider
from weaver.providers.types import GlossaryTerm, TranslationContext, TranslationRequest
from weaver.readers.epub import read_epub
from weaver.storage.db import connect_database, transaction
from weaver.storage.glossary import list_glossary_terms
from weaver.storage.projects import ProjectRecord, get_project
from weaver.storage.segments import (
    SegmentRecord,
    list_segments_for_translation,
    sync_document_segments,
    update_segment_status,
)
from weaver.storage.translations import (
    list_previous_translated_segments,
    record_translation,
)

MAX_GLOSSARY_TERMS_PER_SEGMENT = 20
MAX_CONTEXT_SEGMENTS = 5
MAX_CONTEXT_TOKENS = 600

VALID_HONORIFIC_POLICIES = frozenset({"preserve", "localize", "hybrid"})


@dataclass(frozen=True)
class TranslationRunSummary:
    """Outcome of a `weaver translate` run."""

    total_segments: int
    selected_segments: int
    translated_segments: int
    failed_segments: int
    pending_segments: int
    stale_segments: int
    input_tokens: int
    output_tokens: int


def build_context(
    *,
    segment: BlockIR,
    glossary_terms: Iterable[GlossaryTerm],
    previous_segments: Sequence[tuple[str, str]],
    honorific_policy: str = "preserve",
) -> TranslationContext:
    """Assemble a `TranslationContext` for one segment.

    Filters `glossary_terms` to entries whose `source` appears as a substring
    of the segment's normalized source text, capped at 20 entries
    (PROMPT_DESIGN.md §Glossary Filtering). Trims `previous_segments` to the
    most recent 5 entries within a 600-token estimate (oldest-first ordering
    preserved). Tokens are estimated as 1 token ≈ 4 characters.

    Args:
        segment: Current segment being translated.
        glossary_terms: All approved glossary terms for the project.
        previous_segments: (source, translation) pairs from earlier segments
            in the same chapter, ordered oldest-first.
        honorific_policy: One of `preserve` | `localize` | `hybrid`.

    Returns:
        Immutable TranslationContext ready for prompt rendering.

    Raises:
        ValueError: If `honorific_policy` is not a recognized value.
    """

    if honorific_policy not in VALID_HONORIFIC_POLICIES:
        raise ValueError(
            f"honorific_policy must be one of {sorted(VALID_HONORIFIC_POLICIES)}, "
            f"got {honorific_policy!r}"
        )

    filtered_glossary = _filter_glossary(glossary_terms, segment.normalized_source_text)
    trimmed_window = _trim_window(previous_segments)

    return TranslationContext(
        previous_segments=trimmed_window,
        glossary_terms=filtered_glossary,
        honorific_policy=honorific_policy,
    )


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
        if len(matches) >= MAX_GLOSSARY_TERMS_PER_SEGMENT:
            break
    return tuple(matches)


def _trim_window(
    previous_segments: Sequence[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    if not previous_segments:
        return ()
    tail = list(previous_segments[-MAX_CONTEXT_SEGMENTS:])
    while tail and _estimate_tokens(tail) > MAX_CONTEXT_TOKENS:
        tail.pop(0)
    return tuple((str(source), str(translation)) for source, translation in tail)


def _estimate_tokens(window: Sequence[tuple[str, str]]) -> int:
    total_chars = sum(len(source) + len(translation) for source, translation in window)
    return total_chars // 4


def translate_project(
    project_toml: Path,
    *,
    cwd: Path | None = None,
    retry_failed: bool = False,
    provider: LLMProvider | None = None,
    progress_callback: Callable[[int, int, SegmentRecord, bool], None] | None = None,
) -> TranslationRunSummary:
    """Translate selected project segments through the configured provider.

    Args:
        project_toml: Weaver project file.
        cwd: Working directory used to resolve relative project paths.
        retry_failed: Select failed segments instead of pending segments.
        provider: Optional provider injection for tests.
        progress_callback: Optional callback invoked after each selected segment.

    Returns:
        TranslationRunSummary with current database counts and token totals.
    """

    base_dir = cwd or Path.cwd()
    data = tomllib.loads(project_toml.read_text(encoding="utf-8"))
    project_config = data["project"]
    provider_config = data["provider"]
    translation_config = data["translation"]
    db_path = _resolve_path(str(project_config["database_path"]), base_dir, project_toml.parent)
    source_path = _resolve_path(str(project_config["source_file"]), base_dir, project_toml.parent)

    document = read_epub(source_path)
    block_by_id = _index_blocks(document)
    active_provider = provider or build_provider(provider_config)
    provider_model = str(provider_config["model"])
    honorific_policy = str(translation_config.get("honorifics", "preserve"))

    translated_count = 0
    input_tokens = 0
    output_tokens = 0

    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        with transaction(connection):
            sync_document_segments(connection, project_id=project.id, document=document)

        glossary_terms = list_glossary_terms(connection, project_id=project.id)
        selected = list_segments_for_translation(
            connection, project_id=project.id, retry_failed=retry_failed
        )
        total_selected = len(selected)

        for index, segment in enumerate(selected, start=1):
            block = block_by_id.get(segment.id)
            if block is None:
                raise ConfigError(
                    f"Segment `{segment.id}` is missing from the current source EPUB. "
                    "Likely cause: project state and source file are out of sync. "
                    "Next command: rerun `weaver init <input.epub>` for this source."
                )

            translated, response_input_tokens, response_output_tokens = _translate_one(
                connection=connection,
                segment=segment,
                block=block,
                project=project,
                glossary_terms=glossary_terms,
                honorific_policy=honorific_policy,
                provider=active_provider,
                provider_model=provider_model,
            )
            if translated:
                translated_count += 1
                input_tokens += response_input_tokens or 0
                output_tokens += response_output_tokens or 0
            if progress_callback is not None:
                progress_callback(index, total_selected, segment, translated)

        counts = _read_segment_counts(connection)

    return TranslationRunSummary(
        total_segments=counts["total"],
        selected_segments=total_selected,
        translated_segments=translated_count,
        failed_segments=counts["failed"],
        pending_segments=counts["pending"],
        stale_segments=counts["stale"],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _translate_one(
    *,
    connection: sqlite3.Connection,
    segment: SegmentRecord,
    block: BlockIR,
    project: ProjectRecord,
    glossary_terms: Iterable[GlossaryTerm],
    honorific_policy: str,
    provider: LLMProvider,
    provider_model: str,
) -> tuple[bool, int | None, int | None]:
    with transaction(connection):
        update_segment_status(connection, segment_id=segment.id, status="in_progress")
        previous_segments = list_previous_translated_segments(
            connection,
            chapter_id=segment.chapter_id,
            before_block_order=segment.block_order,
            limit=MAX_CONTEXT_SEGMENTS,
        )
        context = build_context(
            segment=block,
            glossary_terms=glossary_terms,
            previous_segments=previous_segments,
            honorific_policy=honorific_policy,
        )
        request = TranslationRequest(
            segment_id=segment.id,
            source_text=block.source_text,
            normalized_source_text=block.normalized_source_text,
            source_language=project.source_lang,
            target_language=project.target_lang,
            context=context,
            provider_model=provider_model,
        )
        try:
            response = provider.translate(request)
        except ProviderError:
            update_segment_status(connection, segment_id=segment.id, status="failed")
            return False, None, None

        record_translation(
            connection,
            segment_id=segment.id,
            text=response.translation,
            source_hash=segment.source_hash,
            provider=provider.name,
            model=provider_model,
            raw_response=response.raw_response,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
        update_segment_status(connection, segment_id=segment.id, status="translated")
        return True, response.input_tokens, response.output_tokens


def _load_single_project(connection: sqlite3.Connection) -> ProjectRecord:
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ConfigError(
            "Project database has no project row. "
            "Likely cause: database was not initialized by `weaver init`. "
            "Next command: run `weaver init <input.epub>`."
        )
    return get_project(connection, int(row["id"]))


def _index_blocks(document: DocumentIR) -> dict[str, BlockIR]:
    return {block.id: block for chapter in document.chapters for block in chapter.blocks}


def _read_segment_counts(connection: sqlite3.Connection) -> dict[str, int]:
    status_counts = {
        str(row["status"]): int(row["count"])
        for row in connection.execute(
            "SELECT status, COUNT(*) AS count FROM segments GROUP BY status"
        ).fetchall()
    }
    total = sum(status_counts.values())
    return {
        "total": total,
        "pending": status_counts.get("pending", 0),
        "failed": status_counts.get("failed", 0),
        "stale": status_counts.get("stale", 0),
    }


def _resolve_path(path_value: str, cwd: Path, project_toml_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    cwd_path = cwd / path
    if cwd_path.exists():
        return cwd_path
    return project_toml_dir / path
