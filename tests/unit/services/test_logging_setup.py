"""Tests for ``services.logging_setup`` (Sprint G6)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from weaver.services.app_paths import AppPaths
from weaver.services.logging_setup import (
    LOG_FILES,
    install_logging,
    log_backend_event,
    log_export_event,
    log_job_event,
    log_provider_event,
    log_runtime_event,
    read_log_file,
    reset_logging,
    scrub_provider_record,
)


@pytest.fixture
def paths(tmp_path: Path):
    paths = AppPaths(root=tmp_path / "data")
    reset_logging()  # clear any handlers from prior tests (G6 install is idempotent)
    install_logging(paths)
    yield paths
    reset_logging()


def test_install_creates_all_five_log_files(paths: AppPaths) -> None:
    log_runtime_event("runtime.start", env="dev")
    log_backend_event("backend.boot")
    log_job_event("job.submitted", job_id="abc")
    log_export_event("export.start", target="epub")
    log_provider_event("provider.invoke", provider="fake")

    for filename in LOG_FILES:
        path = paths.logs_dir / filename
        assert path.is_file(), f"missing {filename}"


def test_runtime_event_payload_is_json_lines(paths: AppPaths) -> None:
    log_runtime_event("runtime.start", env="dev", port=8765)

    lines = read_log_file(paths, "runtime.log")
    assert len(lines) == 1
    entry = lines[0]
    assert entry["event"] == "runtime.start"
    assert entry["env"] == "dev"
    assert entry["port"] == 8765
    assert "ts" in entry
    assert entry["level"] == "INFO"


def test_provider_log_redacts_secret_shaped_fields(paths: AppPaths) -> None:
    log_provider_event(
        "provider.invoke",
        provider="deepseek",
        model="deepseek-chat",
        api_key="sk-secret-value",
        AUTH_TOKEN="bearer abc",
        Authorization="Bearer xyz",
        password="hunter2",
        latency_ms=42,
    )

    lines = read_log_file(paths, "provider.log")
    assert len(lines) == 1
    entry = lines[0]
    # Visible fields preserved.
    assert entry["provider"] == "deepseek"
    assert entry["model"] == "deepseek-chat"
    assert entry["latency_ms"] == 42
    # Secret-shaped fields redacted.
    assert entry["api_key"] == "<redacted>"
    assert entry["AUTH_TOKEN"] == "<redacted>"
    assert entry["Authorization"] == "<redacted>"
    assert entry["password"] == "<redacted>"

    # Belt-and-braces: the literal secret strings never appear in the file.
    raw = (paths.logs_dir / "provider.log").read_text(encoding="utf-8")
    assert "sk-secret-value" not in raw
    assert "bearer abc" not in raw
    assert "Bearer xyz" not in raw
    assert "hunter2" not in raw


def test_provider_log_contains_no_api_keys_regression(paths: AppPaths) -> None:
    # Simulates a noisy callsite trying every shape an API key might take.
    log_provider_event(
        "provider.invoke",
        api_key="DEEPSEEK_KEY_VALUE",
        DEEPSEEK_API_KEY="another-secret",
        Bearer_Token="rotating-token",
        client_secret="oauth-thing",
    )

    raw = (paths.logs_dir / "provider.log").read_text(encoding="utf-8")
    # Every value above must be absent.
    for needle in (
        "DEEPSEEK_KEY_VALUE",
        "another-secret",
        "rotating-token",
        "oauth-thing",
    ):
        assert needle not in raw, f"{needle!r} leaked into provider.log"


def test_install_is_idempotent(paths: AppPaths) -> None:
    install_logging(paths)
    install_logging(paths)
    log_runtime_event("runtime.tick")

    # No duplicate handlers → exactly one line per event.
    lines = read_log_file(paths, "runtime.log")
    assert len(lines) == 1


def test_scrub_handles_nested_value_types() -> None:
    cleaned = scrub_provider_record(
        {
            "api_key": "abc",
            "model": "x",
            "MIXED_token_field": "y",
            "ok_field": 1,
        }
    )
    assert cleaned["api_key"] == "<redacted>"
    assert cleaned["MIXED_token_field"] == "<redacted>"
    assert cleaned["model"] == "x"
    assert cleaned["ok_field"] == 1


def test_managed_handlers_do_not_leak_to_root_logger(paths: AppPaths) -> None:
    # weaver.* loggers do not propagate; root logger receives no rotating-file output.
    handler_files = []
    for handler in logging.getLogger().handlers:
        baseFilename = getattr(handler, "baseFilename", None)
        if baseFilename:
            handler_files.append(baseFilename)
    for path in handler_files:
        assert "runtime.log" not in path
        assert "provider.log" not in path


def test_reset_logging_closes_handles(tmp_path: Path) -> None:
    paths = AppPaths(root=tmp_path / "data")
    install_logging(paths)
    log_runtime_event("once")
    reset_logging()

    # After reset, calling install with a new dir works without conflict.
    fresh = AppPaths(root=tmp_path / "fresh")
    install_logging(fresh)
    log_runtime_event("again")
    reset_logging()

    assert (fresh.logs_dir / "runtime.log").is_file()
    parsed = json.loads(
        (fresh.logs_dir / "runtime.log").read_text(encoding="utf-8").splitlines()[0]
    )
    assert parsed["event"] == "again"
