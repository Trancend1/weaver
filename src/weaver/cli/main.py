"""Typer entry point for the `weaver` command."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from weaver import __version__
from weaver.errors import WeaverError
from weaver.services.project import initialize_project, inspect_project

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
def inspect_project_command(project_toml: Path) -> None:
    """Show project status."""

    try:
        summary = inspect_project(project_toml)
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
    console.print(table)


def _exit_with_error(error: WeaverError) -> None:
    typer.echo(str(error), err=True)
    raise typer.Exit(code=1) from error


if __name__ == "__main__":
    app()
