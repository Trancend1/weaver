"""Glossary candidate extraction and review services."""

from __future__ import annotations

import csv
import re
import sqlite3
import subprocess
import tomllib
from collections import Counter
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.ir import DocumentIR
from weaver.errors import ConfigError, GlossaryConflictError
from weaver.storage.db import connect_database, transaction
from weaver.storage.glossary import (
    GlossaryCandidateRecord,
    insert_glossary_candidate,
    list_glossary_conflicts,
)
from weaver.storage.projects import get_project

KATAKANA_PATTERN = re.compile(r"[ァ-ヶー]{2,}(?:たち)?")
HONORIFIC_PATTERN = re.compile(r"([一-龯々ァ-ヶーA-Za-z0-9]{1,12})(?:さん|ちゃん|様)")
CJK_PATTERN = re.compile(r"[一-龯々]{2,8}(?:たち)?")
JAPANESE_FALLBACK_PATTERN = re.compile(r"[ぁ-んァ-ヶー一-龯々]{2,12}")
VARIANT_SUFFIXES = ("たち",)
TSV_FIELDS = ("source", "target", "category", "notes", "status", "frequency")


@dataclass(frozen=True)
class GlossaryCandidate:
    """Extracted glossary candidate before persistence."""

    source: str
    target: str | None
    category: str
    notes: str | None
    frequency: int
    examples: tuple[str, ...]


@dataclass(frozen=True)
class GlossaryExtractionResult:
    """Result of extracting and storing glossary candidates."""

    candidate_count: int
    candidate_path: Path


def extract_glossary_candidates(document: DocumentIR) -> list[GlossaryCandidate]:
    """Extract glossary candidates from a document.

    Uses optional MeCab/fugashi proper noun tokenization when available and a
    deterministic regex fallback for Windows or minimal environments.
    """

    counts: Counter[str] = Counter()
    categories: dict[str, str] = {}
    examples: dict[str, list[str]] = {}
    title_sources: set[str] = set()

    for chapter in document.chapters:
        chapter_title = chapter.title or ""
        for source, category in _extract_terms(chapter_title):
            title_sources.add(source)
            categories.setdefault(source, category)
        for block in chapter.blocks:
            for source, category in _extract_terms(block.normalized_source_text):
                counts[source] += 1
                categories.setdefault(source, category)
                bucket = examples.setdefault(source, [])
                if len(bucket) < 2:
                    bucket.append(block.source_text)

    selected = [source for source in counts if counts[source] >= 2 or source in title_sources]
    if not selected:
        fallback = _first_fallback_term(document)
        if fallback is not None:
            source, example = fallback
            counts[source] = max(counts[source], 1)
            categories.setdefault(source, "fallback")
            examples.setdefault(source, [example])
            selected = [source]

    return [
        GlossaryCandidate(
            source=source,
            target=source,
            category=categories.get(source, "fallback"),
            notes=None,
            frequency=counts[source],
            examples=tuple(examples.get(source, ())),
        )
        for source in sorted(selected, key=lambda item: (-counts[item], item))
    ]


def store_glossary_candidates(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    candidates: list[GlossaryCandidate],
) -> None:
    """Persist extracted glossary candidates."""

    connection.execute(
        "DELETE FROM glossary_candidates WHERE project_id = ? AND status = 'pending'",
        (project_id,),
    )
    for candidate in candidates:
        insert_glossary_candidate(
            connection,
            project_id=project_id,
            source=candidate.source,
            target=candidate.target,
            category=candidate.category,
            notes=candidate.notes,
            status="pending",
            frequency=candidate.frequency,
        )


def write_glossary_candidates_tsv(
    path: Path, candidates: Sequence[GlossaryCandidateRecord | GlossaryCandidate]
) -> None:
    """Write candidates to a reviewable TSV file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=TSV_FIELDS, delimiter="\t")
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {
                    "source": candidate.source,
                    "target": candidate.target or "",
                    "category": candidate.category or "",
                    "notes": candidate.notes or "",
                    "status": getattr(candidate, "status", "pending"),
                    "frequency": candidate.frequency,
                }
            )


def extract_and_store_project_glossary(
    *,
    connection: sqlite3.Connection,
    project_id: int,
    document: DocumentIR,
    candidate_path: Path,
) -> GlossaryExtractionResult:
    """Extract, persist, and export glossary candidates for one project."""

    candidates = extract_glossary_candidates(document)
    store_glossary_candidates(connection, project_id=project_id, candidates=candidates)
    write_glossary_candidates_tsv(candidate_path, candidates)
    return GlossaryExtractionResult(
        candidate_count=len(candidates),
        candidate_path=candidate_path,
    )


def raise_on_glossary_conflicts(connection: sqlite3.Connection, *, project_id: int) -> None:
    """Raise when approved glossary candidates disagree on a source."""

    conflicts = list_glossary_conflicts(connection, project_id=project_id)
    if not conflicts:
        return
    source, targets = conflicts[0]
    raise GlossaryConflictError(
        f"Glossary conflict for `{source}`: {', '.join(targets)}. "
        "Likely cause: approved candidates disagree on one source term. "
        "Next command: run `weaver glossary review <project.toml>` and reject or edit one entry."
    )


def sync_glossary_tsv_to_database(project_toml: Path, *, editor: str | None) -> int:
    """Open glossary TSV in an editor, then sync reviewed rows into SQLite."""

    if not editor:
        raise ConfigError(
            "Cannot open glossary TSV because EDITOR is not set. "
            "Likely cause: no editor command is configured in this shell. "
            "Next command: set EDITOR, for example `set EDITOR=notepad` on Windows."
        )

    base_dir = Path.cwd()
    data = tomllib.loads(project_toml.read_text(encoding="utf-8"))
    project_config = data["project"]
    glossary_config = data["glossary"]
    db_path = _resolve_path(str(project_config["database_path"]), base_dir, project_toml.parent)
    tsv_path = _resolve_path(str(glossary_config["candidate_path"]), base_dir, project_toml.parent)

    subprocess.run([editor, str(tsv_path)], check=True)

    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        with transaction(connection):
            rows = _read_tsv_rows(tsv_path)
            for row in rows:
                status = row["status"]
                if status not in {"approved", "edited", "rejected", "pending"}:
                    raise ConfigError(
                        f"Invalid glossary status `{status}` in TSV. "
                        "Likely cause: glossary_candidates.tsv was edited with an "
                        "unsupported status. "
                        "Next command: use pending, approved, edited, or rejected."
                    )
                insert_glossary_candidate(
                    connection,
                    project_id=project.id,
                    source=row["source"],
                    target=row["target"] or None,
                    category=row["category"] or None,
                    notes=row["notes"] or None,
                    status=status,  # type: ignore[arg-type]
                    frequency=int(row["frequency"] or "1"),
                )
        return len(rows)


def _extract_terms(text: str) -> list[tuple[str, str]]:
    terms: list[tuple[str, str]] = []
    terms.extend(_extract_fugashi_proper_nouns(text))
    for match in HONORIFIC_PATTERN.finditer(text):
        terms.append((_cluster_surface(match.group(1)), "honorific"))
    for match in KATAKANA_PATTERN.finditer(text):
        if text[match.end() : match.end() + 1] in {"様"}:
            continue
        if text[match.end() : match.end() + 3] in {"さん", "ちゃん"}:
            continue
        terms.append((_cluster_surface(match.group(0)), "katakana"))
    for match in CJK_PATTERN.finditer(text):
        terms.append((_cluster_surface(match.group(0)), "cjk"))
    return [(source, category) for source, category in terms if len(source) >= 2]


def _extract_fugashi_proper_nouns(text: str) -> list[tuple[str, str]]:
    try:
        from fugashi import Tagger  # type: ignore[import-not-found]
    except Exception:
        return []

    try:
        tagger = Tagger()
    except Exception:
        return []

    terms: list[tuple[str, str]] = []
    for token in tagger(text):
        feature = str(token.feature)
        if any(label in feature for label in ("人名", "地名", "組織名", "固有名詞")):
            terms.append((_cluster_surface(str(token.surface)), "proper_noun"))
    return terms


def _cluster_surface(source: str) -> str:
    for suffix in VARIANT_SUFFIXES:
        if source.endswith(suffix) and len(source) > len(suffix) + 1:
            return source[: -len(suffix)]
    return source


def _first_fallback_term(document: DocumentIR) -> tuple[str, str] | None:
    for chapter in document.chapters:
        texts = [chapter.title or "", *(block.normalized_source_text for block in chapter.blocks)]
        for text in texts:
            match = JAPANESE_FALLBACK_PATTERN.search(text)
            if match is not None:
                return match.group(0), text
    return None


def _read_tsv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return [dict(row) for row in csv.DictReader(file, delimiter="\t")]


def _load_single_project(connection: sqlite3.Connection):
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ConfigError(
            "Project database has no project row. "
            "Likely cause: database was not initialized by `weaver init`. "
            "Next command: run `weaver init <input.epub>`."
        )
    return get_project(connection, int(row["id"]))


def _resolve_path(path_value: str, cwd: Path, project_toml_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    cwd_path = cwd / path
    if cwd_path.exists():
        return cwd_path
    return project_toml_dir / path
