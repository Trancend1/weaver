"""`weaver doctor` diagnostic: surface env / DB / provider config gaps.

Project-agnostic checks (no project_toml needed): Python version, $EDITOR.
Project-aware checks (require project_toml): config schema valid, database
opens in WAL mode, provider env var present for the configured provider type.
Optional `--healthcheck` adds a provider reachability probe.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.config import load_project_config
from weaver.errors import ConfigError, WeaverError
from weaver.providers import build_provider
from weaver.providers.deepseek import ENV_API_KEY as DEEPSEEK_ENV_KEY
from weaver.providers.gemini import ENV_API_KEY as GEMINI_ENV_KEY
from weaver.storage.db import connect_readonly_database

MIN_PYTHON = (3, 11)

PROVIDER_ENV_VARS: dict[str, str] = {
    "deepseek": DEEPSEEK_ENV_KEY,
    "gemini": GEMINI_ENV_KEY,
}


@dataclass(frozen=True)
class DoctorCheck:
    """One diagnostic check outcome."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class DoctorReport:
    """Result of one `weaver doctor` run."""

    checks: tuple[DoctorCheck, ...]

    @property
    def all_passed(self) -> bool:
        return all(check.passed for check in self.checks)


def run_doctor(
    project_toml: Path | None = None,
    *,
    cwd: Path | None = None,
    run_healthcheck: bool = False,
) -> DoctorReport:
    """Run diagnostic checks.

    Args:
        project_toml: Optional project file. Without it, only host-level checks run.
        cwd: Working directory used to resolve relative project paths.
        run_healthcheck: When True and a project is supplied, probe the configured
            provider for reachability.

    Returns:
        DoctorReport whose `all_passed` is True only if every check passed.
    """

    checks: list[DoctorCheck] = []
    checks.append(_check_python_version())
    checks.append(_check_editor_env())

    if project_toml is not None:
        config_check, parsed = _check_config_load(project_toml)
        checks.append(config_check)
        if parsed is not None:
            checks.append(_check_database_wal(project_toml, parsed, cwd or Path.cwd()))
            checks.append(_check_provider_env_var(parsed))
            if run_healthcheck:
                checks.append(_check_provider_healthcheck(parsed))

    return DoctorReport(checks=tuple(checks))


def _check_python_version() -> DoctorCheck:
    if sys.version_info >= MIN_PYTHON:
        return DoctorCheck(
            name="python",
            passed=True,
            detail=f"Python {sys.version_info.major}.{sys.version_info.minor} >= 3.11",
        )
    return DoctorCheck(
        name="python",
        passed=False,
        detail=(
            f"Python {sys.version_info.major}.{sys.version_info.minor} is below 3.11. "
            "Install Python 3.11+ and reinstall weaver."
        ),
    )


def _check_editor_env() -> DoctorCheck:
    editor = os.environ.get("EDITOR")
    if editor:
        return DoctorCheck(name="editor", passed=True, detail=f"EDITOR={editor}")
    return DoctorCheck(
        name="editor",
        passed=False,
        detail="EDITOR is not set. `weaver edit` and `weaver glossary edit` will fail.",
    )


def _check_config_load(
    project_toml: Path,
) -> tuple[DoctorCheck, dict[str, object] | None]:
    if not project_toml.exists():
        return (
            DoctorCheck(
                name="config",
                passed=False,
                detail=f"project file not found: {project_toml}",
            ),
            None,
        )
    try:
        data = load_project_config(project_toml)
    except ConfigError as exc:
        return (
            DoctorCheck(
                name="config",
                passed=False,
                detail=f"project.toml invalid: {exc}",
            ),
            None,
        )
    return (
        DoctorCheck(
            name="config",
            passed=True,
            detail=f"project.toml parsed ({project_toml})",
        ),
        data,
    )


def _check_database_wal(project_toml: Path, parsed: dict[str, object], cwd: Path) -> DoctorCheck:
    db_value = str((parsed["project"])["database_path"])  # type: ignore[index]
    db_path = _resolve_path(db_value, cwd, project_toml.parent)
    if not db_path.exists():
        return DoctorCheck(
            name="database",
            passed=False,
            detail=f"database file not found: {db_path}",
        )
    try:
        with closing(connect_readonly_database(db_path)) as connection:
            mode_row = connection.execute("PRAGMA journal_mode").fetchone()
    except sqlite3.DatabaseError as exc:
        return DoctorCheck(
            name="database",
            passed=False,
            detail=f"cannot open database: {exc}",
        )
    journal_mode = str(mode_row[0]).lower() if mode_row else ""
    if journal_mode != "wal":
        return DoctorCheck(
            name="database",
            passed=False,
            detail=f"journal_mode is `{journal_mode}`, expected `wal`",
        )
    return DoctorCheck(name="database", passed=True, detail=f"WAL mode at {db_path}")


def _check_provider_env_var(parsed: dict[str, object]) -> DoctorCheck:
    provider_type = str((parsed["provider"])["type"])  # type: ignore[index]
    env_var = PROVIDER_ENV_VARS.get(provider_type)
    if env_var is None:
        return DoctorCheck(
            name="provider-env",
            passed=True,
            detail=f"provider `{provider_type}` does not require an API key env var",
        )
    if os.environ.get(env_var):
        return DoctorCheck(
            name="provider-env",
            passed=True,
            detail=f"${env_var} is set",
        )
    return DoctorCheck(
        name="provider-env",
        passed=False,
        detail=f"${env_var} is not set. Required by provider `{provider_type}`.",
    )


def _check_provider_healthcheck(parsed: dict[str, object]) -> DoctorCheck:
    provider_config = parsed["provider"]
    try:
        provider = build_provider(provider_config)  # type: ignore[arg-type]
    except WeaverError as exc:
        return DoctorCheck(
            name="provider-healthcheck",
            passed=False,
            detail=f"cannot build provider: {exc}",
        )
    status = provider.healthcheck()
    if status.healthy:
        return DoctorCheck(
            name="provider-healthcheck",
            passed=True,
            detail=f"{status.provider_name} reachable (latency_ms={status.latency_ms})",
        )
    message = status.message or "no detail returned"
    return DoctorCheck(
        name="provider-healthcheck",
        passed=False,
        detail=f"{status.provider_name} unhealthy: {message}",
    )


def _resolve_path(path_value: str, cwd: Path, project_toml_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    cwd_path = cwd / path
    if cwd_path.exists():
        return cwd_path
    return project_toml_dir / path
