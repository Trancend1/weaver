"""WV-014 characterization tests: ruby / vertical-text fidelity.

These tests verify EPUB text extraction behavior after the Sprint Q11
ruby-annotation fix (Commit 4). ``_element_text()`` now skips ``<rt>`` and
``<rp>`` elements, so furigana readings and fallback punctuation no longer
leak into the source segment. See ``docs/audit/WV-014_RUBY_VERTICAL_TEXT_SPIKE.md``
for the original spike findings and ``tests/unit/readers/test_epub_ruby.py``
for comprehensive coverage.
"""

from __future__ import annotations

from xml.etree import ElementTree

from weaver.readers.epub import _element_text

_XHTML_NS = "http://www.w3.org/1999/xhtml"


def test_ruby_reading_is_excluded() -> None:
    xhtml = f'<p xmlns="{_XHTML_NS}">吾輩は<ruby>猫<rt>ねこ</rt></ruby>である</p>'
    element = ElementTree.fromstring(xhtml)

    assert _element_text(element) == "吾輩は猫である"


def test_ruby_with_fallback_parens_excluded() -> None:
    xhtml = f'<p xmlns="{_XHTML_NS}"><ruby>漢字<rp>(</rp><rt>かんじ</rt><rp>)</rp></ruby></p>'
    element = ElementTree.fromstring(xhtml)

    assert _element_text(element) == "漢字"
