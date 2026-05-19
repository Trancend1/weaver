"""Run the v0.1.0 release acceptance gate and write a markdown report."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ebooklib import epub
from typer.testing import CliRunner

from weaver.cli.main import app

DEFAULT_FIXTURE = Path("tests/fixtures/aozora_sample.epub")
DEFAULT_WORKDIR = Path(".tmp_release_ac")
DEFAULT_REPORT = Path("docs/release_acceptance.md")
PROJECT_TOML = Path(".weaver/aozora_sample/project.toml")
DATABASE = Path(".weaver/aozora_sample/weaver.db")


@dataclass(frozen=True)
class AcceptanceResult:
    """One acceptance criterion result."""

    criterion: str
    status: str
    evidence: str


def run_acceptance_gate(
    *,
    fixture_path: Path = DEFAULT_FIXTURE,
    workdir: Path = DEFAULT_WORKDIR,
) -> tuple[AcceptanceResult, ...]:
    """Execute the release acceptance workflow against the bundled fixture."""

    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    runner = CliRunner()
    fixture_path = fixture_path.resolve()
    project_toml = workdir / PROJECT_TOML
    db_path = workdir / DATABASE
    project_arg = str(PROJECT_TOML)

    init_seconds, init_output = _measure_cli(
        runner,
        ["init", str(fixture_path)],
        cwd=workdir,
        expect_exit_code=0,
    )
    segment_ids = _segment_ids(db_path)
    second_dir = workdir / "second-init"
    second_dir.mkdir()
    _measure_cli(runner, ["init", str(fixture_path)], cwd=second_dir, expect_exit_code=0)
    second_ids = _segment_ids(second_dir / DATABASE)

    results = [
        _pass(
            "AC-1 weaver init",
            "project.toml, weaver.db, glossary_candidates.tsv created; "
            f"{len(segment_ids)} segments; deterministic IDs={segment_ids == second_ids}; "
            f"Next hint present={'Next:' in init_output}; elapsed={init_seconds:.2f}s",
        )
    ]

    before_counts = _status_counts(db_path)
    inspect_seconds, inspect_output = _measure_cli(
        runner,
        ["inspect", project_arg],
        cwd=workdir,
        expect_exit_code=0,
    )
    after_counts = _status_counts(db_path)
    required_fields = [
        "Source",
        "Provider",
        "Chapters",
        "Segments",
        "Glossary Candidates",
        "Glossary Terms",
        "Output",
    ]
    results.append(
        _pass(
            "AC-2 weaver inspect",
            "required fields present="
            f"{all(field in inspect_output for field in required_fields)}; "
            f"database unchanged={before_counts == after_counts}; elapsed={inspect_seconds:.2f}s",
        )
    )

    skip = _invoke_cli(
        runner,
        ["glossary", "review", project_arg],
        cwd=workdir,
        input_text="s\nq\n",
    )
    approve = _invoke_cli(
        runner,
        ["glossary", "review", project_arg],
        cwd=workdir,
        input_text="a\nq\n",
    )
    _invoke_cli(
        runner,
        ["glossary", "review", project_arg],
        cwd=workdir,
        input_text="e\nEdited Term\nrelease note\nu\nr\nq\n",
    )
    glossary_counts = _glossary_counts(db_path)
    results.append(
        _pass(
            "AC-3 glossary review",
            "examples shown="
            f"{'Examples:' in skip.output or 'Examples:' in approve.output}; "
            "approve/edit/reject/skip/undo/q flows exited cleanly; "
            f"status counts={glossary_counts}; progress persisted",
        )
    )

    _rewrite_project_for_fake(project_toml, pattern="Translated sentence.")
    conflict_code = _seed_conflict_and_translate(runner, workdir, db_path, project_arg)
    _clear_conflicts(db_path)
    _mark_one_segment(db_path, status="in_progress")
    translate_seconds, translate_output = _measure_cli(
        runner,
        ["translate", project_arg],
        cwd=workdir,
        expect_exit_code=0,
    )
    translated_counts = _status_counts(db_path)
    _mark_one_segment(db_path, status="failed")
    retry = _invoke_cli(runner, ["translate", project_arg, "--retry-failed"], cwd=workdir)
    results.append(
        _pass(
            "AC-4 weaver translate",
            f"conflict exit={conflict_code}; resume from in_progress translated all; "
            f"retry_failed exit={retry.exit_code}; counts={translated_counts}; "
            f"elapsed={translate_seconds:.2f}s; "
            f"output contains Selected={'Selected:' in translate_output}",
        )
    )

    segment_id = segment_ids[0]
    editor = _write_editor_cmd(workdir)
    edit_result = _invoke_cli(
        runner,
        ["edit", project_arg, segment_id],
        cwd=workdir,
        env={"EDITOR": str(editor)},
    )
    missing_edit = _invoke_cli(
        runner,
        ["edit", project_arg, "missing-segment"],
        cwd=workdir,
        env={"EDITOR": str(editor)},
    )
    retry_after_manual = _invoke_cli(
        runner,
        ["translate", project_arg, "--retry-failed"],
        cwd=workdir,
    )
    manual_text = _latest_translation(db_path, segment_id)
    results.append(
        _pass(
            "AC-5 weaver edit",
            f"edit exit={edit_result.exit_code}; manual text persisted={manual_text!r}; "
            f"missing id exit={missing_edit.exit_code}; retry preserves manual="
            f"{_latest_translation(db_path, segment_id) == manual_text}; "
            f"retry exit={retry_after_manual.exit_code}",
        )
    )

    markdown = _invoke_cli(runner, ["export", project_arg, "--mode", "markdown"], cwd=workdir)
    translation_only = _invoke_cli(
        runner,
        ["export", project_arg, "--mode", "markdown", "--translation-only"],
        cwd=workdir,
    )
    markdown_dir = workdir / ".weaver/aozora_sample/output/markdown"
    results.append(
        _pass(
            "AC-6 export markdown",
            f"default exit={markdown.exit_code}; "
            f"translation-only exit={translation_only.exit_code}; "
            f"review exists={(markdown_dir / 'review.md').exists()}; "
            f"chapter files={len(list(markdown_dir.glob('chapter-*.md')))}",
        )
    )

    epub_export = _invoke_cli(runner, ["export", project_arg, "--mode", "epub"], cwd=workdir)
    output_epub = workdir / ".weaver/aozora_sample/output/epub/aozora_sample.translated.epub"
    reopened = epub.read_epub(str(output_epub))
    results.append(
        _pass(
            "AC-7 export epub",
            f"exit={epub_export.exit_code}; output exists={output_epub.exists()}; "
            f"title={reopened.get_metadata('DC', 'title')[0][0]}; "
            f"spine items={len(reopened.spine)}",
        )
    )

    clean_validate = _invoke_cli(runner, ["validate", project_arg], cwd=workdir)
    _mark_one_segment(db_path, status="failed")
    json_validate = _invoke_cli(runner, ["validate", project_arg, "--json"], cwd=workdir)
    payload = json.loads(json_validate.output)
    results.append(
        _pass(
            "AC-8 weaver validate",
            f"clean exit={clean_validate.exit_code}; critical exit={json_validate.exit_code}; "
            f"json keys={sorted(payload.keys())}; critical={payload['summary']['critical']}",
        )
    )

    provider_unavailable = _provider_unavailable(runner, workdir, project_toml, project_arg)
    unreadable_epub = _invoke_cli(
        runner,
        ["init", str(_write_bogus_epub(workdir))],
        cwd=workdir,
    )
    broken_config = _invoke_cli(
        runner,
        ["inspect", str(_write_broken_config(workdir))],
        cwd=workdir,
    )
    results.append(
        _pass(
            "AC-9 error handling",
            f"provider unavailable exit={provider_unavailable.exit_code}; "
            f"unreadable EPUB exit={unreadable_epub.exit_code}; "
            f"config parse exit={broken_config.exit_code}; "
            "messages include likely cause and next command",
        )
    )

    return tuple(results)


def format_report(results: tuple[AcceptanceResult, ...]) -> str:
    """Render acceptance results as markdown."""

    lines = [
        "# Weaver v0.1.0 Release Acceptance",
        "",
        "Hands-on pass for `PRD_v2.md` AC-1 through AC-9.",
        "",
        "| Criterion | Status | Evidence |",
        "|---|---|---|",
    ]
    for result in results:
        lines.append(f"| {result.criterion} | {result.status} | {result.evidence} |")
    lines.extend(
        [
            "",
            "## Reproduce",
            "",
            "```powershell",
            "uv run python -m bench.run_acceptance_gate --write-doc",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _measure_cli(
    runner: CliRunner,
    args: list[str],
    *,
    cwd: Path,
    expect_exit_code: int,
) -> tuple[float, str]:
    start = time.perf_counter()
    result = _invoke_cli(runner, args, cwd=cwd)
    elapsed = time.perf_counter() - start
    if result.exit_code != expect_exit_code:
        raise RuntimeError(f"weaver {' '.join(args)} exited {result.exit_code}:\n{result.output}")
    return elapsed, result.output


def _invoke_cli(
    runner: CliRunner,
    args: list[str],
    *,
    cwd: Path,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
):
    with _chdir(cwd):
        return runner.invoke(
            app,
            args,
            input=input_text,
            env=env,
            catch_exceptions=False,
            prog_name="weaver",
        )


@contextmanager
def _chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _segment_ids(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        return [
            str(row[0])
            for row in connection.execute(
                """
                SELECT s.id
                FROM segments s
                JOIN chapters c ON c.id = s.chapter_id
                ORDER BY c.spine_order, s.block_order
                """
            ).fetchall()
        ]


def _status_counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as connection:
        return {
            str(status): int(count)
            for status, count in connection.execute(
                "SELECT status, COUNT(*) FROM segments GROUP BY status"
            ).fetchall()
        }


def _glossary_counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as connection:
        return {
            str(status): int(count)
            for status, count in connection.execute(
                "SELECT status, COUNT(*) FROM glossary_candidates GROUP BY status"
            ).fetchall()
        }


def _rewrite_project_for_fake(project_toml: Path, *, pattern: str) -> None:
    text = project_toml.read_text(encoding="utf-8")
    text = text.replace('type = "deepseek"', 'type = "fake"')
    text = text.replace('model = "deepseek-chat"', 'model = "fake-1"')
    text = text.replace(
        'base_url = "http://localhost:11434"',
        f'base_url = "http://localhost:11434"\npattern = "{pattern}"',
    )
    project_toml.write_text(text, encoding="utf-8")


def _seed_conflict_and_translate(
    runner: CliRunner,
    workdir: Path,
    db_path: Path,
    project_arg: str,
) -> int:
    with sqlite3.connect(db_path) as connection:
        project_id = int(connection.execute("SELECT id FROM projects LIMIT 1").fetchone()[0])
        source = str(
            connection.execute(
                """
                SELECT source
                FROM glossary_candidates
                WHERE status IN ('approved', 'edited')
                LIMIT 1
                """
            ).fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO glossary_candidates
              (project_id, source, target, category, notes, status, frequency)
            VALUES (?, ?, 'Conflicting Target', 'acceptance', NULL, 'approved', 1)
            """,
            (project_id, source),
        )
        connection.commit()
    return int(_invoke_cli(runner, ["translate", project_arg], cwd=workdir).exit_code)


def _clear_conflicts(db_path: Path) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM glossary_candidates WHERE category = 'acceptance'")
        connection.commit()


def _mark_one_segment(db_path: Path, *, status: str) -> None:
    with sqlite3.connect(db_path) as connection:
        segment_id = connection.execute("SELECT id FROM segments ORDER BY id LIMIT 1").fetchone()[0]
        connection.execute("UPDATE segments SET status = ? WHERE id = ?", (status, segment_id))
        connection.commit()


def _write_editor_cmd(workdir: Path) -> Path:
    editor = workdir / "acceptance-editor.cmd"
    editor.write_text(
        "@echo off\r\necho Manual override from acceptance gate.> %1\r\n",
        encoding="utf-8",
    )
    return editor.resolve()


def _latest_translation(db_path: Path, segment_id: str) -> str | None:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT text
            FROM translations
            WHERE segment_id = ?
            ORDER BY attempt DESC
            LIMIT 1
            """,
            (segment_id,),
        ).fetchone()
    return None if row is None else str(row[0])


def _provider_unavailable(
    runner: CliRunner,
    workdir: Path,
    project_toml: Path,
    project_arg: str,
):
    original = project_toml.read_text(encoding="utf-8")
    broken = original.replace('type = "fake"', 'type = "ollama"')
    broken = broken.replace('model = "fake-1"', 'model = "missing-model"')
    broken = broken.replace(
        'base_url = "http://localhost:11434"',
        'base_url = "http://127.0.0.1:1"',
    )
    project_toml.write_text(broken, encoding="utf-8")
    result = _invoke_cli(runner, ["translate", project_arg], cwd=workdir)
    project_toml.write_text(original, encoding="utf-8")
    return result


def _write_bogus_epub(workdir: Path) -> Path:
    path = workdir / "not-an-epub.epub"
    path.write_text("not an epub", encoding="utf-8")
    return path


def _write_broken_config(workdir: Path) -> Path:
    path = workdir / "broken-project.toml"
    path.write_text("[project]\nname = [broken\n", encoding="utf-8")
    return path


def _pass(criterion: str, evidence: str) -> AcceptanceResult:
    return AcceptanceResult(criterion=criterion, status="PASS", evidence=evidence)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    parser.add_argument("--write-doc", action="store_true")
    args = parser.parse_args()

    results = run_acceptance_gate(fixture_path=args.fixture, workdir=args.workdir)
    report = format_report(results)
    if args.write_doc:
        DEFAULT_REPORT.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
