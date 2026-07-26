"""Smoke tests for the Phase 0 skeleton + the release version drift guard."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

import weaver
from weaver.cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
TAURI_CONF = REPO_ROOT / "desktop" / "tauri.conf.json"


def _pyproject_version() -> str:
    if not PYPROJECT.exists():
        pytest.skip("pyproject.toml not present (running outside the repo tree)")
    with PYPROJECT.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def test_version_string_is_set() -> None:
    assert weaver.__version__
    assert isinstance(weaver.__version__, str)


def test_cli_version_flag_exits_zero() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0, result.output
    assert weaver.__version__ in result.output


def test_package_version_matches_pyproject() -> None:
    """`pyproject.toml` is the single source of truth (docs/MAINTENANCE.md).

    The other version tests only compare `__version__` against itself, so they
    stay green no matter how far it drifts — `__version__` sat at 0.7.0 through
    both the v0.7.1 and v0.7.2 releases, making `weaver --version` and
    `GET /version` under-report the shipped build. This is the only assertion
    that can catch that.
    """

    assert weaver.__version__ == _pyproject_version()


def test_desktop_version_matches_pyproject() -> None:
    """Mirror of `desktop/scripts/check-version.ps1` so drift fails in pytest too."""

    if not TAURI_CONF.exists():
        pytest.skip("desktop/tauri.conf.json not present")
    tauri_version = json.loads(TAURI_CONF.read_text(encoding="utf-8"))["version"]

    assert tauri_version == _pyproject_version()
