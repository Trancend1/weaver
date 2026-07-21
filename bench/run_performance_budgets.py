"""Run Weaver performance budgets against the synthetic benchmark fixture."""

from __future__ import annotations

import argparse
import os
import re
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
from weaver.providers.fake import FakeProvider
from weaver.readers.epub import read_epub
from weaver.services.glossary import extract_glossary_candidates
from weaver.services.translation import translate_project
from weaver.services.workspace_providers import build_workspace_providers
from weaver.services.workspace_queue import build_workspace_queue
from weaver.storage.db import connect_database, connect_readonly_database
from weaver.storage.translations import list_previous_translated_segments

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
    # Probed on copies made before the main translate run consumes the pending
    # segments, so the budgets below still measure a full 10,000-segment run.
    results.append(_measure_concurrency_scaling(workdir))
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

    results.append(_measure_window_flat_cost(db_path))

    providers_seconds = _measure(lambda: build_workspace_providers(workdir))
    results.append(
        _budget("providers-hub render", 2.0, providers_seconds, "1-project workspace, read-only")
    )
    queue_seconds = _measure(lambda: build_workspace_queue(workdir))
    results.append(_budget("queue render", 2.0, queue_seconds, "1-project workspace, read-only"))

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


_FLAT_COST_OP = "rolling-window flat cost"
_FLAT_COST_MAX_GROWTH = 1.2


def _measure_window_flat_cost(db_path: Path) -> BudgetResult:
    """Prove the rolling-window query is flat across the 10k-segment table.

    The chapter-scoped CTE (v0.7.3 M1.2) makes ``list_previous_translated_segments``
    depend only on chapter size, not total table size — so the last chapter of
    the fixture must cost about the same as the first (growth < 1.2x), which the
    pre-M1.2 O(n^2) query failed (measured 1.96x on a fresh 10k run).
    """

    with closing(connect_readonly_database(db_path)) as connection:
        chapters = [
            str(row["id"])
            for row in connection.execute("SELECT id FROM chapters ORDER BY spine_order").fetchall()
        ]
        first_avg = _avg_window_query(connection, chapters[0])
        last_avg = _avg_window_query(connection, chapters[-1])

    growth = last_avg / first_avg if first_avg > 0 else 1.0
    return BudgetResult(
        operation=_FLAT_COST_OP,
        target_seconds=_FLAT_COST_MAX_GROWTH,
        elapsed_seconds=growth,
        passed=growth < _FLAT_COST_MAX_GROWTH,
        note=(
            f"first chapter {first_avg * 1e6:.1f} us vs last {last_avg * 1e6:.1f} us "
            "per query over 10,000 segments"
        ),
    )


_CONCURRENCY_OP = "translate concurrency scaling"
_CONCURRENCY_MIN_SPEEDUP = 2.4
# 24 rather than a smaller batch: `translate_project` does fixed per-run setup
# (source read, glossary load, segment selection) that is identical on both
# sides and therefore drags the ratio toward 1. More segments amortize it, so
# the number reported is closer to the concurrency the window actually buys.
_CONCURRENCY_SEGMENTS = 24
_CONCURRENCY_LATENCY_SECONDS = 0.3


def _measure_concurrency_scaling(workdir: Path) -> BudgetResult:
    """Measure the wall-clock speedup of a 3-worker window vs sequential (ADR 020).

    The v0.7.3 exit criterion is >= 2.4x at ``max_concurrent = 3``. A
    latency-simulating provider is required: with the zero-latency fake the run
    is dominated by SQLite writes and would measure scheduling overhead rather
    than the provider overlap that concurrency actually buys.

    Each side runs on its own copy of the freshly-initialized project so the two
    measurements start from identical state and neither consumes the pending
    segments the later budgets need.
    """

    elapsed: dict[int, float] = {}
    for workers in (1, 3):
        probe_dir = workdir / f".tmp_concurrency_{workers}"
        shutil.copytree(workdir / ".weaver", probe_dir / ".weaver")
        probe_toml = probe_dir / PROJECT_TOML
        elapsed[workers] = _measure(
            lambda toml=probe_toml, cwd=probe_dir, n=workers: translate_project(
                toml,
                cwd=cwd,
                first_n=_CONCURRENCY_SEGMENTS,
                provider=FakeProvider(latency_seconds=_CONCURRENCY_LATENCY_SECONDS),
                max_concurrent=n,
            )
        )
        shutil.rmtree(probe_dir)

    speedup = elapsed[1] / elapsed[3] if elapsed[3] > 0 else 0.0
    return BudgetResult(
        operation=_CONCURRENCY_OP,
        target_seconds=_CONCURRENCY_MIN_SPEEDUP,
        elapsed_seconds=speedup,
        passed=speedup >= _CONCURRENCY_MIN_SPEEDUP,
        note=(
            f"{_CONCURRENCY_SEGMENTS} segments at {_CONCURRENCY_LATENCY_SECONDS:g}s "
            f"provider latency: {elapsed[1]:.2f}s sequential vs {elapsed[3]:.2f}s "
            "at 3 workers"
        ),
    )


def _avg_window_query(
    connection: sqlite3.Connection, chapter_id: str, *, iterations: int = 100
) -> float:
    start = time.perf_counter()
    for _ in range(iterations):
        list_previous_translated_segments(
            connection, chapter_id=chapter_id, before_block_order=1_000_000
        )
    return (time.perf_counter() - start) / iterations


def _measure_resume_scan(db_path: Path) -> float:
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE segments SET status = 'in_progress'")
        connection.commit()

    def open_and_reset() -> None:
        with closing(connect_database(db_path)):
            pass

    return _measure(open_and_reset)


# `pattern` yields pure-English output (no `{source}`, no Japanese) so the QA
# checks see clean translations and `weaver validate` exits 0 — matching the
# pre-v0.7.2 bench contract. The default `[FAKE] {source}` pattern would retain
# the Japanese source and trip `untranslated_japanese` criticals (validate → 1).
_FAKE_PROVIDER_BLOCK = (
    "[provider]\n"
    'type = "custom"\n'
    'protocol = "fake"\n'
    'model = "fake-1"\n'
    'base_url = ""\n'
    'api_key_env = ""\n'
    'pattern = "Translated sentence."\n\n'
)


def _rewrite_project_for_fake(project_toml: Path) -> None:
    """Point the benchmark project at the deterministic fake provider.

    Since v0.7.2, ``weaver init`` writes an unresolvable placeholder
    ``[provider]`` block (empty ``protocol``), so the old string-patch of
    ``type = "deepseek"`` silently no-ops and translate/export budgets never
    run. Replace the whole ``[provider]`` table with the canonical fake block
    (``protocol = "fake"`` — resolved by ``providers.registry._build_fake``).
    """

    text = project_toml.read_text(encoding="utf-8")
    new_text, count = re.subn(r"\[provider\][^\[]*", _FAKE_PROVIDER_BLOCK, text, count=1)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly one [provider] table in {project_toml}; replaced {count}. "
            "The bench fake-provider rewrite is out of sync with `weaver init`."
        )
    project_toml.write_text(new_text, encoding="utf-8")


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
    if result.operation == _FLAT_COST_OP:
        return f"< {result.target_seconds:g}x growth"
    if result.operation == _CONCURRENCY_OP:
        return f">= {result.target_seconds:g}x speedup"
    return f"< {result.target_seconds:g} s"


def _format_measured(result: BudgetResult) -> str:
    if result.elapsed_seconds is None:
        return "-"
    if result.operation == "weaver translate fake provider":
        return f"{result.elapsed_seconds * 1000:.2f} ms/segment"
    if result.operation in (_FLAT_COST_OP, _CONCURRENCY_OP):
        return f"{result.elapsed_seconds:.2f}x"
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
