"""Segment identity and source hash tests."""

from __future__ import annotations

from weaver.core.segment import compute_segment_id, compute_source_hash, is_source_stale


def test_segment_id_is_deterministic_across_runs() -> None:
    first = compute_segment_id(
        chapter_href="text/chapter01.xhtml",
        dom_path="/html/body/section[1]/p[1]",
        paragraph_index=0,
    )
    second = compute_segment_id(
        chapter_href="text/chapter01.xhtml",
        dom_path="/html/body/section[1]/p[1]",
        paragraph_index=0,
    )

    assert first == second
    assert len(first) == 16


def test_segment_id_changes_when_dom_path_changes() -> None:
    original = compute_segment_id(
        chapter_href="text/chapter01.xhtml",
        dom_path="/html/body/section[1]/p[1]",
        paragraph_index=0,
    )
    moved = compute_segment_id(
        chapter_href="text/chapter01.xhtml",
        dom_path="/html/body/section[1]/p[2]",
        paragraph_index=0,
    )

    assert moved != original


def test_source_hash_uses_normalized_source_text() -> None:
    full_width = compute_source_hash("Ｈｅｌｌｏ　世界")
    normalized = compute_source_hash("Hello 世界")

    assert full_width == normalized
    assert len(full_width) == 64


def test_stale_detection_flags_changed_source_hash() -> None:
    stored_hash = compute_source_hash("猫がいる。")
    current_hash = compute_source_hash("猫がいた。")

    assert is_source_stale(stored_hash=stored_hash, current_source_hash=current_hash)
    assert not is_source_stale(stored_hash=stored_hash, current_source_hash=stored_hash)
