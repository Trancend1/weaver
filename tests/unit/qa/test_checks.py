"""Unit tests for Phase 9 deterministic QA checks."""

from __future__ import annotations

from weaver.providers.types import GlossaryTerm
from weaver.qa.checks import (
    SegmentInput,
    check_empty_translation,
    check_failed_segment,
    check_glossary_mismatch,
    check_length_ratio,
    check_stale_segment,
    check_untranslated_japanese,
    run_all_checks,
)


def _segment(
    *,
    status: str = "translated",
    source_text: str = "原文",
    translation_text: str | None = "translation",
    segment_id: str = "seg-1",
) -> SegmentInput:
    return SegmentInput(
        segment_id=segment_id,
        source_text=source_text,
        normalized_source_text=source_text,
        status=status,
        translation_text=translation_text,
    )


def test_check_empty_translation_flags_blank_translated_segment() -> None:
    warning = check_empty_translation(_segment(translation_text="   "))
    assert warning is not None
    assert warning.severity == "critical"
    assert warning.check_name == "empty_translation"


def test_check_empty_translation_skips_pending_segment() -> None:
    assert check_empty_translation(_segment(status="pending", translation_text=None)) is None


def test_check_empty_translation_skips_when_text_present() -> None:
    assert check_empty_translation(_segment(translation_text="ok")) is None


def test_check_untranslated_japanese_flags_four_or_more_contiguous_chars() -> None:
    warning = check_untranslated_japanese(_segment(translation_text="Hello 吾輩は猫である world"))
    assert warning is not None
    assert warning.severity == "critical"
    assert warning.check_name == "untranslated_japanese"


def test_check_untranslated_japanese_ignores_three_or_fewer_chars() -> None:
    assert check_untranslated_japanese(_segment(translation_text="Mr. 田中三 said")) is None


def test_check_untranslated_japanese_ignores_ascii_only() -> None:
    assert check_untranslated_japanese(_segment(translation_text="plain ASCII text")) is None


def test_check_length_ratio_flags_below_threshold() -> None:
    warning = check_length_ratio(
        _segment(source_text="x" * 100, translation_text="short"),
        minimum_ratio=0.3,
    )
    assert warning is not None
    assert warning.severity == "warning"
    assert warning.check_name == "length_ratio"


def test_check_length_ratio_passes_at_threshold() -> None:
    assert (
        check_length_ratio(
            _segment(source_text="x" * 10, translation_text="y" * 3),
            minimum_ratio=0.3,
        )
        is None
    )


def test_check_length_ratio_skips_empty_translation() -> None:
    assert (
        check_length_ratio(
            _segment(source_text="x" * 10, translation_text="   "),
            minimum_ratio=0.3,
        )
        is None
    )


def test_check_glossary_mismatch_flags_when_target_absent() -> None:
    terms = [GlossaryTerm(source="護衛", target="bodyguard")]
    segment = _segment(source_text="護衛がいる", translation_text="A guard appears.")
    findings = check_glossary_mismatch(segment, terms)
    assert len(findings) == 1
    assert findings[0].check_name == "glossary_mismatch"
    assert findings[0].severity == "warning"


def test_check_glossary_mismatch_silent_when_target_present() -> None:
    terms = [GlossaryTerm(source="護衛", target="bodyguard")]
    segment = _segment(source_text="護衛がいる", translation_text="A bodyguard appears.")
    assert check_glossary_mismatch(segment, terms) == []


def test_check_glossary_mismatch_respects_case_sensitive_flag() -> None:
    terms = [GlossaryTerm(source="Kai", target="Kai", case_sensitive=True)]
    segment = _segment(source_text="Kai walks", translation_text="kai walks")
    findings = check_glossary_mismatch(segment, terms)
    assert len(findings) == 1


def test_check_failed_segment_flags_failed_status() -> None:
    warning = check_failed_segment(_segment(status="failed", translation_text=None))
    assert warning is not None
    assert warning.severity == "critical"
    assert warning.check_name == "failed_segment"


def test_check_stale_segment_flags_stale_status() -> None:
    warning = check_stale_segment(_segment(status="stale"))
    assert warning is not None
    assert warning.severity == "warning"
    assert warning.check_name == "stale_segment"


def test_run_all_checks_respects_disable_flags() -> None:
    segment = _segment(
        status="translated",
        source_text="x" * 100,
        translation_text="Mr. 吾輩は猫である appeared.",
    )
    findings = run_all_checks(
        segment,
        glossary_terms=[],
        detect_empty=False,
        detect_japanese=False,
        detect_glossary_mismatch=False,
    )
    assert findings == []


def test_run_all_checks_always_runs_status_checks() -> None:
    segment = _segment(status="failed", translation_text=None)
    findings = run_all_checks(
        segment,
        glossary_terms=[],
        detect_empty=False,
        detect_japanese=False,
        detect_glossary_mismatch=False,
    )
    assert len(findings) == 1
    assert findings[0].check_name == "failed_segment"
