"""Typer entry point for the `weaver` command."""

from __future__ import annotations

import os
import sys
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
from weaver.errors import (
    ConfigError,
    EpubReadError,
    EpubWriteError,
    GlossaryConflictError,
    ProviderUnavailable,
    SegmentNotFoundError,
    WeaverError,
)
from weaver.providers import ProviderStatus
from weaver.services.doctor import DoctorReport, run_doctor
from weaver.services.export import export_epub_project, export_markdown_project
from weaver.services.glossary import sync_glossary_tsv_to_database
from weaver.services.glossary_review import (
    GlossaryReviewSession,
    list_project_glossary_conflicts,
    open_glossary_review_session,
)
from weaver.services.manual_edit import SegmentSelector, edit_segment, resolve_segment_id
from weaver.services.preview import PreviewBlock, preview_project
from weaver.services.project import initialize_project, inspect_project, project_exists
from weaver.services.qa import (
    ValidationReport,
    format_report_json,
    qa_report_schema,
    validate_project,
)
from weaver.services.translation import translate_project
from weaver.storage.glossary import GlossaryCandidateRecord
from weaver.storage.segments import SegmentRecord

app = typer.Typer(
    name="weaver",
    help="Offline-capable, glossary-aware JP-EN novel translation workbench.",
    no_args_is_help=True,
    add_completion=True,
)
glossary_app = typer.Typer(help="Review and edit glossary candidates.")
app.add_typer(glossary_app, name="glossary")
app.add_typer(glossary_app, name="gl", hidden=True)
console = Console()

_DEBUG_MODE = False


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
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Print full exception traceback on failure instead of the three-line user error.",
    ),
) -> None:
    """Weaver CLI root."""

    global _DEBUG_MODE
    _DEBUG_MODE = debug


@app.command(
    "init",
    epilog=(
        "Examples:\n  weaver init novel.epub\n  weaver init novel.epub --from-template light-novel"
    ),
)
def init_project(
    input_epub: Path,
    from_template: str | None = typer.Option(
        None,
        "--from-template",
        help="Apply a project template preset (light-novel, web-novel, aozora-classic).",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation when overwriting an existing project.",
    ),
) -> None:
    """Create a Weaver project from an EPUB."""

    if not yes and project_exists(input_epub):
        typer.confirm(
            f"Project already exists for {input_epub.name}. Overwrite?",
            abort=True,
        )

    try:
        result = initialize_project(input_epub, template=from_template)
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
    if from_template:
        typer.echo(f"Template: {from_template}")
    typer.echo("")
    typer.echo("Next:")
    typer.echo(f"  weaver glossary review {result.project_toml}")


@app.command(
    "new",
    epilog="Examples:\n  weaver new\n  weaver new --yes",
)
def new_project_command(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation before initialising the project.",
    ),
) -> None:
    """Interactively create a Weaver project via guided wizard."""

    from weaver.services.wizard import run_new_wizard

    try:
        answers = run_new_wizard()
    except WeaverError as exc:
        _exit_with_error(exc)

    if not yes:
        typer.confirm(
            f"Create project from {answers.epub_path.name} using {answers.provider}?",
            abort=True,
        )

    try:
        result = initialize_project(
            answers.epub_path,
            template=answers.template,
            cwd=answers.working_dir,
        )
    except WeaverError as exc:
        _exit_with_error(exc)

    typer.echo(f"Reading {answers.epub_path}...")
    typer.echo(f"Created: {result.project_toml}")
    typer.echo(f"Database: {result.database_path}")
    typer.echo(f"Detected: {result.chapter_count} chapters, {result.segment_count} segments")
    typer.echo(
        f"Extracted {result.glossary_candidate_count} glossary candidates -> "
        f"{result.glossary_candidate_path}"
    )
    if answers.template:
        typer.echo(f"Template: {answers.template}")
    typer.echo("")
    typer.echo("Next:")
    typer.echo(f"  weaver glossary review {result.project_toml}")


@app.command(
    "inspect",
    epilog=(
        "Examples:\n"
        "  weaver inspect .weaver/novel/project.toml\n"
        "  weaver inspect .weaver/novel/project.toml --healthcheck"
    ),
)
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
    table.add_row("Pending", _count_with_percent(summary.pending_count, summary.segment_count))
    table.add_row(
        "Translated", _count_with_percent(summary.translated_count, summary.segment_count)
    )
    table.add_row("Failed", _count_with_percent(summary.failed_count, summary.segment_count))
    table.add_row("Stale", _count_with_percent(summary.stale_count, summary.segment_count))
    table.add_row("Glossary Candidates", str(summary.glossary_candidate_count))
    table.add_row(
        "Glossary Terms",
        _count_with_percent(
            summary.glossary_term_count,
            summary.glossary_candidate_count,
            denominator_label="candidates",
        ),
    )
    table.add_row("Output", summary.output_dir)
    if summary.provider_status is not None:
        table.add_row("Healthcheck", _format_healthcheck(summary.provider_status))
    console.print(table)


def _count_with_percent(count: int, total: int, *, denominator_label: str | None = None) -> str:
    if total <= 0:
        return str(count)
    percent = round(100 * count / total, 1)
    if denominator_label:
        return f"{count} ({percent}% of {denominator_label})"
    return f"{count} ({percent}%)"


@app.command(
    "dashboard",
    epilog=(
        "Examples:\n"
        "  weaver dashboard .weaver/novel/project.toml\n"
        "  weaver dashboard .weaver/novel/project.toml --no-color"
    ),
)
def dashboard_command(
    project_toml: Path,
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable color output.",
    ),
) -> None:
    """Launch read-only TUI dashboard showing project status."""

    from weaver.tui.dashboard_app import run_dashboard

    try:
        run_dashboard(project_toml, no_color=no_color)
    except WeaverError as exc:
        _exit_with_error(exc)


@app.command(
    "translate",
    epilog=(
        "Examples:\n"
        "  weaver translate .weaver/novel/project.toml\n"
        "  weaver translate .weaver/novel/project.toml --provider gemini --dry-run"
    ),
)
def translate_project_command(
    project_tomls: list[Path] = typer.Argument(
        ...,
        help="One or more project files. Processed sequentially in argument order.",
    ),
    retry_failed: bool = typer.Option(
        False,
        "--retry-failed",
        "-r",
        help="Retry failed segments instead of translating pending segments.",
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        help="Override [provider] type for this run (deepseek|gemini|ollama|fake).",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Override [provider] model for this run.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Count segments and estimate input tokens without contacting the provider.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Echo per-segment token I/O alongside the progress bar.",
    ),
    first_n: int | None = typer.Option(
        None,
        "--first-N",
        help="Translate only the first N selected segments for a fast-fail sanity check.",
    ),
) -> None:
    """Translate project segments through the configured provider."""

    provider_override: dict[str, str] | None = None
    if provider is not None or model is not None:
        provider_override = {}
        if provider is not None:
            provider_override["type"] = provider
        if model is not None:
            provider_override["model"] = model

    for index, project_toml in enumerate(project_tomls, start=1):
        if len(project_tomls) > 1:
            typer.echo("")
            typer.echo(f"[{index}/{len(project_tomls)}] {project_toml}")
        _translate_one_project(
            project_toml,
            retry_failed=retry_failed,
            dry_run=dry_run,
            verbose=verbose,
            first_n=first_n,
            provider_override=provider_override,
        )


def _translate_one_project(
    project_toml: Path,
    *,
    retry_failed: bool,
    dry_run: bool,
    verbose: bool,
    first_n: int | None,
    provider_override: dict[str, str] | None,
) -> None:
    try:
        if dry_run:
            summary = translate_project(
                project_toml,
                retry_failed=retry_failed,
                dry_run=True,
                first_n=first_n,
                provider_override=provider_override,
            )
        else:
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
                    current: int,
                    total: int,
                    segment: SegmentRecord,
                    translated: bool,
                    input_tokens: int | None,
                    output_tokens: int | None,
                ) -> None:
                    nonlocal task_id
                    if task_id is None:
                        task_id = progress.add_task("segments", total=total)
                    progress.update(
                        task_id,
                        completed=current,
                        description=f"Segment {segment.id}",
                    )
                    if verbose and translated:
                        typer.echo(f"Segment {segment.id} <- in={input_tokens} out={output_tokens}")

                summary = translate_project(
                    project_toml,
                    retry_failed=retry_failed,
                    progress_callback=advance,
                    first_n=first_n,
                    provider_override=provider_override,
                )
    except WeaverError as exc:
        _exit_with_error(exc)

    if dry_run:
        typer.echo(
            f"Would translate {summary.selected_segments} segments. "
            f"Estimated input tokens: {summary.input_tokens}."
        )
        return

    typer.echo(f"Selected: {summary.selected_segments}")
    typer.echo(f"Translated: {summary.translated_segments}")
    typer.echo(f"Failed: {summary.failed_segments}")
    typer.echo(f"Pending: {summary.pending_segments}")
    typer.echo(f"Stale: {summary.stale_segments}")
    if summary.input_tokens or summary.output_tokens:
        typer.echo(f"Tokens: input {summary.input_tokens} | output {summary.output_tokens}")


@app.command(
    "edit",
    epilog=(
        "Examples:\n"
        "  weaver edit .weaver/novel/project.toml 8a3df9c64e0a7ce0\n"
        "  weaver edit .weaver/novel/project.toml --first-failed"
    ),
)
def edit_segment_command(
    project_toml: Path,
    segment_id: str | None = typer.Argument(
        None,
        help="Segment id to edit (omit when using --first-failed/--next-stale/--recent).",
    ),
    first_failed: bool = typer.Option(
        False,
        "--first-failed",
        help="Edit the earliest segment whose status is `failed`.",
    ),
    next_stale: bool = typer.Option(
        False,
        "--next-stale",
        help="Edit the earliest segment whose status is `stale`.",
    ),
    recent: bool = typer.Option(
        False,
        "--recent",
        help="Edit the segment that was most recently translated.",
    ),
) -> None:
    """Override one segment's translation through $EDITOR."""

    resolved_id = _resolve_edit_target(
        project_toml,
        segment_id=segment_id,
        first_failed=first_failed,
        next_stale=next_stale,
        recent=recent,
    )

    try:
        result = edit_segment(
            project_toml,
            resolved_id,
            editor=os.environ.get("EDITOR"),
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except WeaverError as exc:
        _exit_with_error(exc)

    typer.echo(f"Saved. Segment {result.segment_id} marked manual.")


def _resolve_edit_target(
    project_toml: Path,
    *,
    segment_id: str | None,
    first_failed: bool,
    next_stale: bool,
    recent: bool,
) -> str:
    selectors: list[SegmentSelector] = []
    if first_failed:
        selectors.append("first-failed")
    if next_stale:
        selectors.append("next-stale")
    if recent:
        selectors.append("recent")

    if segment_id is None and not selectors:
        typer.echo(
            "weaver edit requires a segment id or one of "
            "--first-failed/--next-stale/--recent. "
            "Likely cause: no target specified. "
            "Next command: run `weaver inspect <project.toml>` for segment ids "
            "or rerun with a selector flag.",
            err=True,
        )
        raise typer.Exit(code=1)
    if segment_id is not None and selectors:
        typer.echo(
            "weaver edit accepts either a positional segment id or a selector "
            "flag, not both. "
            "Likely cause: --first-failed/--next-stale/--recent was combined with "
            "an explicit id. "
            "Next command: rerun with the selector flag alone or with the id alone.",
            err=True,
        )
        raise typer.Exit(code=1)
    if len(selectors) > 1:
        typer.echo(
            "weaver edit accepts only one selector flag at a time "
            "(--first-failed, --next-stale, --recent). "
            "Likely cause: multiple selector flags were passed together. "
            "Next command: rerun with exactly one selector.",
            err=True,
        )
        raise typer.Exit(code=1)

    if segment_id is not None:
        return segment_id

    try:
        return resolve_segment_id(project_toml, selector=selectors[0])
    except WeaverError as exc:
        _exit_with_error(exc)


@app.command(
    "export",
    epilog=(
        "Examples:\n"
        "  weaver export .weaver/novel/project.toml --mode markdown\n"
        "  weaver export .weaver/novel/project.toml --mode epub"
    ),
)
def export_project_command(
    project_toml: Path,
    mode: str = typer.Option(
        "markdown",
        "--mode",
        help="Export mode: markdown or epub.",
    ),
    translation_only: bool = typer.Option(
        False,
        "--translation-only",
        help="Omit source text from Markdown review files.",
    ),
) -> None:
    """Export review or reader artifacts."""

    if mode not in {"markdown", "epub"}:
        typer.echo(
            "Unsupported export mode. Likely cause: only markdown and epub modes are implemented. "
            "Next command: run `weaver export <project.toml> --mode markdown` "
            "or `--mode epub`.",
            err=True,
        )
        raise typer.Exit(code=1)
    if mode == "epub" and translation_only:
        typer.echo(
            "--translation-only is only valid with --mode markdown. "
            "Likely cause: flag combination is not supported for EPUB output. "
            "Next command: rerun without --translation-only.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        if mode == "markdown":
            markdown_result = export_markdown_project(
                project_toml,
                translation_only=translation_only,
            )
            typer.echo(f"Wrote {markdown_result.index_path}")
            typer.echo(f"Chapters: {len(markdown_result.chapter_paths)}")
            return
        epub_result = export_epub_project(project_toml)
    except WeaverError as exc:
        _exit_with_error(exc)

    typer.echo(f"Wrote {epub_result.output_path}")
    typer.echo(
        f"Translated blocks: {epub_result.translated_blocks} | "
        f"Fallback blocks: {epub_result.fallback_blocks}"
    )


@app.command(
    "preview",
    epilog=(
        "Examples:\n"
        "  weaver preview .weaver/novel/project.toml\n"
        "  weaver preview .weaver/novel/project.toml --chapter 1\n"
        "  weaver preview .weaver/novel/project.toml --segment 8a3df9c6"
    ),
)
def preview_command(
    project_toml: Path,
    segment: str | None = typer.Option(
        None,
        "--segment",
        help="Show only this segment (exact id match).",
    ),
    chapter: int | None = typer.Option(
        None,
        "--chapter",
        help="Show only segments from this chapter (1-indexed).",
    ),
    pager: str | None = typer.Option(
        None,
        "--pager",
        help="Pipe output through pager. Use 'auto' to respect $PAGER.",
    ),
) -> None:
    """Preview source + translation pairs inline."""

    try:
        blocks = preview_project(
            project_toml,
            segment_id=segment,
            chapter=chapter,
        )
    except WeaverError as exc:
        _exit_with_error(exc)

    output = _render_preview_blocks(blocks)
    if pager == "auto":
        pager_cmd = os.environ.get("PAGER")
        if pager_cmd:
            import subprocess

            try:
                subprocess.run(
                    [pager_cmd],
                    input=output,
                    text=True,
                    check=False,
                )
                return
            except FileNotFoundError:
                pass
    typer.echo(output)


def _render_preview_blocks(blocks: list[PreviewBlock]) -> str:
    lines: list[str] = []
    current_chapter = -1
    for block in blocks:
        if block.chapter_index != current_chapter:
            if lines:
                lines.append("")
            lines.append(f"── Chapter {block.chapter_index}: {block.chapter_title} ──")
            lines.append("")
            current_chapter = block.chapter_index
        lines.append(f"[{block.segment_id}] ({block.status})")
        lines.append(f"  Source: {block.source_text}")
        if block.translation:
            lines.append(f"  Translation: {block.translation}")
        else:
            lines.append(f"  Translation: [{block.status.upper()}]")
        lines.append("")
    return "\n".join(lines)


@app.command(
    "doctor",
    epilog=("Examples:\n  weaver doctor\n  weaver doctor .weaver/novel/project.toml --healthcheck"),
)
def doctor_command(
    project_toml: Path | None = typer.Argument(
        None,
        help="Optional project.toml. Without it, only host-level checks run.",
    ),
    healthcheck: bool = typer.Option(
        False,
        "--healthcheck",
        "-H",
        help="Also probe the configured provider for reachability.",
    ),
) -> None:
    """Surface environment, database, and provider configuration gaps."""

    report = run_doctor(project_toml, run_healthcheck=healthcheck)
    _render_doctor_report(report)
    if not report.all_passed:
        raise typer.Exit(code=1)


def _render_doctor_report(report: DoctorReport) -> None:
    name_width = max((len(check.name) for check in report.checks), default=10)
    for check in report.checks:
        status = "PASS" if check.passed else "FAIL"
        typer.echo(f"{status}  {check.name.ljust(name_width)}  {check.detail}")


@app.command(
    "validate",
    epilog=(
        "Examples:\n  weaver validate .weaver/novel/project.toml\n"
        "  weaver validate --schema\n"
        "  weaver validate .weaver/novel/project.toml --epub"
    ),
)
def validate_project_command(
    project_toml: Path | None = typer.Argument(
        None,
        help="Project file to validate (required unless --schema is set).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Emit findings as JSON.",
    ),
    schema: bool = typer.Option(
        False,
        "--schema",
        help="Print the stable JSON shape produced by --json and exit. No project required.",
    ),
    epub: bool = typer.Option(
        False,
        "--epub",
        help="Run EPUBCheck on the exported EPUB (requires Java + epubcheck.jar).",
    ),
) -> None:
    """Run deterministic QA checks against a project."""

    if schema:
        import json as _json

        typer.echo(_json.dumps(qa_report_schema(), ensure_ascii=True, indent=2))
        return

    if project_toml is None:
        typer.echo(
            "weaver validate requires a project file. "
            "Likely cause: no project.toml was passed. "
            "Next command: run `weaver validate <project.toml>` "
            "or `weaver validate --schema` to inspect the JSON shape.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        report = validate_project(project_toml)
    except WeaverError as exc:
        _exit_with_error(exc)

    if json_output:
        typer.echo(format_report_json(report))
    else:
        _render_validation_report(report)

    if epub:
        _run_epubcheck_step(project_toml)

    if report.counts.get("critical", 0) > 0:
        raise typer.Exit(code=1)


def _run_epubcheck_step(project_toml: Path) -> None:
    from weaver.core.config import load_project_config
    from weaver.services.epubcheck import run_epubcheck

    data = load_project_config(project_toml)
    project_cfg = data["project"]
    source_stem = Path(str(project_cfg["source_file"])).stem
    raw_output_dir = str(project_cfg.get("output_dir", "output"))
    output_root = Path(raw_output_dir)
    if not output_root.is_absolute():
        cwd_candidate = Path.cwd() / output_root
        output_root = cwd_candidate if cwd_candidate.exists() else project_toml.parent / output_root
    epub_path = output_root / "epub" / f"{source_stem}.translated.epub"

    if not epub_path.exists():
        typer.echo(
            "EPUBCheck skipped: exported EPUB not found. "
            "Next command: run `weaver export --mode epub` first.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        result = run_epubcheck(epub_path)
    except WeaverError as exc:
        _exit_with_error(exc)

    if not result.epubcheck_available:
        typer.echo("EPUBCheck not available: jar not found. Skipping EPUB validation.")
        return

    if result.errors:
        for err in result.errors:
            typer.echo(f"  ERROR: {err}", err=True)
    if result.warnings:
        for warn in result.warnings:
            typer.echo(f"  WARNING: {warn}")
    if result.passed:
        typer.echo("EPUBCheck passed.")
    else:
        typer.echo(f"EPUBCheck failed: {len(result.errors)} error(s).", err=True)
        raise typer.Exit(code=1)


def _render_validation_report(report: ValidationReport) -> None:
    if not report.findings:
        typer.echo(f"No QA warnings. Segments scanned: {report.total_segments}.")
        return

    table = Table(title=f"Validate: {report.project_name}")
    table.add_column("Segment")
    table.add_column("Check")
    table.add_column("Severity")
    table.add_column("Message")
    for finding in report.findings:
        table.add_row(
            finding.segment_id,
            finding.check_name,
            finding.severity,
            finding.message,
        )
    with console.capture() as capture:
        console.print(table)
    _safe_echo(capture.get())
    typer.echo(
        f"Total: {report.total_segments} | "
        f"critical: {report.counts.get('critical', 0)} | "
        f"warning: {report.counts.get('warning', 0)} | "
        f"info: {report.counts.get('info', 0)}"
    )


@glossary_app.command(
    "review",
    epilog=(
        "Examples:\n"
        "  weaver glossary review .weaver/novel/project.toml\n"
        "  weaver glossary review .weaver/novel/project.toml --find Aozora"
    ),
)
def glossary_review_command(
    project_toml: Path,
    find: str | None = typer.Option(
        None,
        "--find",
        help="Jump to the first pending candidate whose source contains the substring.",
    ),
) -> None:
    """Interactively approve, edit, reject, or skip glossary candidates."""

    try:
        _run_glossary_review(project_toml, pre_seeded_search=find)
    except WeaverError as exc:
        _exit_with_error(exc)


@glossary_app.command(
    "edit",
    epilog=(
        "Examples:\n"
        "  weaver glossary edit .weaver/novel/project.toml\n"
        "  weaver glossary edit .weaver/novel/project.toml --yes"
    ),
)
def glossary_edit_command(
    project_toml: Path,
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation before syncing TSV changes.",
    ),
) -> None:
    """Open glossary TSV in $EDITOR and sync reviewed rows."""

    if not yes:
        typer.confirm(
            "Syncing the TSV will overwrite glossary state in the database. Continue?",
            abort=True,
        )

    try:
        count = sync_glossary_tsv_to_database(
            project_toml,
            editor=os.environ.get("EDITOR"),
        )
    except WeaverError as exc:
        _exit_with_error(exc)
    typer.echo(f"Synced {count} glossary TSV rows.")


@glossary_app.command(
    "conflicts",
    epilog=("Examples:\n  weaver glossary conflicts .weaver/novel/project.toml"),
)
def glossary_conflicts_command(project_toml: Path) -> None:
    """Show approved glossary target conflicts."""

    try:
        conflicts = list_project_glossary_conflicts(project_toml)
    except WeaverError as exc:
        _exit_with_error(exc)

    if not conflicts:
        typer.echo("No glossary conflicts.")
        return
    for source, targets in conflicts:
        _safe_echo(f"{source}: {', '.join(targets)}")


@glossary_app.command(
    "diff",
    epilog="Examples:\n  weaver glossary diff .weaver/novel/project.toml 1 2",
)
def glossary_diff_command(
    project_toml: Path,
    chapter_a: int = typer.Argument(..., help="First chapter number (1-indexed)."),
    chapter_b: int = typer.Argument(..., help="Second chapter number (1-indexed)."),
) -> None:
    """Show approved glossary term coverage diff between two chapters."""

    from weaver.services.glossary_diff import glossary_diff

    try:
        result = glossary_diff(project_toml, chapter_a, chapter_b)
    except WeaverError as exc:
        _exit_with_error(exc)

    if result.only_in_a:
        _safe_echo(
            f"Only in chapter {chapter_a} ({len(result.only_in_a)}): {', '.join(result.only_in_a)}"
        )
    if result.only_in_b:
        _safe_echo(
            f"Only in chapter {chapter_b} ({len(result.only_in_b)}): {', '.join(result.only_in_b)}"
        )
    if result.in_both:
        _safe_echo(f"In both ({len(result.in_both)}): {', '.join(result.in_both)}")
    if not result.only_in_a and not result.only_in_b and not result.in_both:
        typer.echo("No approved glossary terms found in either chapter.")


def _run_glossary_review(
    project_toml: Path,
    *,
    pre_seeded_search: str | None = None,
) -> None:
    with open_glossary_review_session(project_toml) as session:
        pending_search: str | None = pre_seeded_search

        while True:
            counts = session.status_counts()
            total = counts.pending + counts.approved + counts.rejected
            reviewed = counts.approved + counts.rejected
            typer.echo(
                f"Reviewed {reviewed} of {total} | "
                f"Pending: {counts.pending}  "
                f"Approved: {counts.approved}  "
                f"Rejected: {counts.rejected}"
            )

            candidate = _select_next_candidate(session, pending_search)
            pending_search = None
            if candidate is None:
                typer.echo("No pending glossary candidates.")
                return

            examples = session.examples_for(candidate.source)
            _print_candidate(candidate, examples=examples)

            action = (
                typer.prompt(
                    "[a]pprove [e]dit [r]eject [s]kip [u]ndo [f]ind [q]uit ?",
                    default="q",
                )
                .strip()
                .lower()
            )

            outcome = _apply_review_action(session, candidate, action)
            if outcome is False:
                return
            if isinstance(outcome, str):
                pending_search = outcome


def _select_next_candidate(
    session: GlossaryReviewSession, search: str | None
) -> GlossaryCandidateRecord | None:
    if search:
        match = session.find(search)
        if match is not None:
            return match
        typer.echo(f"No pending candidate matches `{search}`.")
    return session.next_pending()


def _apply_review_action(
    session: GlossaryReviewSession,
    candidate: GlossaryCandidateRecord,
    action: str,
) -> bool | str:
    """Apply one review action.

    Returns:
        `False` when the loop should exit, a substring when the next iteration
        should pre-seed a search, otherwise `True` to continue the normal queue.
    """

    if action == "q":
        typer.echo("Review progress saved.")
        return False
    if action == "s":
        typer.echo("Skipped")
        return True
    if action == "u":
        if session.undo():
            typer.echo("Undone")
        else:
            typer.echo("Nothing to undo")
        return True
    if action == "a":
        session.approve(candidate)
        typer.echo("Approved")
        return True
    if action == "r":
        session.reject(candidate)
        typer.echo("Rejected")
        return True
    if action == "e":
        target = typer.prompt("Target", default=candidate.target or candidate.source)
        notes = typer.prompt("Notes", default=candidate.notes or "")
        session.edit(candidate, target=target, notes=notes or None)
        typer.echo("Edited")
        return True
    if action == "f":
        substring = typer.prompt("Find substring", default="").strip()
        if not substring:
            typer.echo("Find cancelled")
            return True
        return substring

    typer.echo("Unknown action")
    return True


def _print_candidate(candidate: GlossaryCandidateRecord, *, examples: list[str]) -> None:
    typer.echo("")
    _safe_echo(f"Source: {candidate.source}")
    _safe_echo(f"Candidate target: {candidate.target or candidate.source}")
    _safe_echo(f"Category: {candidate.category or '-'}")
    _safe_echo(f"Frequency: {candidate.frequency}")
    if candidate.notes:
        _safe_echo(f"Notes: {candidate.notes}")
    if examples:
        typer.echo("Examples:")
        for sentence in examples:
            _safe_echo(f"  - {sentence}")


def _safe_echo(text: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    typer.echo(safe)


def _format_healthcheck(status: ProviderStatus) -> str:
    state = "healthy" if status.healthy else "unhealthy"
    parts = [state]
    if status.latency_ms is not None:
        parts.append(f"{status.latency_ms} ms")
    if status.message:
        parts.append(status.message)
    return " — ".join(parts)


def _exit_with_error(error: WeaverError) -> NoReturn:
    if _DEBUG_MODE:
        import traceback

        traceback.print_exception(error, file=sys.stderr)
    else:
        typer.echo(str(error), err=True)
    if isinstance(error, ProviderUnavailable):
        code = 3
    elif isinstance(error, (EpubReadError, EpubWriteError)):
        code = 4
    elif isinstance(error, SegmentNotFoundError):
        code = 5
    elif isinstance(error, GlossaryConflictError):
        code = 6
    elif isinstance(error, ConfigError):
        code = 7
    else:
        code = 1
    raise typer.Exit(code=code) from error


app.command("tx", hidden=True)(translate_project_command)
app.command("ins", hidden=True)(inspect_project_command)


if __name__ == "__main__":
    app()
