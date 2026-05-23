"""Unit tests for the preview service."""

from __future__ import annotations

import pytest

from weaver.services.preview import PreviewBlock


def test_preview_block_is_frozen() -> None:
    block = PreviewBlock(
        segment_id="abc123",
        chapter_index=1,
        chapter_title="Test Chapter",
        source_text="テスト",
        translation="Test",
        status="translated",
    )
    with pytest.raises(AttributeError):
        block.status = "failed"  # type: ignore[misc]


def test_preview_block_fields() -> None:
    block = PreviewBlock(
        segment_id="abc123",
        chapter_index=1,
        chapter_title="Chapter One",
        source_text="テスト",
        translation=None,
        status="pending",
    )
    assert block.segment_id == "abc123"
    assert block.chapter_index == 1
    assert block.chapter_title == "Chapter One"
    assert block.source_text == "テスト"
    assert block.translation is None
    assert block.status == "pending"
