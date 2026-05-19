"""Run Weaver performance budgets against the synthetic benchmark fixture."""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import time
from collections.abc import Callable
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from typer.testing import CliRunner

from bench.generate_synthetic_fixture import generate_synthetic_epub
from weaver.cli.main import app
from weaver.readers.epub import read_epub
from weaver.services.glossary import extract_glossary_candidates
from weaver.storage.db import connect_database

DEFAULT_FIXTURE = Path("tests/fixtures/synthetic_200_chapter.epub")
DEFAULT_WORKDIR = Path(".tmp_benchmarks")
PROJECT_TOML = Path(".weaver/synthetic_200_chapter/project.toml")
DATABASE = Path(".weaver/synthetic_200_chapter/weaver.db")


@dataclass(frozen=True)
class BudgetResult:
    """One measured performance budget result."""

    operation: str
    target_seconds: float | None
    elapsed_seconds: float | None
    passed: bool | None
    note: str


def run_benchmarks(
    *,
    fixture_path: Path = DEFAULT_FIXTURE,
    workdir: Path = DEFAULT_WORKDIR,
    refresh_fixture: bool = False,
) -> tuple[BudgetResult, ...]:
    """Run the repeatable benchmark set and return measured results."""

    if refresh_fixture or not fixture_path.exists():
        generate_synthetic_epub(fixture_path)

    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    runner = CliRunner()
    fixture_path = fixture_path.resolve()
    project_toml = workdir / PROJECT_TOML
    project_toml_arg = str(PROJECT_TOML)
    db_path = workdir / DATABASE

    results: list[BudgetResult] = []
    init_seconds = _measure_cli(
        runner,
        ["init", str(fixture_path)],
        cwd=workdir,
        expect_exit_code=0,
    )
    results.append(_budget("weaver init", 30.0, init_seconds, "200 chapters / 10,000 blocks"))

    glossary_seconds = _measure(
        lambda: extract_glossary_candidates(read_epub(fixture_path)),
    )
    results.append(
        _budget(
            "glossary extraction",
            20.0,
            glossary_seconds,
            "same 200-chapter fixture, extraction only",
        )
    )

    inspect_seconds = _measure_cli(
        runner,
        ["inspect", project_toml_arg],
        cwd=workdir,
        expect_exit_code=0,
    )
    results.append(_budget("weaver inspect", 1.0, inspect_seconds, "10,000-segment project"))

    resume_seconds = _measure_resume_scan(db_path)
    results.append(_budget("resume scan on startup", 5.0, resume_seconds, "10,000 reset rows"))

    _rewrite_project_for_fake(project_toml)
    translate_seconds = _measure_cli(
        runner,
        ["translate", project_toml_arg],
        cwd=workdir,
        expect_exit_code=0,
    )
    per_segment_ms = translate_seconds / 10_000 * 1000
    results.append(
        _budget(
            "weaver translate fake provider",
            0.05,
            per_segment_ms / 1000,
            f"{per_segment_ms:.2f} ms/segment over 10,000 segments",
        )
    )

    markdown_seconds = _measure_cli(
        runner,
        ["export", project_toml_arg, "--mode", "markdown"],
        cwd=workdir,
        expect_exit_code=0,
    )
    results.append(_budget("weaver export markdown", 10.0, markdown_seconds, "10,000 segments"))

    epub_seconds = _measure_cli(
        runner,
        ["export", project_toml_arg, "--mode", "epub"],
        cwd=workdir,
        expect_exit_code=0,
    )
    results.append(_budget("weaver export epub", 30.0, epub_seconds, "10,000 segments"))

    validate_seconds = _measure_cli(
        runner,
        ["validate", project_toml_arg],
        cwd=workdir,
        expect_exit_code=0,
    )
    results.append(_budget("weaver validate", 15.0, validate_seconds, "10,000 segments"))

    db_size_mb = db_path.stat().st_size / 1024 / 1024
    results.append(_budget("SQLite DB size", None, None, f"{db_size_mb:.2f} MB < 100 MB"))
    results.append(
        BudgetResult(
            operation="weaver status",
            target_seconds=1.0,
            elapsed_seconds=None,
            passed=None,
            note="Not an MVP-0 command; `weaver inspect` is the status surface.",
        )
    )
    return tuple(results)


def format_markdown(results: tuple[BudgetResult, ...]) -> str:
    """Render benchmark results for docs/benchmarks.md."""

    lines = [
        "# Weaver Benchmarks",
        "",
        "Performance baseline for the v0.1.0 release candidate.",
        "",
        "## Fixture",
        "",
        "- Fixture: `tests/fixtures/synthetic_200_chapter.epub`",
        "- Shape: 200 chapters, 50 text blocks per chapter, 10,000 total blocks",
        "- Generator: `bench/generate_synthetic_fixture.py`",
        "- Runner: `bench/run_performance_budgets.py`",
        "",
        "## Latest Run",
        "",
        "| Operation | Budget | Measured | Result | Notes |",
        "|---|---:|---:|---|---|",
    ]
    for result in results:
        budget = _format_budget(result)
        measured = _format_measured(result)
        status = _format_status(result)
        lines.append(f"| {result.operation} | {budget} | {measured} | {status} | {result.note} |")
    lines.extend(
        [
            "",
            "## Reproduce",
            "",
            "```powershell",
            "uv run python -m bench.generate_synthetic_fixture",
            "uv run python -m bench.run_performance_budgets --write-doc",
            "```",
            "",
            "Budgets come from `docs/SECURITY_AND_PERFORMANCE.md`.",
            "`weaver status` is listed there as a future/status surface budget,",
            "but MVP-0 ships `weaver inspect` as the user-facing status command.",
            "",
        ]
    )
    return "\n".join(lines)


def _measure(action: Callable[[], object]) -> float:
    start = time.perf_counter()
    action()
    return time.perf_counter() - start


def _measure_cli(
    runner: CliRunner,
    args: list[str],
    *,
    cwd: Path,
    expect_exit_code: int,
) -> float:
    start = time.perf_counter()
    with _chdir(cwd):
        result = runner.invoke(app, args, catch_exceptions=False, prog_name="weaver", env={})
    elapsed = time.perf_counter() - start
    if result.exit_code != expect_exit_code:
        command = "weaver " + " ".join(args)
        raise RuntimeError(f"{command} exited {result.exit_code}:\n{result.output}")
    return elapsed


@contextmanager
def _chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _measure_resume_scan(db_path: Path) -> float:
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE segments SET status = 'in_progress'")
        connection.commit()

    def open_and_reset() -> None:
        with closing(connect_database(db_path)):
            pass

    return _measure(open_and_reset)


def _rewrite_project_for_fake(project_toml: Path) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    text = text.replace(
        'base_url = "http://localhost:11434"',
        'base_url = "http://localhost:11434"\npattern = "Translated sentence."',
    )
    project_toml.write_text(text, encoding="utf-8")


def _budget(
    operation: str,
    target_seconds: float | None,
    elapsed_seconds: float | None,
    note: str,
) -> BudgetResult:
    passed = (
        None
        if target_seconds is None or elapsed_seconds is None
        else elapsed_seconds < target_seconds
    )
    return BudgetResult(
        operation=operation,
        target_seconds=target_seconds,
        elapsed_seconds=elapsed_seconds,
        passed=passed,
        note=note,
    )


def _format_budget(result: BudgetResult) -> str:
    if result.target_seconds is None:
        return "-"
    if result.operation == "weaver translate fake provider":
        return "< 50 ms/segment"
    return f"< {result.target_seconds:g} s"


def _format_measured(result: BudgetResult) -> str:
    if result.elapsed_seconds is None:
        return "-"
    if result.operation == "weaver translate fake provider":
        return f"{result.elapsed_seconds * 1000:.2f} ms/segment"
    return f"{result.elapsed_seconds:.2f} s"


def _format_status(result: BudgetResult) -> str:
    if result.passed is True:
        return "PASS"
    if result.passed is False:
        return "FAIL"
    return "N/A"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    parser.add_argument("--refresh-fixture", action="store_true")
    parser.add_argument("--write-doc", action="store_true")
    args = parser.parse_args()

    results = run_benchmarks(
        fixture_path=args.fixture,
        workdir=args.workdir,
        refresh_fixture=args.refresh_fixture,
    )
    markdown = format_markdown(results)
    if args.write_doc:
        Path("docs/benchmarks.md").write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
