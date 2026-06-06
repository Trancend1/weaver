"""Scope-level QA checks (Phase B / Stage B2)."""

from __future__ import annotations

from weaver.qa.checks import SegmentInput
from weaver.qa.scope_checks import (
    FALLBACK_HEAVY_MIN_SEGMENTS,
    check_fallback_heavy,
    check_mixed_status,
    check_repeated_identical_translation,
)


def _seg(
    segment_id: str,
    *,
    status: str = "translated",
    source: str = "ソース",
    translation: str | None = "A reasonably long translation.",
) -> SegmentInput:
    return SegmentInput(
        segment_id=segment_id,
        source_text=source,
        normalized_source_text=source,
        status=status,
        translation_text=translation,
    )


def test_repeated_flags_distinct_sources_sharing_a_translation() -> None:
    segments = [
        _seg("a", source="アア", translation="The exact same sentence."),
        _seg("b", source="イイ", translation="The exact same sentence."),
    ]
    findings = check_repeated_identical_translation(segments)
    assert {f.segment_id for f in findings} == {"a", "b"}
    assert all(f.check_name == "repeated_identical_translation" for f in findings)
    assert all(f.severity == "warning" for f in findings)


def test_repeated_ignores_identical_sources() -> None:
    segments = [
        _seg("a", source="同じ文", translation="The exact same sentence."),
        _seg("b", source="同じ文", translation="The exact same sentence."),
    ]
    assert check_repeated_identical_translation(segments) == []


def test_repeated_ignores_short_translations() -> None:
    segments = [
        _seg("a", source="ア", translation="Yes."),
        _seg("b", source="イ", translation="Yes."),
    ]
    assert check_repeated_identical_translation(segments) == []


def test_repeated_ignores_unique_translations() -> None:
    segments = [
        _seg("a", source="ア", translation="First long sentence here."),
        _seg("b", source="イ", translation="Second long sentence here."),
    ]
    assert check_repeated_identical_translation(segments) == []


def test_repeated_ignores_unpublished_segments() -> None:
    segments = [
        _seg("a", status="pending", source="ア", translation="The exact same sentence."),
        _seg("b", status="failed", source="イ", translation="The exact same sentence."),
    ]
    assert check_repeated_identical_translation(segments) == []


def test_fallback_heavy_flags_majority_unpublished() -> None:
    warning = check_fallback_heavy(total_segments=10, fallback_segments=6)
    assert warning is not None
    assert warning.check_name == "fallback_heavy_chapter"
    assert warning.severity == "warning"


def test_fallback_heavy_below_ratio_is_clean() -> None:
    assert check_fallback_heavy(total_segments=10, fallback_segments=4) is None


def test_fallback_heavy_below_min_segments_is_clean() -> None:
    n = FALLBACK_HEAVY_MIN_SEGMENTS - 1
    assert check_fallback_heavy(total_segments=n, fallback_segments=n) is None


def test_repeated_honors_custom_min_chars() -> None:
    # "Yes." is 4 chars — ignored at the default 8, flagged when min_chars drops.
    segments = [
        _seg("a", source="ア", translation="Yes."),
        _seg("b", source="イ", translation="Yes."),
    ]
    assert check_repeated_identical_translation(segments, min_chars=3) != []
    assert check_repeated_identical_translation(segments, min_chars=8) == []


def test_fallback_heavy_honors_custom_thresholds() -> None:
    # 3/3 = 100% fallback: clean at the default min_segments=5, flagged at min_segments=1.
    assert check_fallback_heavy(total_segments=3, fallback_segments=3, min_segments=1) is not None
    assert check_fallback_heavy(total_segments=3, fallback_segments=3) is None
    # A stricter ratio suppresses a borderline chapter.
    assert check_fallback_heavy(total_segments=10, fallback_segments=6, heavy_ratio=0.7) is None


def test_mixed_status_flags_partial_chapter() -> None:
    warning = check_mixed_status([_seg("a", status="translated"), _seg("b", status="pending")])
    assert warning is not None
    assert warning.check_name == "mixed_status_chapter"
    assert warning.severity == "info"


def test_mixed_status_all_published_is_clean() -> None:
    assert check_mixed_status([_seg("a", status="translated"), _seg("b", status="manual")]) is None


def test_mixed_status_all_unpublished_is_clean() -> None:
    assert check_mixed_status([_seg("a", status="pending"), _seg("b", status="failed")]) is None
