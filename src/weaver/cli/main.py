"""Typer entry point for the `weaver` command."""

from __future__ import annotations

import os
import sys
import tomllib
from contextlib import closing
from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from weaver import __version__
from weaver.errors import GlossaryConflictError, WeaverError
from weaver.providers import ProviderStatus
from weaver.services.export import export_markdown_project
from weaver.services.glossary import sync_glossary_tsv_to_database
from weaver.services.project import initialize_project, inspect_project
from weaver.services.translation import translate_project
from weaver.storage.db import connect_database, transaction
from weaver.storage.glossary import (
    GlossaryCandidateRecord,
    approve_glossary_candidate,
    count_glossary_candidates_by_status,
    edit_glossary_candidate,
    get_pending_glossary_candidate,
    list_glossary_conflicts,
    reject_glossary_candidate,
    restore_glossary_candidate,
)
from weaver.storage.projects import get_project
from weaver.storage.segments import SegmentRecord

app = typer.Typer(
    name="weaver",
    help="Offline-capable, glossary-aware JP-EN novel translation workbench.",
    no_args_is_help=True,
    add_completion=False,
)
glossary_app = typer.Typer(help="Review and edit glossary candidates.")
app.add_typer(glossary_app, name="glossary")
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"weaver {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Weaver CLI root."""


@app.command("init")
def init_project(input_epub: Path) -> None:
    """Create a Weaver project from an EPUB."""

    try:
        result = initialize_project(input_epub)
    except WeaverError as exc:
        _exit_with_error(exc)

    typer.echo(f"Reading {input_epub}...")
    typer.echo(f"Created: {result.project_toml}")
    typer.echo(f"Database: {result.database_path}")
    typer.echo(f"Detected: {result.chapter_count} chapters, {result.segment_count} segments")
    typer.echo(
        f"Extracted {result.glossary_candidate_count} glossary candidates -> "
        f"{result.glossary_candidate_path}"
    )
    typer.echo("")
    typer.echo("Next:")
    typer.echo(f"  weaver glossary review {result.project_toml}")


@app.command("inspect")
def inspect_project_command(
    project_toml: Path,
    healthcheck: bool = typer.Option(
        False,
        "--healthcheck",
        "-H",
        help="Probe the configured provider for availability (makes a network call).",
    ),
) -> None:
    """Show project status."""

    try:
        summary = inspect_project(project_toml, run_healthcheck=healthcheck)
    except WeaverError as exc:
        _exit_with_error(exc)

    table = Table(title=f"Weaver Project: {summary.project_name}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Source", summary.source_file)
    table.add_row("Provider", f"{summary.provider} / {summary.model}")
    table.add_row("Chapters", str(summary.chapter_count))
    table.add_row("Segments", str(summary.segment_count))
    table.add_row("Pending", str(summary.pending_count))
    table.add_row("Translated", str(summary.translated_count))
    table.add_row("Failed", str(summary.failed_count))
    table.add_row("Stale", str(summary.stale_count))
    table.add_row("Glossary Candidates", str(summary.glossary_candidate_count))
    table.add_row("Glossary Terms", str(summary.glossary_term_count))
    table.add_row("Output", summary.output_dir)
    if summary.provider_status is not None:
        table.add_row("Healthcheck", _format_healthcheck(summary.provider_status))
    console.print(table)


@app.command("translate")
def translate_project_command(
    project_toml: Path,
    retry_failed: bool = typer.Option(
        False,
        "--retry-failed",
        "-r",
        help="Retry failed segments instead of translating pending segments.",
    ),
) -> None:
    """Translate project segments through the configured provider."""

    try:
        with Progress(
            TextColumn("Translating"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task_id: TaskID | None = None

            def advance(
                current: int, total: int, segment: SegmentRecord, _translated: bool
            ) -> None:
                nonlocal task_id
                if task_id is None:
                    task_id = progress.add_task("segments", total=total)
                progress.update(
                    task_id,
                    completed=current,
                    description=f"Segment {segment.id}",
                )

            summary = translate_project(
                project_toml,
                retry_failed=retry_failed,
                progress_callback=advance,
            )
    except WeaverError as exc:
        _exit_with_error(exc)

    typer.echo(f"Selected: {summary.selected_segments}")
    typer.echo(f"Translated: {summary.translated_segments}")
    typer.echo(f"Failed: {summary.failed_segments}")
    typer.echo(f"Pending: {summary.pending_segments}")
    typer.echo(f"Stale: {summary.stale_segments}")
    if summary.input_tokens or summary.output_tokens:
        typer.echo(f"Tokens: input {summary.input_tokens} | output {summary.output_tokens}")


@app.command("export")
def export_project_command(
    project_toml: Path,
    mode: str = typer.Option(
        "markdown",
        "--mode",
        help="Export mode. MVP-0 currently supports markdown.",
    ),
    translation_only: bool = typer.Option(
        False,
        "--translation-only",
        help="Omit source text from Markdown review files.",
    ),
) -> None:
    """Export review or reader artifacts."""

    if mode != "markdown":
        typer.echo(
            "Unsupported export mode. Likely cause: only markdown export is implemented. "
            "Next command: run `weaver export <project.toml> --mode markdown`.",
            err=True,
        )
        raise typer.Exit(code=1)
    try:
        result = export_markdown_project(
            project_toml,
            translation_only=translation_only,
        )
    except WeaverError as exc:
        _exit_with_error(exc)

    typer.echo(f"Wrote {result.index_path}")
    typer.echo(f"Chapters: {len(result.chapter_paths)}")


@glossary_app.command("review")
def glossary_review_command(project_toml: Path) -> None:
    """Interactively approve, edit, reject, or skip glossary candidates."""

    try:
        _run_glossary_review(project_toml)
    except WeaverError as exc:
        _exit_with_error(exc)


@glossary_app.command("edit")
def glossary_edit_command(project_toml: Path) -> None:
    """Open glossary TSV in $EDITOR and sync reviewed rows."""

    try:
        count = sync_glossary_tsv_to_database(
            project_toml,
            editor=os.environ.get("EDITOR"),
        )
    except WeaverError as exc:
        _exit_with_error(exc)
    typer.echo(f"Synced {count} glossary TSV rows.")


@glossary_app.command("conflicts")
def glossary_conflicts_command(project_toml: Path) -> None:
    """Show approved glossary target conflicts."""

    try:
        db_path = _database_path_from_project(project_toml)
        with closing(connect_database(db_path)) as connection:
            project = _load_single_project(connection)
            conflicts = list_glossary_conflicts(connection, project_id=project.id)
    except WeaverError as exc:
        _exit_with_error(exc)

    if not conflicts:
        typer.echo("No glossary conflicts.")
        return
    for source, targets in conflicts:
        _safe_echo(f"{source}: {', '.join(targets)}")


def _run_glossary_review(project_toml: Path) -> None:
    db_path = _database_path_from_project(project_toml)
    undo_snapshot: GlossaryCandidateRecord | None = None

    with closing(connect_database(db_path)) as connection:
        project = _load_single_project(connection)
        while True:
            counts = count_glossary_candidates_by_status(connection, project_id=project.id)
            pending = counts.get("pending", 0)
            approved = counts.get("approved", 0) + counts.get("edited", 0)
            rejected = counts.get("rejected", 0)
            typer.echo(f"Pending: {pending}  Approved: {approved}  Rejected: {rejected}")

            candidate = get_pending_glossary_candidate(connection, project_id=project.id)
            if candidate is None:
                typer.echo("No pending glossary candidates.")
                return

            _print_candidate(candidate)
            action = (
                typer.prompt(
                    "[a]pprove [e]dit [r]eject [s]kip [u]ndo [q]uit ?",
                    default="q",
                )
                .strip()
                .lower()
            )

            if action == "q":
                typer.echo("Review progress saved.")
                return
            if action == "s":
                typer.echo("Skipped")
                continue
            if action == "u":
                if undo_snapshot is None:
                    typer.echo("Nothing to undo")
                    continue
                with transaction(connection):
                    restore_glossary_candidate(connection, candidate=undo_snapshot)
                typer.echo("Undone")
                undo_snapshot = None
                continue

            undo_snapshot = candidate
            with transaction(connection):
                if action == "a":
                    approve_glossary_candidate(connection, candidate_id=candidate.id)
                    typer.echo("Approved")
                elif action == "r":
                    reject_glossary_candidate(connection, candidate_id=candidate.id)
                    typer.echo("Rejected")
                elif action == "e":
                    target = typer.prompt("Target", default=candidate.target or candidate.source)
                    notes = typer.prompt("Notes", default=candidate.notes or "")
                    edit_glossary_candidate(
                        connection,
                        candidate_id=candidate.id,
                        target=target,
                        notes=notes or None,
                    )
                    typer.echo("Edited")
                else:
                    typer.echo("Unknown action")
                    undo_snapshot = None


def _print_candidate(candidate: GlossaryCandidateRecord) -> None:
    typer.echo("")
    _safe_echo(f"Source: {candidate.source}")
    _safe_echo(f"Candidate target: {candidate.target or candidate.source}")
    _safe_echo(f"Category: {candidate.category or '-'}")
    _safe_echo(f"Frequency: {candidate.frequency}")
    if candidate.notes:
        _safe_echo(f"Notes: {candidate.notes}")


def _safe_echo(text: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    typer.echo(safe)


def _database_path_from_project(project_toml: Path) -> Path:
    data = tomllib.loads(project_toml.read_text(encoding="utf-8"))
    path = Path(str(data["project"]["database_path"]))
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    return project_toml.parent / path


def _load_single_project(connection):
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        from weaver.errors import ConfigError

        raise ConfigError(
            "Project database has no project row. "
            "Likely cause: database was not initialized by `weaver init`. "
            "Next command: run `weaver init <input.epub>`."
        )
    return get_project(connection, int(row["id"]))


def _format_healthcheck(status: ProviderStatus) -> str:
    state = "healthy" if status.healthy else "unhealthy"
    parts = [state]
    if status.latency_ms is not None:
        parts.append(f"{status.latency_ms} ms")
    if status.message:
        parts.append(status.message)
    return " — ".join(parts)


def _exit_with_error(error: WeaverError) -> NoReturn:
    typer.echo(str(error), err=True)
    code = 6 if isinstance(error, GlossaryConflictError) else 1
    raise typer.Exit(code=code) from error


if __name__ == "__main__":
    app()
