"""Translation context assembly and Phase 4 orchestration."""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from weaver.core.config import load_project_config
from weaver.core.ir import BlockIR, DocumentIR, scope_document_to_volume
from weaver.core.slop_seed import DEFAULT_BANNED_PHRASES
from weaver.core.task_types import TaskType
from weaver.errors import ConfigError, ParserError, ProviderError, ProviderUnavailable
from weaver.providers import LLMProvider, build_provider
from weaver.providers.types import (
    CharacterContext,
    GlossaryTerm,
    TranslationContext,
    TranslationProfile,
    TranslationRequest,
    TranslationResponse,
)
from weaver.readers import read_source
from weaver.services.enforcement import evaluate_translation, repair_translation
from weaver.services.glossary import raise_on_glossary_conflicts
from weaver.services.routing import resolve_chain
from weaver.services.segment_runner import run_segment_window
from weaver.storage.characters import list_characters
from weaver.storage.db import connect_database, transaction
from weaver.storage.glossary import list_glossary_terms, record_uncertain_glossary_candidate
from weaver.storage.projects import ProjectRecord, get_project
from weaver.storage.segments import (
    SegmentRecord,
    SegmentStatus,
    list_segments_for_translation,
    reset_in_progress_segments,
    sync_document_segments,
    update_segment_status,
)
from weaver.storage.translation_memory import (
    lookup_translation_memory,
    save_translation_memory,
)
from weaver.storage.translations import (
    list_previous_translated_segments,
    record_translation,
)
from weaver.storage.volumes import list_volumes

MAX_GLOSSARY_TERMS_PER_SEGMENT = 20
MAX_CHARACTERS_PER_SEGMENT = 20
MAX_CONTEXT_SEGMENTS = 5
# Honest CJK-aware budget for the rolling window (audit N7). The old flat
# `chars // 4` estimator undercounted Japanese ~3x, so the previous "600 token"
# label really admitted ~1.5–2k tokens of JP context. Recalibrated: a typical
# 5-pair light-novel window (~JP source + EN translation) costs ~700 honest
# tokens, so 1000 preserves today's effective window for common prose while
# roughly halving the old worst-case real spend.
MAX_CONTEXT_TOKENS = 1000

# Provider/model sentinel recorded on a translation reused from translation memory,
# so the attempt history stays audit-able (it was not a live provider call).
MEMORY_PROVIDER = "memory"
MEMORY_MODEL = "memory"

VALID_HONORIFIC_POLICIES = frozenset({"preserve", "localize", "hybrid"})

# Bounded translate concurrency (ADR 020). Absent = 1 = today's sequential
# behavior bit-for-bit. The cap is fixed at 4 — no autoscaling (D9 fence).
MAX_CONCURRENT_LIMIT = 4


def resolve_max_concurrent(translation_config: Mapping[str, Any]) -> int:
    """Read and validate `[translation] max_concurrent`.

    Args:
        translation_config: The parsed `[translation]` table.

    Returns:
        The worker-window size, 1 when the key is absent.

    Raises:
        ConfigError: When the value is not an integer in 1..4.
    """

    if "max_concurrent" not in translation_config:
        return 1
    value = translation_config["max_concurrent"]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(
            f"Invalid max_concurrent value `{value!r}` (expected type: integer). "
            "Likely cause: project.toml [translation] max_concurrent was hand-edited. "
            "Next command: edit project.toml and set an integer between 1 and "
            f"{MAX_CONCURRENT_LIMIT}."
        )
    if not 1 <= value <= MAX_CONCURRENT_LIMIT:
        raise ConfigError(
            f"Invalid max_concurrent value `{value}` "
            f"(expected: between 1 and {MAX_CONCURRENT_LIMIT}). "
            "Likely cause: project.toml [translation] max_concurrent is out of range. "
            "Next command: edit project.toml and set a value between 1 and "
            f"{MAX_CONCURRENT_LIMIT}."
        )
    return value


# How long a connection stays cold-marked after a per-segment failure within one
# run (ADR 018 D4 — a simple try-next window, not a circuit breaker).
_FALLBACK_COLD_SECONDS = 30.0

_LOGGER = logging.getLogger(__name__)


class ColdMarks:
    """Per-run fallback cold-mark map, safe for the M4 worker window.

    ADR 018 D4: a failed engine is skipped for a short window, never
    circuit-broken. The lock is defensive — today's two call sites are single
    dict operations, atomic under CPython — but it keeps the invariant explicit
    if this ever becomes a read-modify-write.
    """

    def __init__(self) -> None:
        self._until: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_cold(self, engine_name: str, *, now: float) -> bool:
        with self._lock:
            return self._until.get(engine_name, 0.0) > now

    def mark(self, engine_name: str, until: float) -> None:
        with self._lock:
            self._until[engine_name] = until


ProgressCallback = Callable[[int, int, SegmentRecord, bool, int | None, int | None], None]


@dataclass(frozen=True)
class TranslationRunSummary:
    """Outcome of a `weaver translate` run."""

    total_segments: int
    selected_segments: int
    translated_segments: int
    reused_from_memory: int
    failed_segments: int
    pending_segments: int
    stale_segments: int
    input_tokens: int
    output_tokens: int
    # Non-None when the primary provider failed its pre-flight healthcheck and
    # the run continued on a healthy fallback (audit A1); surfaced by the CLI.
    preflight_warning: str | None = None
    # Hidden round-trips made visible (audit F6 / §4.3 gate 6): enforcement
    # repair re-asks (E2) and provider-internal JSON-parse repairs.
    repair_calls: int = 0
    json_repair_calls: int = 0


@dataclass(frozen=True)
class SegmentTranslationOutcome:
    """Result of one :func:`translate_one_segment` call.

    ``input_tokens``/``output_tokens`` are the segment's **total** provider
    spend (primary call plus the repair re-ask when one was issued), so run
    summaries reconcile exactly with the per-row primary/repair split persisted
    by ``record_translation`` (audit A5). ``None`` on failure or memory reuse.
    """

    translated: bool
    reused_from_memory: bool
    input_tokens: int | None
    output_tokens: int | None
    # True when an enforcement repair re-ask (ADR 019 E2) was issued for this
    # segment — regardless of whether its result was accepted.
    repair_call_made: bool = False
    # True when the provider needed an internal JSON-parse repair round-trip.
    json_repair_used: bool = False


def preflight_provider_chain(
    provider: LLMProvider,
    fallback_engines: Sequence[tuple[LLMProvider, str]] = (),
) -> str | None:
    """Healthcheck the engine chain once before a run starts (audit A1).

    A healthy primary returns ``None`` — today's behavior. A dead primary no
    longer aborts a run that has a healthy fallback configured: the per-segment
    try-next chain (ADR 018 D4) cold-marks the primary and advances, so the run
    completes on the fallback. The returned warning is logged here and carried
    on the plan/summary so the failure stays visible, never silent.

    Raises:
        ProviderUnavailable: When the primary is unhealthy and no configured
            fallback passes its healthcheck (or none is configured) — the
            pre-flight abort stands.
    """

    status = provider.healthcheck()
    if status.healthy:
        return None
    detail = status.message or "no detail returned"
    for engine, _model in fallback_engines:
        if engine.healthcheck().healthy:
            warning = (
                f"Primary provider {provider.name} is unavailable: {detail}. "
                f"Continuing on healthy fallback {engine.name}; the primary is "
                "retried during the run (ADR 018 D4)."
            )
            _LOGGER.warning(warning)
            return warning
    fallback_note = (
        ", and no configured fallback passed its healthcheck" if fallback_engines else ""
    )
    raise ProviderUnavailable(
        f"Provider {provider.name} is unavailable: {detail}{fallback_note}. "
        "Likely cause: API key missing/invalid, network unreachable, or "
        "local Ollama not running. "
        "Next command: run `weaver inspect --healthcheck <project.toml>`."
    )


def build_context(
    *,
    normalized_source_text: str,
    glossary_terms: Iterable[GlossaryTerm],
    previous_segments: Sequence[tuple[str, str]],
    honorific_policy: str = "preserve",
    characters: Iterable[CharacterContext] = (),
    profile: TranslationProfile | None = None,
) -> TranslationContext:
    """Assemble a `TranslationContext` for one segment.

    Filters `glossary_terms` to entries whose `source` appears as a substring
    of the segment's normalized source text, capped at 20 entries
    (PROMPT_DESIGN.md §Glossary Filtering). Trims `previous_segments` to the
    most recent 5 entries within the `MAX_CONTEXT_TOKENS` estimate (oldest-first
    ordering preserved). Tokens are estimated CJK-aware via `estimate_tokens`
    (CJK ≈ 1 token/char, other ≈ 1/4 — audit N7).

    Args:
        normalized_source_text: Normalized source text of the current segment,
            used for substring glossary matching.
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

    filtered_glossary = _filter_glossary(glossary_terms, normalized_source_text)
    filtered_characters = _filter_characters(characters, normalized_source_text)
    trimmed_window = _trim_window(previous_segments)

    return TranslationContext(
        previous_segments=trimmed_window,
        glossary_terms=filtered_glossary,
        honorific_policy=honorific_policy,
        characters=filtered_characters,
        profile=profile,
    )


def _filter_glossary(
    terms: Iterable[GlossaryTerm], normalized_source: str
) -> tuple[GlossaryTerm, ...]:
    # Hoist the source casefold out of the per-term loop: it is invariant across
    # terms, so folding it once per segment (not once per term) is O(1) vs O(n).
    folded_source = normalized_source.casefold()
    matches: list[GlossaryTerm] = []
    for term in terms:
        if not term.source:
            continue
        haystack = normalized_source if term.case_sensitive else folded_source
        needle = term.source if term.case_sensitive else term.source.casefold()
        if needle in haystack:
            matches.append(term)
        if len(matches) >= MAX_GLOSSARY_TERMS_PER_SEGMENT:
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
        if len(matches) >= MAX_CHARACTERS_PER_SEGMENT:
            break
    return tuple(matches)


def load_character_contexts(
    connection: sqlite3.Connection, *, project_id: int
) -> tuple[CharacterContext, ...]:
    """Load a project's characters as prompt-ready contexts (storage → DTO)."""

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


def _trim_window(
    previous_segments: Sequence[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    if not previous_segments:
        return ()
    tail = list(previous_segments[-MAX_CONTEXT_SEGMENTS:])
    while tail and _estimate_window_tokens(tail) > MAX_CONTEXT_TOKENS:
        tail.pop(0)
    return tuple((str(source), str(translation)) for source, translation in tail)


# Unicode ranges treated as CJK for token estimation: on modern BPE
# vocabularies these characters tokenize near 1 token each, while Latin prose
# averages ~4 characters per token.
_CJK_RANGES = (
    (0x3000, 0x30FF),  # CJK punctuation, hiragana, katakana
    (0x3400, 0x4DBF),  # CJK unified extension A
    (0x4E00, 0x9FFF),  # CJK unified ideographs
    (0xF900, 0xFAFF),  # CJK compatibility ideographs
    (0xFF00, 0xFFEF),  # full-width forms + half-width katakana
)


def estimate_tokens(text: str) -> int:
    """Two-class token estimate (audit N7): CJK ≈ 1 token/char, other ≈ 1/4.

    Deterministic, dependency-free heuristic shared by the rolling-window
    budget and dry-run cost estimates. The old flat ``chars // 4`` undercounted
    Japanese roughly 3x.
    """

    cjk_chars = 0
    other_chars = 0
    for char in text:
        code = ord(char)
        if any(low <= code <= high for low, high in _CJK_RANGES):
            cjk_chars += 1
        else:
            other_chars += 1
    return cjk_chars + other_chars // 4


def _estimate_window_tokens(window: Sequence[tuple[str, str]]) -> int:
    return sum(
        estimate_tokens(str(source)) + estimate_tokens(str(translation))
        for source, translation in window
    )


def translate_project(
    project_toml: Path,
    *,
    cwd: Path | None = None,
    retry_failed: bool = False,
    dry_run: bool = False,
    first_n: int | None = None,
    provider: LLMProvider | None = None,
    provider_override: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> TranslationRunSummary:
    """Translate selected project segments through the configured provider.

    Args:
        project_toml: Weaver project file.
        cwd: Working directory used to resolve relative project paths.
        retry_failed: Select failed segments instead of pending segments.
        dry_run: When True, count selected segments and estimate input tokens
            without contacting the provider or mutating the database. Returned
            `input_tokens` is a CJK-aware estimate (`estimate_tokens`);
            `translated_segments` is always 0.
        provider: Optional provider injection for tests.
        provider_override: Optional dict merged onto the configured `[provider]`
            section (e.g. `{"type": "gemini", "model": "gemini-1.5-flash"}`) so
            a single run can target a different provider/model without editing
            project.toml. Ignored when `provider` is supplied directly.
        first_n: When set, translate only the first N selected segments. The
            remaining segments stay in their current status. Composes with
            ``retry_failed`` and ``dry_run``.
        progress_callback: Optional callback invoked after each selected segment
            with `(index, total, segment, translated, input_tokens,
            output_tokens)`. In dry-run mode the callback receives
            `translated=False` and the per-segment estimated input tokens.
        should_cancel: Optional predicate checked before each segment. When it
            returns True the loop stops cleanly, leaving already-translated
            segments committed and the rest in their prior status (cooperative
            cancel, ADR `0019`). CLI passes None (no behavior change); the web
            cockpit passes the JobManager cancel flag.

    Returns:
        TranslationRunSummary with current database counts and token totals.
    """

    base_dir = cwd or Path.cwd()
    data = load_project_config(project_toml)
    project_config = data["project"]
    engine_chain = resolve_chain(project_toml, TaskType.translate, data=data)
    provider_config = _merge_provider_config(engine_chain[0].provider_config, provider_override)
    translation_config = data["translation"]
    persist_raw_response = raw_response_logging_enabled(data)
    enforce_repair = enforce_repair_enabled(data)
    profile = build_translation_profile(data)
    db_path = _resolve_path(str(project_config["database_path"]), base_dir, project_toml.parent)
    source_path = _resolve_path(str(project_config["source_file"]), base_dir, project_toml.parent)

    document = read_source(source_path)
    # Scope reader ids to this source's volume so the freshly-read document joins
    # 1:1 with the persisted (volume-scoped) rows below (Stage 11B-1.5).
    with closing(connect_database(db_path)) as id_connection:
        scope_volume_id = _source_volume_id(
            id_connection,
            project_id=_load_single_project(id_connection).id,
            source_path=source_path,
        )
    document = scope_document_to_volume(document, scope_volume_id)
    block_by_id = _index_blocks(document)

    if dry_run:
        return _dry_run_summary(
            db_path=db_path,
            block_by_id=block_by_id,
            retry_failed=retry_failed,
            first_n=first_n,
            progress_callback=progress_callback,
        )

    active_provider = build_provider(provider_config) if provider is None else provider
    # Build the fallback engines once per run (skip any that cannot be built — a
    # missing-key fallback must not abort the run; the primary still translates).
    # Skipped when a provider is injected directly (test path).
    fallback_engines: list[tuple[LLMProvider, str]] = []
    run_cold = ColdMarks()
    if provider is None:
        for candidate in engine_chain[1:]:
            try:
                fallback_engines.append(
                    (build_provider(candidate.provider_config), candidate.model)
                )
            except (ConfigError, ProviderError):
                continue
    preflight_warning = preflight_provider_chain(active_provider, fallback_engines)
    provider_model = str(provider_config["model"])
    honorific_policy = str(translation_config.get("honorifics", "preserve"))
    if honorific_policy not in VALID_HONORIFIC_POLICIES:
        valid = ", ".join(sorted(VALID_HONORIFIC_POLICIES))
        raise ConfigError(
            f"Invalid honorifics value `{honorific_policy}`. "
            f"Likely cause: project.toml [translation] honorifics must be one of: {valid}. "
            "Next command: edit project.toml and correct the value."
        )

    translated_count = 0
    reused_count = 0
    input_tokens = 0
    output_tokens = 0
    repair_calls = 0
    json_repair_calls = 0

    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        raise_on_glossary_conflicts(connection, project_id=project.id)
        volume_id = _source_volume_id(connection, project_id=project.id, source_path=source_path)
        with transaction(connection):
            sync_document_segments(
                connection, project_id=project.id, volume_id=volume_id, document=document
            )
            reset_in_progress_segments(connection)

        glossary_terms = list_glossary_terms(connection, project_id=project.id)
        characters = load_character_contexts(connection, project_id=project.id)
        selected = list_segments_for_translation(
            connection, project_id=project.id, retry_failed=retry_failed
        )
        if first_n is not None:
            selected = selected[:first_n]
        total_selected = len(selected)

        max_concurrent = resolve_max_concurrent(translation_config)

        def _translate(
            worker_connection: sqlite3.Connection, segment: SegmentRecord
        ) -> SegmentTranslationOutcome:
            block = block_by_id.get(segment.id)
            if block is None:
                raise ConfigError(
                    f"Segment `{segment.id}` is missing from the current source EPUB. "
                    "Likely cause: project state and source file are out of sync. "
                    "Next command: rerun `weaver init <input.epub>` for this source."
                )
            return translate_one_segment(
                connection=worker_connection,
                segment=segment,
                source_text=block.source_text,
                normalized_source_text=block.normalized_source_text,
                project=project,
                glossary_terms=glossary_terms,
                honorific_policy=honorific_policy,
                provider=active_provider,
                provider_model=provider_model,
                characters=characters,
                persist_raw_response=persist_raw_response,
                fallbacks=fallback_engines,
                cold=run_cold,
                enforce_repair=enforce_repair,
                profile=profile,
            )

        def _accumulate(
            ordinal: int,
            total: int,
            segment: SegmentRecord,
            outcome: SegmentTranslationOutcome,
        ) -> None:
            nonlocal translated_count, reused_count, input_tokens, output_tokens
            nonlocal repair_calls, json_repair_calls
            if outcome.translated:
                translated_count += 1
                input_tokens += outcome.input_tokens or 0
                output_tokens += outcome.output_tokens or 0
            if outcome.reused_from_memory:
                reused_count += 1
            if outcome.repair_call_made:
                repair_calls += 1
            if outcome.json_repair_used:
                json_repair_calls += 1
            if progress_callback is not None:
                progress_callback(
                    ordinal,
                    total,
                    segment,
                    outcome.translated,
                    outcome.input_tokens,
                    outcome.output_tokens,
                )

        run_segment_window(
            items=selected,
            max_concurrent=max_concurrent,
            connection_factory=lambda: connect_database(db_path),
            work=_translate,
            on_complete=_accumulate,
            should_cancel=should_cancel,
        )

        counts = _read_segment_counts(connection)

    return TranslationRunSummary(
        total_segments=counts["total"],
        selected_segments=total_selected,
        translated_segments=translated_count,
        reused_from_memory=reused_count,
        failed_segments=counts["failed"],
        pending_segments=counts["pending"],
        stale_segments=counts["stale"],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        preflight_warning=preflight_warning,
        repair_calls=repair_calls,
        json_repair_calls=json_repair_calls,
    )


def _merge_provider_config(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return base
    return {**base, **{k: v for k, v in override.items() if v is not None}}


def _dry_run_summary(
    *,
    db_path: Path,
    block_by_id: dict[str, BlockIR],
    retry_failed: bool,
    first_n: int | None,
    progress_callback: ProgressCallback | None,
) -> TranslationRunSummary:
    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        selected = list_segments_for_translation(
            connection, project_id=project.id, retry_failed=retry_failed
        )
        if first_n is not None:
            selected = selected[:first_n]
        counts = _read_segment_counts(connection)

    total_selected = len(selected)
    estimated_input_tokens = 0
    for index, segment in enumerate(selected, start=1):
        block = block_by_id.get(segment.id)
        segment_estimate = estimate_tokens(block.normalized_source_text) if block is not None else 0
        estimated_input_tokens += segment_estimate
        if progress_callback is not None:
            progress_callback(index, total_selected, segment, False, segment_estimate, None)

    return TranslationRunSummary(
        total_segments=counts["total"],
        selected_segments=total_selected,
        translated_segments=0,
        reused_from_memory=0,
        failed_segments=counts["failed"],
        pending_segments=counts["pending"],
        stale_segments=counts["stale"],
        input_tokens=estimated_input_tokens,
        output_tokens=0,
    )


def translate_one_segment(
    *,
    connection: sqlite3.Connection,
    segment: SegmentRecord,
    source_text: str,
    normalized_source_text: str,
    project: ProjectRecord,
    glossary_terms: Iterable[GlossaryTerm],
    honorific_policy: str,
    provider: LLMProvider,
    provider_model: str,
    characters: Iterable[CharacterContext] = (),
    use_translation_memory: bool = True,
    persist_raw_response: bool = False,
    fallbacks: Sequence[tuple[LLMProvider, str]] = (),
    cold: ColdMarks | None = None,
    enforce_repair: bool = True,
    profile: TranslationProfile | None = None,
) -> SegmentTranslationOutcome:
    """Translate one segment; commit its result and status atomically.

    Sets the segment to ``in_progress`` (its own short transaction). When
    ``use_translation_memory`` is True, first looks up the segment's
    ``source_hash`` in the project's translation memory; on an exact match it
    records the stored target as a new attempt (provider/model ``"memory"``),
    marks the segment ``translated``, and returns **without calling the
    provider**. On a miss it assembles context (rolling window + filtered
    glossary/characters), calls the provider, records the result, and saves the
    successful translation back into memory (never overwriting a ``manual``
    entry). On ``ProviderError`` the status becomes ``failed``, no attempt is
    recorded, and nothing is written to memory. Source text is never mutated.
    The translation-memory key is always the stored ``segment.source_hash``; it
    is never recomputed here.

    Transaction shape: the provider network call (up to minutes with fallbacks
    and the repair re-ask) runs **outside** any transaction — holding the WAL
    write lock across it starves every other writer (cockpit edits, imports)
    into "database is locked". The invariant that matters is preserved: the
    translation row, memory write, discovered candidates, and the ``translated``
    status commit together in one transaction. If the process dies between the
    ``in_progress`` marker and the result commit, ``reset_in_progress_segments``
    reclaims the segment on the next run; an unexpected in-flight exception
    restores the segment's prior status before propagating.

    Args:
        connection: Open writable SQLite connection.
        segment: Stored segment row being translated.
        source_text: Raw source text handed to the provider.
        normalized_source_text: Normalized source text for glossary matching and
            the provider request.
        project: Owning project (supplies source/target languages).
        glossary_terms: Approved glossary terms for the project.
        honorific_policy: One of `preserve` | `localize` | `hybrid`.
        provider: Built, healthchecked provider.
        provider_model: Model name recorded with the attempt.
        characters: Project character contexts injected into the prompt.
        use_translation_memory: When True, reuse an exact memory match instead of
            calling the provider. Callers pass False for explicit retranslate so
            a fresh provider call is made (the memory is still refreshed on
            success).
        persist_raw_response: When True, store the provider's raw response on the
            translation row. Defaults False (QF-07 / SD-9): the verbose raw
            response is dropped unless ``[logging].raw_response_logging`` opts in,
            so raw provider payloads do not accumulate by default.

    Returns:
        A :class:`SegmentTranslationOutcome`. ``reused_from_memory`` is True only
        when the result came from translation memory (no provider call, no token
        cost). Tokens are the segment's total spend (primary + repair re-ask);
        None on failure or a memory hit.
    """

    with transaction(connection):
        update_segment_status(connection, segment_id=segment.id, status="in_progress")

    settled = False
    try:
        if use_translation_memory:
            remembered = lookup_translation_memory(
                connection, project_id=project.id, source_hash=segment.source_hash
            )
            if remembered is not None:
                with transaction(connection):
                    record_translation(
                        connection,
                        segment_id=segment.id,
                        text=remembered.target_text,
                        source_hash=segment.source_hash,
                        provider=MEMORY_PROVIDER,
                        model=MEMORY_MODEL,
                    )
                    update_segment_status(connection, segment_id=segment.id, status="translated")
                settled = True
                return SegmentTranslationOutcome(
                    translated=True, reused_from_memory=True, input_tokens=None, output_tokens=None
                )

        previous_segments = list_previous_translated_segments(
            connection,
            chapter_id=segment.chapter_id,
            before_block_order=segment.block_order,
            limit=MAX_CONTEXT_SEGMENTS,
        )
        context = build_context(
            normalized_source_text=normalized_source_text,
            glossary_terms=glossary_terms,
            previous_segments=previous_segments,
            honorific_policy=honorific_policy,
            characters=characters,
            profile=profile,
        )
        banned_phrases = profile.banned_phrases if profile is not None else ()
        # Primary + ordered fallbacks (ADR 018 D4). Try each in turn; on a
        # provider failure, cold-mark that engine for a short window and advance.
        # No circuit breaker (D9) — just a simple try-next. If every candidate is
        # currently cold, try them anyway rather than failing the segment blind.
        candidates: list[tuple[LLMProvider, str]] = [(provider, provider_model), *fallbacks]
        now = time.monotonic()
        warm = [c for c in candidates if cold is None or not cold.is_cold(c[0].name, now=now)]
        for cand_provider, cand_model in warm or candidates:
            request = TranslationRequest(
                segment_id=segment.id,
                source_text=source_text,
                normalized_source_text=normalized_source_text,
                source_language=project.source_lang,
                target_language=project.target_lang,
                context=context,
                provider_model=cand_model,
            )
            try:
                response = cand_provider.translate(request)
            except ProviderError:
                if cold is not None:
                    cold.mark(cand_provider.name, now + _FALLBACK_COLD_SECONDS)
                continue

            # Enforcement gate (ADR 019 E1+E2): glossary/character/anti-slop must
            # bind. Detection always runs (free, deterministic) so the verdict is
            # persisted with the attempt (audit A4a); `enforce_repair` gates only
            # the token-costing repair re-ask. Never blocks — the committed text
            # is the best attempt and any residual violation stays visible in the
            # QA report and the attempt history.
            final = response
            verdict = evaluate_translation(
                segment_id=segment.id,
                source_text=source_text,
                normalized_source_text=normalized_source_text,
                translation_text=response.translation,
                glossary_terms=glossary_terms,
                characters=characters,
                banned_phrases=banned_phrases,
            )
            # Violations describing the *committed* text (may improve on repair).
            final_violations = verdict.violations
            repair_attempted = False
            repair_outcome: str | None = None
            repair_input_tokens: int | None = None
            repair_output_tokens: int | None = None
            if enforce_repair and not verdict.ok:
                repair_attempted = True
                repaired = _try_repair(
                    cand_provider,
                    source_text=source_text,
                    previous_translation=response.translation,
                    violations=verdict.violations,
                    source_language=project.source_lang,
                    target_language=project.target_lang,
                )
                if repaired is None:
                    repair_outcome = "failed"
                else:
                    # The repair was spent regardless of outcome; record its cost.
                    repair_input_tokens = repaired.input_tokens
                    repair_output_tokens = repaired.output_tokens
                    recheck = evaluate_translation(
                        segment_id=segment.id,
                        source_text=source_text,
                        normalized_source_text=normalized_source_text,
                        translation_text=repaired.translation,
                        glossary_terms=glossary_terms,
                        characters=characters,
                        banned_phrases=banned_phrases,
                    )
                    # Keep the repaired attempt unless it is strictly worse than
                    # the original (a targeted fix that regressed is discarded).
                    if len(recheck.violations) <= len(verdict.violations):
                        final = repaired
                        final_violations = recheck.violations
                        repair_outcome = "accepted"
                    else:
                        repair_outcome = "discarded"
            spent_input = (response.input_tokens or 0) + (repair_input_tokens or 0)
            spent_output = (response.output_tokens or 0) + (repair_output_tokens or 0)

            # Result + memory + candidates + status commit atomically. The row
            # keeps the primary call's tokens; the repair spend goes in its own
            # columns so sum(rows) reconciles with the run summary (audit A5).
            with transaction(connection):
                record_translation(
                    connection,
                    segment_id=segment.id,
                    text=final.translation,
                    source_hash=segment.source_hash,
                    provider=cand_provider.name,
                    model=cand_model,
                    raw_response=final.raw_response if persist_raw_response else None,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    enforcement_violations=final_violations,
                    repair_attempted=repair_attempted,
                    repair_outcome=repair_outcome,
                    repair_input_tokens=repair_input_tokens,
                    repair_output_tokens=repair_output_tokens,
                )
                save_translation_memory(
                    connection,
                    project_id=project.id,
                    source_text=normalized_source_text,
                    source_hash=segment.source_hash,
                    target_text=final.translation,
                    provider=cand_provider.name,
                    model=cand_model,
                    protect_manual=True,
                )
                # Recover the model's self-reported uncertain terms as discovered
                # glossary candidates (ADR 019 E4) — free entity discovery, no extra
                # model call. Idempotent + non-intrusive; the user reviews them later.
                for uncertain_term in final.uncertain_terms:
                    record_uncertain_glossary_candidate(
                        connection, project_id=project.id, source=uncertain_term
                    )
                update_segment_status(connection, segment_id=segment.id, status="translated")
            settled = True
            return SegmentTranslationOutcome(
                translated=True,
                reused_from_memory=False,
                input_tokens=spent_input,
                output_tokens=spent_output,
                repair_call_made=repair_attempted,
                json_repair_used=response.json_repair_used,
            )

        with transaction(connection):
            update_segment_status(connection, segment_id=segment.id, status="failed")
        settled = True
        return SegmentTranslationOutcome(
            translated=False, reused_from_memory=False, input_tokens=None, output_tokens=None
        )
    finally:
        if not settled:
            # An unexpected exception (e.g. ParserError) is propagating: put the
            # segment back to its pre-run status so it is not stranded
            # ``in_progress``. Best-effort — if this write itself cannot commit,
            # ``reset_in_progress_segments`` reclaims the segment on the next run.
            with contextlib.suppress(sqlite3.Error), transaction(connection):
                update_segment_status(
                    connection,
                    segment_id=segment.id,
                    # The record's status came from the DB and its CHECK
                    # constraint, so the narrowing is safe.
                    status=cast(SegmentStatus, segment.status),
                )


def _try_repair(
    provider: LLMProvider,
    *,
    source_text: str,
    previous_translation: str,
    violations: tuple[str, ...],
    source_language: str,
    target_language: str,
) -> TranslationResponse | None:
    """One bounded enforcement-repair re-ask; None when it fails (keep the original).

    The repair is best-effort on an already-successful translation: any failure —
    a provider error, unparseable output, or a provider that does not implement the
    ``complete()`` primitive (``NotImplementedError``) — must never lose the good
    primary translation. The caller commits the original attempt and the residual
    violation stays visible in the QA report (never blocked, never substituted).
    """

    try:
        return repair_translation(
            provider,
            source_text=source_text,
            previous_translation=previous_translation,
            violations=violations,
            source_language=source_language,
            target_language=target_language,
        )
    except (ProviderError, ParserError, NotImplementedError):
        return None


def enforce_repair_enabled(config: dict[str, Any]) -> bool:
    """Read ``[translation] enforce_repair`` (default True — ADR 019 §6).

    Detection always runs; this flag only gates the token-costing repair re-ask.
    """
    translation_config = config.get("translation", {})
    if not isinstance(translation_config, dict):
        return True
    return bool(translation_config.get("enforce_repair", True))


def build_translation_profile(config: dict[str, Any]) -> TranslationProfile | None:
    """Build the project's ``[translation_profile]`` style contract (ADR 019 E3).

    Returns ``None`` when the section is absent (no behavior change). When present,
    ``banned_phrases`` defaults to the shipped seed; ``[]`` disables it and a custom
    array replaces it (the seed only applies once a profile is declared).
    """
    raw = config.get("translation_profile")
    if not isinstance(raw, dict):
        return None
    banned = raw.get("banned_phrases")
    if banned is None:
        banned_phrases = DEFAULT_BANNED_PHRASES
    elif isinstance(banned, list):
        banned_phrases = tuple(str(phrase) for phrase in banned)
    else:
        banned_phrases = ()
    return TranslationProfile(
        tone=_clean_profile_field(raw.get("tone")),
        dialog_style=_clean_profile_field(raw.get("dialog_style")),
        name_rendering=_clean_profile_field(raw.get("name_rendering")),
        tense=_clean_profile_field(raw.get("tense")),
        banned_phrases=banned_phrases,
    )


def _clean_profile_field(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def raw_response_logging_enabled(config: dict[str, Any]) -> bool:
    """Read ``[logging].raw_response_logging`` (default False — QF-07 / SD-9).

    When disabled (the default), the provider's verbose raw response is not
    persisted on translation rows, so raw payloads do not accumulate.
    """
    logging_config = config.get("logging", {})
    if not isinstance(logging_config, dict):
        return False
    return bool(logging_config.get("raw_response_logging", False))


def _load_single_project(connection: sqlite3.Connection) -> ProjectRecord:
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ConfigError(
            "Project database has no project row. "
            "Likely cause: database was not initialized by `weaver init`. "
            "Next command: run `weaver init <input.epub>`."
        )
    return get_project(connection, int(row["id"]))


def _source_volume_id(connection: sqlite3.Connection, *, project_id: int, source_path: Path) -> int:
    """Resolve the volume the translate source belongs to.

    Translate re-reads the project's single ``source_file`` and re-syncs it; that
    file maps to one volume. Match by source path, falling back to the first
    volume (legacy single-source projects always have one after migration).
    """

    volumes = list_volumes(connection, project_id)
    if not volumes:
        raise ConfigError(
            "Project has no volume to translate. "
            "Likely cause: database predates the volume model and was not migrated. "
            "Next command: run `weaver inspect <project.toml>` to migrate, then retry."
        )
    target = str(source_path)
    return next((volume.id for volume in volumes if volume.source_path == target), volumes[0].id)


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
