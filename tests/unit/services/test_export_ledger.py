"""Tests for the export-history ledger writer (Sprint Q7)."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest

from weaver.services import export_ledger
from weaver.services.export_book import prepare_export
from weaver.services.export_ledger import run_export_recorded
from weaver.services.project import initialize_project
from weaver.storage.db import connect_readonly_database
from weaver.storage.export_history import list_export_history

FIXTURE_EPUB = Path(__file__).parents[2] / "fixtures" / "aozora_sample.epub"


def _project(tmp_path: Path) -> tuple[Path, Path]:
    result = initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    db_path = tmp_path / ".weaver" / "alpha" / "weaver.db"
    return result.project_toml, db_path


def _history(db_path: Path) -> list:
    with closing(connect_readonly_database(db_path)) as connection:
        return list_export_history(connection)


def test_success_records_one_row_per_artifact(tmp_path: Path) -> None:
    project_toml, db_path = _project(tmp_path)
    plan = prepare_export(project_toml, scope="novel", target="epub", cwd=tmp_path)

    result = run_export_recorded(plan, db_path, kind="draft", qa_badge=None)

    rows = _history(db_path)
    assert len(rows) == len(result.artifacts)
    assert len(rows) >= 1
    for row in rows:
        assert row.status == "succeeded"
        assert row.kind == "draft"
        assert row.format == "epub"
        assert row.artifact_path is not None
        assert row.byte_size is not None and row.byte_size > 0


def test_success_records_qa_badge_for_final(tmp_path: Path) -> None:
    project_toml, db_path = _project(tmp_path)
    plan = prepare_export(project_toml, scope="novel", target="epub", cwd=tmp_path)

    run_export_recorded(plan, db_path, kind="final", qa_badge="clean", version_label="v1.0")

    rows = _history(db_path)
    assert rows[0].kind == "final"
    assert rows[0].qa_badge == "clean"
    assert rows[0].version_label == "v1.0"


def test_failure_records_failed_row_and_reraises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_toml, db_path = _project(tmp_path)
    plan = prepare_export(project_toml, scope="novel", target="epub", cwd=tmp_path)

    def _boom(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        raise RuntimeError("disk full")

    monkeypatch.setattr(export_ledger, "run_export", _boom)

    with pytest.raises(RuntimeError, match="disk full"):
        run_export_recorded(plan, db_path, kind="final", qa_badge="errors")

    rows = _history(db_path)
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].artifact_path is None
    assert rows[0].qa_badge == "errors"
