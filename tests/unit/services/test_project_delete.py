"""Tests for permanently deleting a project's .weaver/<name> directory."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import ProjectNotFoundError, WeaverError
from weaver.services.project import delete_project, initialize_project


def _fixture_epub() -> Path:
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    return epubs[0]


def test_delete_removes_project_dir(tmp_path: Path) -> None:
    result = initialize_project(_fixture_epub(), cwd=tmp_path)
    project_dir = result.project_toml.parent
    assert project_dir.is_dir()

    delete_project(result.project_toml)

    assert not project_dir.exists()
    # The .weaver root itself survives so other projects are unaffected.
    assert (tmp_path / ".weaver").is_dir()


def test_delete_missing_project_raises(tmp_path: Path) -> None:
    ghost = tmp_path / ".weaver" / "ghost" / "project.toml"
    with pytest.raises(ProjectNotFoundError):
        delete_project(ghost)


def test_delete_refuses_path_outside_weaver(tmp_path: Path) -> None:
    stray = tmp_path / "random" / "project.toml"
    stray.parent.mkdir(parents=True)
    stray.write_text("", encoding="utf-8")
    with pytest.raises(WeaverError, match="Refusing to delete"):
        delete_project(stray)
    # The guard must not have removed anything.
    assert stray.exists()
