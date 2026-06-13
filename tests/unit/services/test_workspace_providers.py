"""Tests for workspace_providers (Sprint Q6)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from weaver.services.project import initialize_project
from weaver.services.workspace_providers import (
    WorkspaceProviders,
    _resolve_key_env,
    build_workspace_providers,
)

FIXTURE_EPUB = Path(__file__).parents[2] / "fixtures" / "aozora_sample.epub"


def _seed_translation(
    connection: sqlite3.Connection,
    *,
    segment_id: str,
    attempt: int,
    input_tokens: int,
    output_tokens: int,
) -> None:
    connection.execute(
        "INSERT INTO translations "
        "(segment_id, attempt, text, source_hash, provider, model, created_at, "
        "input_tokens, output_tokens) "
        "VALUES (?, ?, 'out', 'h', 'deepseek', 'deepseek-chat', "
        "'2025-01-01T00:00:00+00:00', ?, ?)",
        (segment_id, attempt, input_tokens, output_tokens),
    )


def _seed_failed_job(connection: sqlite3.Connection, *, job_id: str, error: str) -> None:
    connection.execute(
        "INSERT INTO jobs (id, kind, project_name, status, started_at, finished_at, "
        "error_summary) VALUES (?, 'translate', 'alpha', 'failed', "
        "'2025-01-01T00:00:00+00:00', '2025-01-01T00:01:00+00:00', ?)",
        (job_id, error),
    )


# ---------- Basic behaviour ----------


def test_providers_empty_books_dir(tmp_path: Path) -> None:
    providers = build_workspace_providers(tmp_path)
    assert isinstance(providers, WorkspaceProviders)
    assert providers.projects == []
    assert providers.degraded == []


def test_providers_builds_summary(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")

    providers = build_workspace_providers(tmp_path)
    assert len(providers.projects) == 1
    p = providers.projects[0]
    assert p.project_name == "alpha"
    assert p.state == "ready"
    assert p.provider_type == "unknown"
    assert p.model == "—"
    assert p.api_key_env is None
    assert p.requires_key is False
    assert p.input_tokens == 0
    assert p.output_tokens == 0
    assert p.failed_job_count == 0


def test_providers_token_totals(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    db_path = tmp_path / ".weaver" / "alpha" / "weaver.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    seg = conn.execute("SELECT id FROM segments LIMIT 1").fetchone()
    seg_id = str(seg["id"]) if seg is not None else "seg-1"
    _seed_translation(conn, segment_id=seg_id, attempt=1, input_tokens=100, output_tokens=40)
    _seed_translation(conn, segment_id=seg_id, attempt=2, input_tokens=50, output_tokens=10)
    conn.commit()
    conn.close()

    providers = build_workspace_providers(tmp_path)
    p = providers.projects[0]
    assert p.input_tokens == 150
    assert p.output_tokens == 50


def test_providers_failure_summary(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    db_path = tmp_path / ".weaver" / "alpha" / "weaver.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _seed_failed_job(conn, job_id="job-1", error="rate limited")
    _seed_failed_job(conn, job_id="job-2", error="timeout")
    conn.commit()
    conn.close()

    providers = build_workspace_providers(tmp_path)
    p = providers.projects[0]
    assert p.failed_job_count == 2
    msgs = {f.error_summary for f in p.recent_failures}
    assert "rate limited" in msgs
    assert "timeout" in msgs


def test_providers_secret_present_when_env_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha", provider="deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-not-rendered")

    providers = build_workspace_providers(tmp_path)
    assert providers.projects[0].secret_present is True


def test_providers_secret_absent_when_env_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    providers = build_workspace_providers(tmp_path)
    assert providers.projects[0].secret_present is False


def test_providers_sorts_projects(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="zeta")
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="beta")

    providers = build_workspace_providers(tmp_path)
    names = [p.project_name for p in providers.projects]
    assert names == ["alpha", "beta", "zeta"]


# ---------- Key env resolution ----------


def test_resolve_key_env_per_protocol() -> None:
    assert (
        _resolve_key_env({"protocol": "openai_chat", "api_key_env": "DEEPSEEK_API_KEY"})
        == "DEEPSEEK_API_KEY"
    )
    assert (
        _resolve_key_env({"protocol": "gemini_generate", "api_key_env": "GEMINI_API_KEY"})
        == "GEMINI_API_KEY"
    )
    assert _resolve_key_env({"protocol": "ollama_generate"}) is None
    assert _resolve_key_env({"protocol": "fake"}) is None
    assert _resolve_key_env({"protocol": "openai_chat", "api_key_env": "MY_KEY"}) == "MY_KEY"
    assert _resolve_key_env({"protocol": "openai_chat"}) is None


# ---------- Error isolation ----------


def test_providers_isolates_corrupt_project(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="healthy")

    bad_dir = tmp_path / ".weaver" / "corrupt"
    bad_dir.mkdir(parents=True)
    (bad_dir / "weaver.db").write_bytes(b"not sqlite")
    (bad_dir / "project.toml").write_text(
        "[project]\nname = 'corrupt'\nsource_file = ''"
        "\nproject_dir = '.weaver/corrupt'\n"
        "database_path = '.weaver/corrupt/weaver.db'\n"
        "output_dir = '.weaver/corrupt/output'\n"
        "schema_version = 10\n\n[languages]\nsource = 'ja'"
        "\ntarget = 'en'\n\n[provider]\ntype = 'fake'\nmodel = 'fake-1'\n",
        encoding="utf-8",
    )

    providers = build_workspace_providers(tmp_path)
    assert len(providers.projects) == 1
    assert providers.projects[0].project_name == "healthy"
    assert any(d.name == "corrupt" and d.state == "error" for d in providers.degraded)


def test_providers_needs_upgrade_for_v8(tmp_path: Path) -> None:
    from tests.unit.services.test_workspace_index import _create_v8_project

    _create_v8_project(tmp_path, "legacy")
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="modern")

    providers = build_workspace_providers(tmp_path)
    degraded_states = {d.name: d.state for d in providers.degraded}
    assert degraded_states.get("legacy") == "needs_upgrade"
    assert "modern" in {p.project_name for p in providers.projects}


def test_providers_identity_conflict_degraded(tmp_path: Path) -> None:
    import shutil

    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="original")
    copy_dir = tmp_path / ".weaver" / "duplicate"
    (tmp_path / ".weaver" / "original").replace(copy_dir)
    shutil.copytree(copy_dir, tmp_path / ".weaver" / "original", dirs_exist_ok=True)

    providers = build_workspace_providers(tmp_path)
    degraded_states = {d.name: d.state for d in providers.degraded}
    assert degraded_states.get("original") == "identity_conflict"
    assert degraded_states.get("duplicate") == "identity_conflict"


# ---------- No-write / no-provider-call regression ----------


def test_providers_does_not_modify_database(tmp_path: Path) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="readonly")
    db_path = tmp_path / ".weaver" / "readonly" / "weaver.db"
    mtime_before = db_path.stat().st_mtime_ns
    size_before = db_path.stat().st_size

    build_workspace_providers(tmp_path)

    assert db_path.stat().st_mtime_ns == mtime_before
    assert db_path.stat().st_size == size_before


def test_providers_never_instantiates_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_project(FIXTURE_EPUB, cwd=tmp_path, project_name="alpha")

    calls = {"n": 0}

    def _spy(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        calls["n"] += 1
        raise AssertionError("provider must not be built on render")

    monkeypatch.setattr("weaver.providers.registry.build_provider", _spy)
    build_workspace_providers(tmp_path)
    assert calls["n"] == 0
