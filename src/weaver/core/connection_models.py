"""Workspace model-discovery cache (ADR 018 D3/S3).

Discovery is on-demand (Test / Load models) and **never on render** (Gate B1).
To let the cockpit show a connection's models *without* re-probing on every page
load, the last successful ``/v1/models`` snapshot is cached here.

The cache is **workspace-level** — connections are workspace resources, so their
model lists are too. It lives in ``~/.weaver/connection_models.json`` (mode
``0o600``), parallel to ``connections.toml``. This intentionally deviates from the
``connection_models`` SQLite table sketched in ADR 018 §6.1: a per-project table
would cache the same workspace connection separately in every project and needs a
schema migration. A single workspace JSON file is the lean fit (D9) and keeps
derived data out of ``connections.toml`` (D2).
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PATH_ENV_VAR = "WEAVER_CONNECTION_MODELS_PATH"
DEFAULT_TTL_SECONDS = 21_600  # 6 hours; only governs the "(stale)" hint, never a probe


@dataclass(frozen=True)
class CachedModels:
    """The last discovered model snapshot for one connection."""

    models: tuple[str, ...]
    fetched_at: str  # ISO-8601 UTC

    def is_stale(
        self, *, ttl_seconds: int = DEFAULT_TTL_SECONDS, now: datetime | None = None
    ) -> bool:
        try:
            fetched = datetime.fromisoformat(self.fetched_at)
        except ValueError:
            return True
        current = now or datetime.now(UTC)
        return (current - fetched).total_seconds() > ttl_seconds


def default_models_path() -> Path:
    """Return the cache path. Honors ``$WEAVER_CONNECTION_MODELS_PATH``."""

    override = os.environ.get(PATH_ENV_VAR)
    if override and override.strip():
        return Path(override).expanduser()
    return Path.home() / ".weaver" / "connection_models.json"


def load_all(path: Path | None = None) -> dict[str, CachedModels]:
    """Load every cached snapshot, tolerant of a missing/unparseable file."""

    cache_path = path or default_models_path()
    if not cache_path.is_file():
        return {}
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, CachedModels] = {}
    for name, entry in raw.items():
        if isinstance(entry, dict) and isinstance(entry.get("models"), list):
            out[str(name)] = CachedModels(
                models=tuple(str(m) for m in entry["models"]),
                fetched_at=str(entry.get("fetched_at", "")),
            )
    return out


def get_cached(connection_name: str, *, path: Path | None = None) -> CachedModels | None:
    """Return one connection's cached snapshot, or None when absent."""

    return load_all(path).get(connection_name)


def save_cached(
    connection_name: str,
    models: Iterable[str],
    *,
    path: Path | None = None,
    now: datetime | None = None,
) -> None:
    """Replace one connection's snapshot (stamped with the current UTC time)."""

    cache = load_all(path)
    fetched_at = (now or datetime.now(UTC)).isoformat()
    cache[connection_name] = CachedModels(
        models=tuple(str(m) for m in models), fetched_at=fetched_at
    )
    _write(cache, path or default_models_path())


def clear_cached(connection_name: str, *, path: Path | None = None) -> bool:
    """Drop one connection's snapshot. Returns True when one was removed."""

    cache = load_all(path)
    if connection_name not in cache:
        return False
    del cache[connection_name]
    _write(cache, path or default_models_path())
    return True


def _write(cache: dict[str, CachedModels], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        name: {"models": list(entry.models), "fetched_at": entry.fetched_at}
        for name, entry in sorted(cache.items())
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temp_path = Path(file.name)
        file.write(content)
    _restrict(temp_path)
    os.replace(temp_path, path)
    _restrict(path)


def _restrict(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
