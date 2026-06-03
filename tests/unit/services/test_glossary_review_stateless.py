"""Unit tests for the stateless glossary review ops (Phase 12c)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import ConfigError, GlossaryCandidateNotFoundError
from weaver.services.glossary_review import act_on_candidate, list_pending
from weaver.services.project import initialize_project

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def _init(tmp_path: Path) -> Path:
    result = initialize_project(FIXTURE_EPUB, cwd=tmp_path)
    return result.project_toml


def test_list_pending_paginates_and_counts(tmp_path: Path) -> None:
    project_toml = _init(tmp_path)

    page = list_pending(project_toml, cwd=tmp_path, offset=0, limit=2)

    assert len(page.items) <= 2
    assert page.offset == 0
    assert page.limit == 2
    assert page.total_pending == page.counts.pending
    assert page.total_pending >= len(page.items)


def test_list_pending_offset_advances(tmp_path: Path) -> None:
    project_toml = _init(tmp_path)
    full = list_pending(project_toml, cwd=tmp_path, offset=0, limit=100)
    if full.total_pending < 2:
        pytest.skip("fixture yielded fewer than 2 candidates")

    second = list_pending(project_toml, cwd=tmp_path, offset=1, limit=100)
    assert second.items[0].id == full.items[1].id


def test_list_pending_find_filters_by_source(tmp_path: Path) -> None:
    project_toml = _init(tmp_path)
    full = list_pending(project_toml, cwd=tmp_path, limit=100)
    if not full.items:
        pytest.skip("fixture yielded no candidates")
    needle = full.items[0].source[:1]

    filtered = list_pending(project_toml, cwd=tmp_path, limit=100, find=needle)

    assert filtered.find == needle
    assert all(needle in c.source for c in filtered.items)
    assert filtered.total_pending == len(filtered.items)
    assert filtered.total_pending <= full.total_pending


def test_list_pending_find_no_match_is_empty(tmp_path: Path) -> None:
    project_toml = _init(tmp_path)
    page = list_pending(project_toml, cwd=tmp_path, limit=100, find="ZZZ-no-such-term")
    assert page.items == ()
    assert page.total_pending == 0
    # Unfiltered queue counts remain available for display.
    assert page.counts.pending >= 0


def test_act_approve_decrements_pending(tmp_path: Path) -> None:
    project_toml = _init(tmp_path)
    page = list_pending(project_toml, cwd=tmp_path, limit=100)
    before = page.total_pending
    assert before >= 1

    act_on_candidate(project_toml, page.items[0].id, "approve", cwd=tmp_path)

    after = list_pending(project_toml, cwd=tmp_path, limit=100)
    assert after.total_pending == before - 1
    assert after.counts.approved >= 1


def test_act_edit_sets_target(tmp_path: Path) -> None:
    project_toml = _init(tmp_path)
    candidate = list_pending(project_toml, cwd=tmp_path, limit=1).items[0]

    act_on_candidate(project_toml, candidate.id, "edit", cwd=tmp_path, target="Pinned", notes="n")

    # The edited candidate leaves the pending queue.
    remaining = {c.id for c in list_pending(project_toml, cwd=tmp_path, limit=100).items}
    assert candidate.id not in remaining


def test_act_reject_removes_from_pending(tmp_path: Path) -> None:
    project_toml = _init(tmp_path)
    candidate = list_pending(project_toml, cwd=tmp_path, limit=1).items[0]

    act_on_candidate(project_toml, candidate.id, "reject", cwd=tmp_path)

    after = list_pending(project_toml, cwd=tmp_path, limit=100)
    assert candidate.id not in {c.id for c in after.items}
    assert after.counts.rejected >= 1


def test_act_edit_without_target_raises(tmp_path: Path) -> None:
    project_toml = _init(tmp_path)
    candidate = list_pending(project_toml, cwd=tmp_path, limit=1).items[0]
    with pytest.raises(ConfigError):
        act_on_candidate(project_toml, candidate.id, "edit", cwd=tmp_path, target="  ")


def test_act_unknown_action_raises(tmp_path: Path) -> None:
    project_toml = _init(tmp_path)
    candidate = list_pending(project_toml, cwd=tmp_path, limit=1).items[0]
    with pytest.raises(ConfigError):
        act_on_candidate(project_toml, candidate.id, "delete", cwd=tmp_path)


def test_act_missing_candidate_raises(tmp_path: Path) -> None:
    project_toml = _init(tmp_path)
    with pytest.raises(GlossaryCandidateNotFoundError):
        act_on_candidate(project_toml, 999999, "approve", cwd=tmp_path)
