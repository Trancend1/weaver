"""WV-014 characterization tests: ruby / vertical-text fidelity.

These tests pin the *current* behavior of EPUB text extraction so a future
fidelity fix is a deliberate, reviewed change rather than an accident. They are
investigation artifacts for the Sprint Q11 spike — see
``.docs/audit/WV-014_RUBY_VERTICAL_TEXT_SPIKE.md`` — not a contract anyone should
rely on. The headline finding: the importer flattens ``<ruby>`` via
``itertext()``, so the furigana reading (``<rt>``) leaks into the source segment.
"""

from __future__ import annotations

from xml.etree import ElementTree

from weaver.readers.epub import _element_text

_XHTML_NS = "http://www.w3.org/1999/xhtml"


def test_ruby_reading_leaks_into_source_text() -> None:
    # <ruby>base<rt>reading</rt></ruby> — itertext() concatenates base + reading.
    xhtml = f'<p xmlns="{_XHTML_NS}">吾輩は<ruby>猫<rt>ねこ</rt></ruby>である</p>'
    element = ElementTree.fromstring(xhtml)

    # CURRENT behavior: the reading is merged onto the base ("猫ねこ"), not stripped.
    assert _element_text(element) == "吾輩は猫ねこである"


def test_ruby_with_fallback_parens_also_leak() -> None:
    # The <rp> fallback parentheses are likewise concatenated inline.
    xhtml = f'<p xmlns="{_XHTML_NS}"><ruby>漢字<rp>(</rp><rt>かんじ</rt><rp>)</rp></ruby></p>'
    element = ElementTree.fromstring(xhtml)

    assert _element_text(element) == "漢字(かんじ)"
