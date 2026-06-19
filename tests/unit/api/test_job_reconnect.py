"""JobRegistry.find_running_batch — the lookup that re-attaches the project-page
volume progress panel after a reload/navigation (the batch keeps running).
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from weaver.api.jobs import JobRegistry
from weaver.services.batch_translate import BatchTranslationResult


def _empty_result() -> BatchTranslationResult:
    return BatchTranslationResult(
        scope="volume",
        scope_id="3",
        mode="skip_existing",
        provider="fake",
        model="fake-1",
        chapters_total=0,
        chapters_done=0,
        segments_total=0,
        translated=0,
        reused_from_memory=0,
        skipped=0,
        failed=0,
        input_tokens=0,
        output_tokens=0,
        cancelled=False,
        started_at="",
        finished_at="",
        duration_seconds=0.0,
    )


def test_find_running_batch_matches_then_clears_when_done() -> None:
    reg = JobRegistry()  # no base_dir → in-memory only
    release = threading.Event()

    def runner(should_cancel, on_progress) -> BatchTranslationResult:  # noqa: ARG001
        release.wait(timeout=5)
        return _empty_result()

    job = reg.submit_batch(
        project_name="P", scope="volume", scope_id="3", mode="skip_existing", runner=runner
    )
    try:
        # While running, the volume's job is found...
        assert reg.find_running_batch(project_name="P", scope="volume", scope_id="3") is job
        # ...but not for another volume, project, or scope.
        assert reg.find_running_batch(project_name="P", scope="volume", scope_id="99") is None
        assert reg.find_running_batch(project_name="Other", scope="volume", scope_id="3") is None
        assert reg.find_running_batch(project_name="P", scope="chapter", scope_id="3") is None
    finally:
        release.set()
        job.wait(timeout=5)

    # Once the job leaves the running state, the slot must not re-attach.
    assert reg.find_running_batch(project_name="P", scope="volume", scope_id="3") is None


def test_project_tree_flags_running_volume_batch(tmp_path: Path) -> None:
    """End-to-end: a running volume batch surfaces as VolumeView.active_batch_job_id,
    which is what re-attaches the inline panel after a page reload."""
    from weaver.services.project import initialize_project
    from weaver.services.project_discovery import discover_projects
    from weaver.services.project_tree import project_tree

    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = sorted(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path, provider="fake")
    discovered = [d for d in discover_projects(tmp_path) if not d.error]
    name, toml = discovered[0].name, discovered[0].project_toml

    vid = project_tree(toml, cwd=tmp_path, jobs=None).volumes[0].id

    reg = JobRegistry()
    release = threading.Event()

    def runner(should_cancel, on_progress) -> BatchTranslationResult:  # noqa: ARG001
        release.wait(timeout=5)
        return _empty_result()

    job = reg.submit_batch(
        project_name=name, scope="volume", scope_id=str(vid), mode="skip_existing", runner=runner
    )
    try:
        tree = project_tree(toml, cwd=tmp_path, jobs=reg)
        assert tree.volumes[0].active_batch_job_id == job.id
    finally:
        release.set()
        job.wait(timeout=5)

    # After completion the flag clears, so the start button returns.
    assert project_tree(toml, cwd=tmp_path, jobs=reg).volumes[0].active_batch_job_id is None
