"""Render tests for the project-tree partial (_tree.html).

Rendered directly via the Jinja env so the 0-segment (illustration / front-matter)
branch is exercised deterministically without needing an EPUB fixture that happens
to contain an image-only chapter.
"""

from __future__ import annotations

from types import SimpleNamespace

from weaver.api.templating import templates


def _tree_with(
    chapters: list[SimpleNamespace], *, active_batch_job_id: str | None = None
) -> SimpleNamespace:
    volume = SimpleNamespace(
        id=1,
        title="Vol 1",
        status="in_progress",
        status_label="in progress",
        source_format="epub",
        chapter_count=len(chapters),
        segment_count=sum(c.segment_count for c in chapters),
        chapters=chapters,
        active_batch_job_id=active_batch_job_id,
    )
    return SimpleNamespace(project_name="Proj", volumes=[volume])


def _ch(cid: str, title: str | None, segments: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=cid, title=title, segment_count=segments, translated_count=segments, done_count=segments
    )


def _render(tree: SimpleNamespace) -> str:
    return templates.get_template("partials/_tree.html").render({"tree": tree})


def test_zero_segment_chapter_is_marked_not_progress() -> None:
    tree = _tree_with([_ch("c1", None, 0), _ch("c2", "Ch 2", 7)])
    html = _render(tree)

    # The illustration / front-matter chapter is labelled, not shown as 0/0 work.
    assert "No translatable text" in html
    assert 'class="chapter chapter--empty"' in html
    # A None title falls back to a readable label instead of rendering "None".
    assert ">Untitled<" in html
    assert ">None<" not in html


def test_normal_chapter_still_renders_progress() -> None:
    tree = _tree_with([_ch("c2", "Ch 2", 7)])
    html = _render(tree)

    assert "<progress" in html
    assert "7/7" in html
    assert "No translatable text" not in html


def test_running_batch_reattaches_panel_and_hides_start_button() -> None:
    tree = _tree_with([_ch("c2", "Ch 2", 7)], active_batch_job_id="JOB123")
    html = _render(tree)

    # The slot auto-loads the live panel on page load (reconnect, not reset).
    assert "/batch/jobs/JOB123" in html
    assert 'hx-trigger="load"' in html
    # The start button is hidden while a batch is running (no accidental 2nd job).
    assert "Translate volume" not in html


def test_idle_volume_shows_start_button_and_empty_slot() -> None:
    tree = _tree_with([_ch("c2", "Ch 2", 7)])
    html = _render(tree)

    assert "Translate volume" in html
    assert 'id="batch-vol-1"' in html
    assert "/batch/jobs/" not in html  # nothing to re-attach
