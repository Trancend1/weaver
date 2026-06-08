"""Tests for ``services.app_paths`` (Sprint G2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from weaver.services.app_paths import (
    APP_DIR_POSIX,
    APP_NAME,
    DATA_DIR_ENV,
    AppPaths,
    default_root,
    resolve_app_paths,
)


def test_resolve_honors_data_dir_env(tmp_path: Path) -> None:
    paths = resolve_app_paths(env={DATA_DIR_ENV: str(tmp_path)})

    assert paths.root == tmp_path.resolve()
    assert paths.logs_dir == tmp_path.resolve() / "logs"
    assert paths.cache_dir == tmp_path.resolve() / "cache"
    assert paths.export_dir == tmp_path.resolve() / "exports"
    assert paths.temp_dir == tmp_path.resolve() / "tmp"
    assert paths.workspace_dir == tmp_path.resolve() / "workspace"
    assert paths.database_dir == tmp_path.resolve() / "db"


def test_resolve_with_empty_env_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATA_DIR_ENV, raising=False)
    paths = resolve_app_paths(env={})

    assert paths.root == default_root()


def test_resolve_ignores_blank_override(tmp_path: Path) -> None:
    paths = resolve_app_paths(env={DATA_DIR_ENV: "   "})

    assert paths.root == default_root()


def test_default_root_posix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert default_root() == tmp_path / APP_DIR_POSIX


def test_default_root_macos(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert default_root() == tmp_path / "Library" / "Application Support" / APP_NAME


def test_default_root_windows_with_appdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert default_root() == appdata / APP_NAME


def test_default_root_windows_without_appdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert default_root() == tmp_path / "AppData" / "Roaming" / APP_NAME


def test_ensure_runtime_dirs_is_idempotent_and_localized(tmp_path: Path) -> None:
    paths = AppPaths(root=tmp_path / "weaver-data")
    paths.ensure_runtime_dirs()
    paths.ensure_runtime_dirs()

    assert paths.root.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.cache_dir.is_dir()
    assert paths.temp_dir.is_dir()
    # No leakage outside root.
    leaked = [child for child in tmp_path.iterdir() if child != paths.root]
    assert leaked == []


def test_appname_constants_are_stable() -> None:
    # Renaming these is a user-visible contract break — guarded by an explicit assert.
    assert APP_NAME == "Weaver"
    assert APP_DIR_POSIX == ".weaver"
    assert DATA_DIR_ENV == "WEAVER_DATA_DIR"
