"""Tests for the Draft/Final export gate (Sprint Q7)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from weaver.services import export_gate
from weaver.services.export_gate import evaluate_export_gate


@dataclass(frozen=True)
class _FakeReport:
    badge: str
    critical_count: int


def _no_qa(*args: object, **kwargs: object) -> object:
    _ = (args, kwargs)
    raise AssertionError("QA must not run for this gate path")


def _patch_report(monkeypatch: pytest.MonkeyPatch, *, badge: str, critical_count: int) -> None:
    monkeypatch.setattr(
        export_gate,
        "analyze_novel",
        lambda *a, **kw: _FakeReport(badge=badge, critical_count=critical_count),
    )


def test_draft_always_allowed_without_running_qa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_gate, "analyze_novel", _no_qa)
    decision = evaluate_export_gate(Path("project.toml"), kind="draft", require_clean=True)
    assert decision.allowed is True
    assert decision.kind == "draft"
    assert decision.qa_badge is None


def test_final_without_require_clean_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_gate, "analyze_novel", _no_qa)
    decision = evaluate_export_gate(Path("project.toml"), kind="final", require_clean=False)
    assert decision.allowed is True
    assert decision.kind == "final"


def test_final_require_clean_refuses_with_criticals(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_report(monkeypatch, badge="errors", critical_count=3)
    decision = evaluate_export_gate(Path("project.toml"), kind="final", require_clean=True)
    assert decision.allowed is False
    assert decision.critical_count == 3
    assert decision.qa_badge == "errors"
    assert decision.reason is not None and "3" in decision.reason


def test_final_require_clean_allows_when_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_report(monkeypatch, badge="clean", critical_count=0)
    decision = evaluate_export_gate(Path("project.toml"), kind="final", require_clean=True)
    assert decision.allowed is True
    assert decision.qa_badge == "clean"
    assert decision.reason is None


def test_unknown_kind_falls_back_to_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_gate, "analyze_novel", _no_qa)
    decision = evaluate_export_gate(Path("project.toml"), kind="bogus", require_clean=True)
    assert decision.allowed is True
    assert decision.kind == "draft"
