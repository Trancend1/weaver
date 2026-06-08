"""Structured logging baseline (Sprint G6).

Five JSON-lines files in :class:`AppPaths.logs_dir`, rotated at 10 MiB × 5:

```text
runtime.log   FastAPI lifespan, startup/shutdown, env mode
backend.log   request errors, unhandled exceptions
job.log       JobRegistry status transitions (Sprint I will extend)
export.log    export attempts and outcomes
provider.log  provider invocations — never the prompt, never the key
```

The module exposes one entry point (:func:`install_logging`) that the FastAPI
factory calls once. Loggers are vanilla stdlib `logging.Logger` with a
`JsonLineFormatter`; callers use `log.info(event, extra={"data": {...}})` and
the formatter renders `{ts, level, event, ...data}` per line.

Provider safety: :func:`scrub_provider_record` removes any key whose lowercased
name contains ``key``, ``token``, ``password``, ``secret``, or ``authorization``.
Provider call-sites should funnel through :func:`log_provider_event` rather than
raw `logger.info` so this scrub always runs.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from weaver.services.app_paths import AppPaths

LOG_FILES: tuple[str, ...] = (
    "runtime.log",
    "backend.log",
    "job.log",
    "export.log",
    "provider.log",
)
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5

_SECRET_TOKENS = ("key", "token", "password", "secret", "authorization", "credential")
_INSTALLED_KEY = "_weaver_logging_installed"


class JsonLineFormatter(logging.Formatter):
    """Render a record as a single JSON line.

    Standard fields are ``ts``, ``level``, ``logger``, ``event``. Anything in
    ``record.__dict__["data"]`` (set via ``extra={"data": {...}}``) is merged
    into the top-level object.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        data = getattr(record, "data", None)
        if isinstance(data, dict):
            for key, value in data.items():
                if key not in payload:
                    payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def install_logging(app_paths: AppPaths) -> None:
    """Install the five rotating JSON file handlers. Idempotent per process."""
    app_paths.ensure_runtime_dirs()

    if getattr(install_logging, _INSTALLED_KEY, False):
        return

    formatter = JsonLineFormatter()
    for filename in LOG_FILES:
        logger_name = f"weaver.{filename.split('.')[0]}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        # Remove any pre-installed handlers on this logger to keep the contract
        # exact (one rotating handler per named log).
        logger.handlers = [h for h in logger.handlers if not _is_managed(h)]
        handler = RotatingFileHandler(
            app_paths.logs_dir / filename,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(formatter)
        handler._weaver_managed = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
        logger.propagate = False

    setattr(install_logging, _INSTALLED_KEY, True)


def reset_logging() -> None:
    """Tear down installed handlers (test helper).

    Closes file handles and removes managed handlers so a subsequent
    :func:`install_logging` call rebinds to a fresh ``logs_dir``.
    """
    for filename in LOG_FILES:
        logger = logging.getLogger(f"weaver.{filename.split('.')[0]}")
        kept: list[logging.Handler] = []
        for handler in logger.handlers:
            if _is_managed(handler):
                handler.close()
            else:
                kept.append(handler)
        logger.handlers = kept
    setattr(install_logging, _INSTALLED_KEY, False)


def _is_managed(handler: logging.Handler) -> bool:
    return getattr(handler, "_weaver_managed", False)


def scrub_provider_record(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``data`` with secret-shaped keys redacted.

    A key is treated as secret-shaped when its lowercased name contains any of
    the tokens in :data:`_SECRET_TOKENS`. The value is replaced with the
    literal string ``"<redacted>"`` so log readers still see the field exists.
    """
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        lowered = key.lower()
        if any(token in lowered for token in _SECRET_TOKENS):
            cleaned[key] = "<redacted>"
        else:
            cleaned[key] = value
    return cleaned


def log_runtime_event(event: str, **fields: Any) -> None:
    logging.getLogger("weaver.runtime").info(event, extra={"data": dict(fields)})


def log_provider_event(event: str, **fields: Any) -> None:
    """Emit one provider event with secret-shaped fields scrubbed."""
    logging.getLogger("weaver.provider").info(
        event, extra={"data": scrub_provider_record(dict(fields))}
    )


def log_job_event(event: str, **fields: Any) -> None:
    logging.getLogger("weaver.job").info(event, extra={"data": dict(fields)})


def log_export_event(event: str, **fields: Any) -> None:
    logging.getLogger("weaver.export").info(event, extra={"data": dict(fields)})


def log_backend_event(
    event: str, *, level: int = logging.INFO, exc_info: bool = False, **fields: Any
) -> None:
    logging.getLogger("weaver.backend").log(
        level, event, exc_info=exc_info, extra={"data": dict(fields)}
    )


def read_log_file(app_paths: AppPaths, filename: str) -> list[dict[str, Any]]:
    """Read one log file as parsed JSON objects (test helper)."""
    path: Path = app_paths.logs_dir / filename
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
