"""Typer entry point for the `weaver` command."""

from __future__ import annotations

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
from weaver.errors import WeaverError
from weaver.providers import ProviderStatus
from weaver.services.project import initialize_project, inspect_project
from weaver.services.translation import translate_project
from weaver.storage.segments import SegmentRecord

app = typer.Typer(
    name="weaver",
    help="Offline-capable, glossary-aware JP-EN novel translation workbench.",
    no_args_is_help=True,
    add_completion=False,
)
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
    typer.echo("")
    typer.echo("Next:")
    typer.echo(f"  weaver inspect {result.project_toml}")


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
    raise typer.Exit(code=1) from error


if __name__ == "__main__":
    app()
