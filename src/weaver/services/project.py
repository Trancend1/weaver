"""Project initialization and inspection services."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver.core.config import load_project_config
from weaver.core.templates import get_template
from weaver.errors import ConfigError, ProjectNotFoundError, ProviderError, WeaverError
from weaver.providers import ProviderStatus, build_provider
from weaver.services.import_source import import_volume
from weaver.services.logging_setup import log_runtime_event
from weaver.storage.db import (
    SCHEMA_VERSION,
    connect_readonly_database,
    initialize_database,
    transaction,
)
from weaver.storage.projects import create_project


@dataclass(frozen=True)
class InitResult:
    """Result returned after creating a Weaver project."""

    project_name: str
    project_toml: Path
    database_path: Path
    chapter_count: int
    segment_count: int
    glossary_candidate_count: int
    glossary_candidate_path: Path


@dataclass(frozen=True)
class InspectSummary:
    """Read-only project status summary."""

    project_name: str
    source_file: str
    provider: str
    model: str
    volume_count: int
    chapter_count: int
    segment_count: int
    pending_count: int
    translated_count: int
    failed_count: int
    stale_count: int
    glossary_candidate_count: int
    glossary_term_count: int
    output_dir: str
    provider_status: ProviderStatus | None = None
    uuid: str | None = None
    schema_version: int = 0


def project_exists(source_epub: Path, *, cwd: Path | None = None) -> bool:
    """Check whether a Weaver project already exists for this EPUB.

    Args:
        source_epub: Input EPUB path.
        cwd: Working directory used for generated project paths.

    Returns:
        True when the target ``project.toml`` already exists on disk.
    """

    base_dir = cwd or Path.cwd()
    project_name = source_epub.resolve().stem
    project_toml = base_dir / ".weaver" / project_name / "project.toml"
    return project_toml.exists()


def project_name_exists(project_name: str, *, cwd: Path | None = None) -> bool:
    """Check whether a Weaver project already exists for a project name."""

    base_dir = cwd or Path.cwd()
    project_toml = base_dir / ".weaver" / project_name / "project.toml"
    return project_toml.exists()


def delete_project(project_toml: Path) -> None:
    """Permanently delete a Weaver project's ``.weaver/<name>`` directory.

    Removes the cockpit-managed state for one project: ``project.toml``, the
    SQLite database, glossary TSVs, and the ``output`` directory. The original
    imported source file is **not** touched — it lives outside ``.weaver``.

    Args:
        project_toml: Path to the project's ``project.toml``.

    Raises:
        ProjectNotFoundError: The ``project.toml`` does not exist.
        WeaverError: The path is not a ``.weaver/<name>/project.toml`` layout —
            a safety guard against removing an unexpected directory.
    """

    project_dir = project_toml.parent
    if project_toml.name != "project.toml" or project_dir.parent.name != ".weaver":
        raise WeaverError(
            f"Refusing to delete {project_dir}: not a .weaver project directory. "
            "Likely cause: an unexpected project path. "
            "Next command: verify the project name and try again."
        )
    if not project_toml.is_file():
        raise ProjectNotFoundError(
            f"No project found at {project_toml}. "
            "Likely cause: it was already deleted or never created. "
            "Next command: run `weaver inspect` to list known projects."
        )
    shutil.rmtree(project_dir)
    log_runtime_event("project.deleted", project=project_dir.name)


DEFAULT_PROVIDER = ""


def initialize_project(
    source_epub: Path | None = None,
    *,
    cwd: Path | None = None,
    template: str | None = None,
    provider: str | None = None,
    project_name: str | None = None,
) -> InitResult:
    """Create project state, optionally importing an initial source as a volume.

    Args:
        source_epub: Optional input source path for backward-compatible first-volume import.
        cwd: Working directory used for generated project paths.
        template: Optional template preset name (``light-novel``,
            ``web-novel``, ``aozora-classic``). Overrides ``[glossary]``
            and ``[qa]`` sections in the generated ``project.toml``.
        provider: Optional free-form provider type/engine label for the generated
            ``[provider]`` table. New projects default to an empty provider config;
            users fill protocol, endpoint, model, and key env from Config.

    Returns:
        InitResult with created project locations and counts.
    """

    provider_type = provider or DEFAULT_PROVIDER

    base_dir = cwd or Path.cwd()
    source_path = source_epub.resolve() if source_epub is not None else None
    resolved_project_name = project_name or (source_path.stem if source_path is not None else None)
    if not resolved_project_name:
        raise ConfigError(
            "Project name is required. "
            "Likely cause: empty project creation needs a title. "
            "Next command: run `weaver init <project-name>` or choose a project name "
            "in the cockpit."
        )
    project_dir = base_dir / ".weaver" / resolved_project_name
    output_dir = project_dir / "output"
    candidate_path = project_dir / "glossary_candidates.tsv"
    db_path = project_dir / "weaver.db"
    project_toml = project_dir / "project.toml"

    project_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    with closing(initialize_database(db_path)) as connection:
        with transaction(connection):
            create_project(
                connection,
                name=resolved_project_name,
                source_path=str(source_path) if source_path is not None else "",
                source_lang="ja",
                target_lang="en",
            )
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    template_overrides = get_template(template) if template else None
    _write_project_toml(
        project_toml,
        project_name=resolved_project_name,
        source_file=str(source_path) if source_path is not None else "",
        project_dir=_posix_relative(project_dir, base_dir),
        database_path=_posix_relative(db_path, base_dir),
        output_dir=_posix_relative(output_dir, base_dir),
        provider_type=provider_type,
        template_overrides=template_overrides,
    )
    if source_path is not None:
        volume_result = import_volume(project_toml, source_path, cwd=base_dir)
        chapter_count = volume_result.chapter_count
        segment_count = volume_result.segment_count
        glossary_candidate_count = volume_result.glossary_candidate_count
        glossary_candidate_path = candidate_path
    else:
        chapter_count = 0
        segment_count = 0
        glossary_candidate_count = 0
        glossary_candidate_path = candidate_path
    log_runtime_event(
        "project.created",
        project=resolved_project_name,
        chapters=chapter_count,
        segments=segment_count,
        glossary_candidates=glossary_candidate_count,
        provider=provider_type,
    )
    return InitResult(
        project_name=resolved_project_name,
        project_toml=project_toml,
        database_path=db_path,
        chapter_count=chapter_count,
        segment_count=segment_count,
        glossary_candidate_count=glossary_candidate_count,
        glossary_candidate_path=glossary_candidate_path,
    )


def inspect_project(
    project_toml: Path,
    *,
    cwd: Path | None = None,
    run_healthcheck: bool = False,
) -> InspectSummary:
    """Read project status without mutating the database.

    Args:
        project_toml: Path to a Weaver project.toml file.
        cwd: Working directory used to resolve generated project paths.
        run_healthcheck: When true, instantiate the configured provider and
            call `healthcheck()`. Plain inspect (the default) stays offline.

    Returns:
        InspectSummary with project counts and optional provider status.
    """

    base_dir = cwd or Path.cwd()
    data = load_project_config(project_toml)
    project = data["project"]
    provider = data["provider"]
    db_path = _resolve_path(str(project["database_path"]), base_dir, project_toml.parent)

    with closing(connect_readonly_database(db_path)) as connection:
        counts = _read_counts(connection)
        schema_version, project_uuid = _read_identity(connection)

    status = _run_provider_healthcheck(provider) if run_healthcheck else None

    return InspectSummary(
        project_name=str(project["name"]),
        source_file=str(project["source_file"]),
        provider=str(provider["type"]),
        model=str(provider["model"]),
        volume_count=counts["volumes"],
        chapter_count=counts["chapters"],
        segment_count=counts["segments"],
        pending_count=counts["pending"],
        translated_count=counts["translated"],
        failed_count=counts["failed"],
        stale_count=counts["stale"],
        glossary_candidate_count=counts["glossary_candidates"],
        glossary_term_count=counts["glossary_terms"],
        output_dir=str(project["output_dir"]),
        provider_status=status,
        uuid=project_uuid,
        schema_version=schema_version,
    )


def _run_provider_healthcheck(provider_config: dict[str, Any]) -> ProviderStatus:
    provider_type = str(provider_config.get("type", ""))
    model = str(provider_config.get("model", ""))
    try:
        provider = build_provider(provider_config)
    except WeaverError as exc:
        return ProviderStatus(
            healthy=False,
            provider_name=provider_type,
            model=model,
            message=str(exc),
            latency_ms=None,
        )
    try:
        return provider.healthcheck()
    except ProviderError as exc:
        return ProviderStatus(
            healthy=False,
            provider_name=provider_type,
            model=model,
            message=str(exc),
            latency_ms=None,
        )
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            close()


def _write_project_toml(
    path: Path,
    *,
    project_name: str,
    source_file: str,
    project_dir: str,
    database_path: str,
    output_dir: str,
    provider_type: str = DEFAULT_PROVIDER,
    template_overrides: dict[str, dict[str, object]] | None = None,
) -> None:
    glossary_defaults: dict[str, object] = {
        "require_review": True,
        "max_terms_per_segment": 20,
    }
    qa_defaults: dict[str, object] = {
        "detect_untranslated_japanese": True,
        "detect_empty_output": True,
        "detect_glossary_mismatch": True,
        "minimum_length_ratio": 0.3,
    }
    if template_overrides:
        glossary_defaults.update(template_overrides.get("glossary", {}))
        qa_defaults.update(template_overrides.get("qa", {}))

    provider_lines = _provider_lines(provider_type)
    provider_section = "\n".join(provider_lines)

    content = f"""[project]
name = "{project_name}"
source_file = "{_escape_toml(source_file)}"
project_dir = "{project_dir}"
database_path = "{database_path}"
output_dir = "{output_dir}"
schema_version = {SCHEMA_VERSION}

[languages]
source = "ja"
target = "en"

{provider_section}

[translation]
quality = "balanced"
honorifics = "preserve"
context_window_segments = 5
timeout_seconds = 180
max_retries = 2

[glossary]
candidate_path = "{project_dir}/glossary_candidates.tsv"
approved_path = "{project_dir}/glossary.tsv"
require_review = {_toml_bool(glossary_defaults["require_review"])}
max_terms_per_segment = {glossary_defaults["max_terms_per_segment"]}

[output]
default_mode = "markdown"
epub_enabled = true

[qa]
detect_untranslated_japanese = {_toml_bool(qa_defaults["detect_untranslated_japanese"])}
detect_empty_output = {_toml_bool(qa_defaults["detect_empty_output"])}
detect_glossary_mismatch = {_toml_bool(qa_defaults["detect_glossary_mismatch"])}
minimum_length_ratio = {qa_defaults["minimum_length_ratio"]}

[logging]
level = "info"
raw_response_logging = false
"""
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as file:
        temp_path = Path(file.name)
        file.write(content)
    temp_path.replace(path)


def _provider_lines(provider_type: str) -> list[str]:
    if provider_type == "fake":
        return [
            "[provider]",
            'type = "custom"',
            'protocol = "fake"',
            'model = "fake-1"',
            'base_url = ""',
            'api_key_env = ""',
        ]
    return [
        "[provider]",
        f'type = "{_escape_toml(provider_type)}"',
        'protocol = ""',
        'model = ""',
        'base_url = ""',
        'api_key_env = ""',
    ]


def _read_counts(connection: sqlite3.Connection) -> dict[str, int]:
    status_counts = {
        str(row["status"]): int(row["count"])
        for row in connection.execute(
            "SELECT status, COUNT(*) AS count FROM segments GROUP BY status"
        ).fetchall()
    }
    return {
        "volumes": _count(connection, "volumes"),
        "chapters": _count(connection, "chapters"),
        "segments": _count(connection, "segments"),
        "pending": status_counts.get("pending", 0),
        "translated": status_counts.get("translated", 0),
        "failed": status_counts.get("failed", 0),
        "stale": status_counts.get("stale", 0),
        "glossary_candidates": _count(connection, "glossary_candidates"),
        "glossary_terms": _count(connection, "glossary_terms"),
    }


def _read_identity(connection: sqlite3.Connection) -> tuple[int, str | None]:
    """Read schema version and project uuid from an open readonly connection.

    Returns:
        Tuple of (schema_version, uuid_or_none).  uuid is None for databases
        at schema version < 10 where the ``uuid`` column does not exist.
    """

    version_row = connection.execute("PRAGMA user_version").fetchone()
    schema_version = int(version_row[0]) if version_row is not None else 0

    project_uuid: str | None = None
    if schema_version >= 10:
        row = connection.execute("SELECT uuid FROM projects ORDER BY id LIMIT 1").fetchone()
        if row is not None and row["uuid"] is not None:
            project_uuid = str(row["uuid"])

    return schema_version, project_uuid


def _count(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    return int(row["count"])


def _resolve_path(path_value: str, cwd: Path, project_toml_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    cwd_path = cwd / path
    if cwd_path.exists():
        return cwd_path
    return project_toml_dir / path


def _posix_relative(path: Path, start: Path) -> str:
    return Path(os.path.relpath(path, start)).as_posix()


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _toml_bool(value: object) -> str:
    return "true" if value else "false"
