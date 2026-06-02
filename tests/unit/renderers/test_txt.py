"""Tests for the plain-text export renderer (Sprint 8C)."""

from __future__ import annotations

from pathlib import Path

from weaver.renderers.rendered_document import RenderChapter
from weaver.renderers.txt import render_txt


def test_render_txt_writes_blocks_in_order(tmp_path: Path) -> None:
    chapters = [
        RenderChapter(title="第1章", blocks=(("heading", "第1章"), ("paragraph", "おはよう"))),
        RenderChapter(title=None, blocks=(("paragraph", "P2"),)),
    ]
    out = tmp_path / "out" / "vol.txt"

    result = render_txt(output_path=out, title="My Volume", chapters=chapters)

    assert out.exists()
    assert result.chapters == 2
    assert result.blocks == 3
    text = out.read_text(encoding="utf-8")
    assert "My Volume" in text
    assert "おはよう" in text
    assert text.index("第1章") < text.index("おはよう") < text.index("P2")


def test_render_txt_empty_chapters(tmp_path: Path) -> None:
    out = tmp_path / "empty.txt"
    result = render_txt(output_path=out, title="T", chapters=[])
    assert out.exists()
    assert result.blocks == 0
