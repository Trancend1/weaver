"""App-data path resolver (Sprint G2 — Tauri-sidecar-ready runtime foundation).

One OS-aware root for every Weaver-owned user-machine directory: config,
secrets, cache, logs, exports, temp. The root is:

- ``~/.weaver/`` on POSIX (unchanged from pre-G behavior).
- ``%APPDATA%/Weaver/`` on Windows (only when ``APPDATA`` is set).
- ``~/Library/Application Support/Weaver/`` on macOS.
- ``$WEAVER_DATA_DIR`` overrides the default on any platform.

Books-dir (the per-user "where projects live" directory) is **not** here — it
stays in the project-paths layer (``services/project_paths.py``,
``services/project_discovery.py``). App-data is user-machine state; books-dir
is user-content state.

The ``~/.weaver/secrets.toml`` location is preserved verbatim under the default
root and is still resolved by ``weaver.core.secret_store.default_secrets_path``
when ``WEAVER_SECRETS_PATH`` is not set; that contract is older than G2 and
intentionally outlives the abstraction.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DATA_DIR_ENV = "WEAVER_DATA_DIR"
BOOKS_DIR_ENV = "WEAVER_BOOKS_DIR"
APP_NAME = "Weaver"
APP_DIR_POSIX = ".weaver"


@dataclass(frozen=True)
class AppPaths:
    """OS-aware bundle of Weaver-owned app-data directories.

    All directories are anchored at ``root``. Resolution is pure — no I/O
    happens until :meth:`ensure_runtime_dirs` is called by the runtime
    bootstrap (CLI ``serve`` / API factory).
    """

    root: Path

    @property
    def config_dir(self) -> Path:
        return self.root

    @property
    def workspace_dir(self) -> Path:
        return self.root / "workspace"

    @property
    def database_dir(self) -> Path:
        return self.root / "db"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def export_dir(self) -> Path:
        return self.root / "exports"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def temp_dir(self) -> Path:
        return self.root / "tmp"

    @property
    def secrets_path(self) -> Path:
        """Secret store path under the default root.

        Note: ``weaver.core.secret_store.default_secrets_path`` is the
        authoritative resolver (it honors ``WEAVER_SECRETS_PATH``). This
        property is informational — used by ``/runtime/status`` and by G6
        log lines to report where secrets *would* live under this root.
        """
        return self.root / "secrets.toml"

    def ensure_runtime_dirs(self) -> None:
        """Create the runtime-required directories. Idempotent.

        Only directories the runtime writes to are created here. ``root`` and
        ``config_dir`` are the same; the rest are content-owning subdirs.
        """
        for path in (self.root, self.logs_dir, self.cache_dir, self.temp_dir):
            path.mkdir(parents=True, exist_ok=True)


def default_root() -> Path:
    """Compute the OS-default app-data root (no env override).

    POSIX-non-mac → ``~/.weaver``. macOS → ``~/Library/Application Support/Weaver``.
    Windows → ``%APPDATA%/Weaver`` (or ``~/AppData/Roaming/Weaver`` when
    ``APPDATA`` is missing).
    """
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata and appdata.strip():
            return Path(appdata) / APP_NAME
        return home / "AppData" / "Roaming" / APP_NAME
    return home / APP_DIR_POSIX


def resolve_app_paths(*, env: Mapping[str, str] | None = None) -> AppPaths:
    """Resolve :class:`AppPaths` honoring ``WEAVER_DATA_DIR`` if set.

    Args:
        env: Optional environment mapping (defaults to ``os.environ``). Tests
            pass a custom mapping; runtime callers pass nothing.
    """
    source: Mapping[str, str] = os.environ if env is None else env
    override = source.get(DATA_DIR_ENV)
    if override and override.strip():
        return AppPaths(root=Path(override).expanduser().resolve())
    return AppPaths(root=default_root())
