"""Tests for ruby annotation filtering in EPUB text extraction.

``_element_text()`` must skip ``<rt>`` and ``<rp>`` elements so that
furigana readings and fallback punctuation do not leak into source segments.
"""

from __future__ import annotations

from xml.etree import ElementTree

from weaver.readers.epub import _element_text

_XHTML_NS = "http://www.w3.org/1999/xhtml"


def test_rt_reading_is_excluded() -> None:
    xhtml = f'<p xmlns="{_XHTML_NS}">吾輩は<ruby>猫<rt>ねこ</rt></ruby>である</p>'
    element = ElementTree.fromstring(xhtml)
    assert _element_text(element) == "吾輩は猫である"


def test_rp_fallback_punctuation_is_excluded() -> None:
    xhtml = f'<p xmlns="{_XHTML_NS}"><ruby>漢字<rp>(</rp><rt>かんじ</rt><rp>)</rp></ruby></p>'
    element = ElementTree.fromstring(xhtml)
    assert _element_text(element) == "漢字"


def test_adjacent_ruby_bases_preserve_base_text() -> None:
    xhtml = f'<p xmlns="{_XHTML_NS}"><ruby>漢<rt>かん</rt>字<rt>じ</rt></ruby></p>'
    element = ElementTree.fromstring(xhtml)
    assert _element_text(element) == "漢字"


def test_ruby_with_surrounding_paragraph_text() -> None:
    xhtml = f'<p xmlns="{_XHTML_NS}">これは<ruby>日本語<rt>にほんご</rt></ruby>のテストです</p>'
    element = ElementTree.fromstring(xhtml)
    assert _element_text(element) == "これは日本語のテストです"


def test_ruby_without_rt_is_preserved() -> None:
    xhtml = f'<p xmlns="{_XHTML_NS}"><ruby>日本語</ruby>です</p>'
    element = ElementTree.fromstring(xhtml)
    assert _element_text(element) == "日本語です"
