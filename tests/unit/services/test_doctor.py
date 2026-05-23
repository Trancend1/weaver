"""Tests for Phase A9: weaver doctor diagnostic."""

from __future__ import annotations

from pathlib import Path

from weaver.services.doctor import run_doctor
from weaver.services.project import initialize_project

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def test_doctor_without_project_runs_host_checks_only(monkeypatch) -> None:
    monkeypatch.setenv("EDITOR", "notepad")
    report = run_doctor()
    names = {check.name for check in report.checks}
    assert names == {"python", "editor"}
    assert all(check.passed for check in report.checks)


def test_doctor_flags_missing_editor(monkeypatch) -> None:
    monkeypatch.delenv("EDITOR", raising=False)
    report = run_doctor()
    editor_check = next(c for c in report.checks if c.name == "editor")
    assert editor_check.passed is False
    assert "EDITOR is not set" in editor_check.detail
    assert report.all_passed is False


def test_doctor_with_project_runs_full_check_set(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EDITOR", "notepad")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    init = initialize_project(FIXTURE_EPUB)

    report = run_doctor(init.project_toml)

    names = [check.name for check in report.checks]
    assert names == ["python", "editor", "config", "database", "provider-env"]
    assert report.all_passed is True


def test_doctor_flags_missing_provider_env(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EDITOR", "notepad")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    init = initialize_project(FIXTURE_EPUB)

    report = run_doctor(init.project_toml)

    env_check = next(c for c in report.checks if c.name == "provider-env")
    assert env_check.passed is False
    assert "DEEPSEEK_API_KEY" in env_check.detail
    assert report.all_passed is False


def test_doctor_flags_missing_project_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EDITOR", "notepad")
    missing = tmp_path / "does-not-exist.toml"

    report = run_doctor(missing)

    config_check = next(c for c in report.checks if c.name == "config")
    assert config_check.passed is False
    assert "not found" in config_check.detail
