"""Per-segment consistency checks (Phase B / Stage B2)."""

from __future__ import annotations

from weaver.qa.checks import SegmentInput
from weaver.qa.consistency_checks import (
    CharacterName,
    check_character_name_missing,
    check_untranslated_segment,
)


def _seg(
    *,
    status: str = "translated",
    source: str = "ソース",
    translation: str | None = "English text.",
    segment_id: str = "s1",
) -> SegmentInput:
    return SegmentInput(
        segment_id=segment_id,
        source_text=source,
        normalized_source_text=source,
        status=status,
        translation_text=translation,
    )


def test_untranslated_segment_flags_pending_in_progress_skipped() -> None:
    for status in ("pending", "in_progress", "skipped"):
        warning = check_untranslated_segment(_seg(status=status, translation=None))
        assert warning is not None
        assert warning.check_name == "untranslated_segment"
        assert warning.severity == "warning"


def test_untranslated_segment_skips_published_and_terminal_statuses() -> None:
    # published, and the statuses already owned by failed/stale checks
    for status in ("translated", "manual", "failed", "stale"):
        assert check_untranslated_segment(_seg(status=status)) is None


def test_character_name_missing_flags_absent_english_name() -> None:
    seg = _seg(source="エリナは笑った。", translation="She laughed.")
    findings = check_character_name_missing(seg, [CharacterName("エリナ", "Erina")])
    assert len(findings) == 1
    assert findings[0].check_name == "character_name_missing"
    assert findings[0].severity == "warning"
    assert findings[0].segment_id == "s1"


def test_character_name_present_in_translation_is_clean() -> None:
    seg = _seg(source="エリナは笑った。", translation="Erina laughed.")
    assert check_character_name_missing(seg, [CharacterName("エリナ", "Erina")]) == []


def test_character_name_absent_from_source_is_clean() -> None:
    seg = _seg(source="猫がいる。", translation="A cat is here.")
    assert check_character_name_missing(seg, [CharacterName("エリナ", "Erina")]) == []


def test_character_name_missing_skips_empty_translation() -> None:
    assert (
        check_character_name_missing(
            _seg(source="エリナ", translation=None), [CharacterName("エリナ", "Erina")]
        )
        == []
    )
    assert (
        check_character_name_missing(
            _seg(source="エリナ", translation="   "), [CharacterName("エリナ", "Erina")]
        )
        == []
    )


def test_character_name_missing_handles_multiple_characters() -> None:
    seg = _seg(source="エリナと魔王が戦う。", translation="She fights the demon lord.")
    findings = check_character_name_missing(
        seg, [CharacterName("エリナ", "Erina"), CharacterName("魔王", "Demon King")]
    )
    assert {f.message.split()[1] for f in findings}  # both flagged
    assert len(findings) == 2
