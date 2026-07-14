"""Shared TOML write safety: string escaping + corrupt-file write guard.

Two concerns every hand-serialized TOML writer in Weaver shares:

* :func:`escape_toml_string` — escape a value for a TOML *basic* (double-quoted)
  string. TOML forbids unescaped control characters (U+0000–U+001F, U+007F);
  the previous per-module ``_escape`` copies handled only ``\\`` and ``"``, so a
  value containing a newline produced a file the tolerant readers then skipped
  entirely — silent data loss on the next write.
* :func:`guard_unparseable_toml` — refuse to overwrite a present-but-unparseable
  file. The tolerant readers (``load_connections``/``load_secrets``) return ``{}``
  on a corrupt file so startup never breaks; without this guard a subsequent
  write would rebuild the file from that empty view and destroy whatever the
  user had. The guard moves the corrupt file aside to a timestamped backup and
  raises, so the failure is visible and the data recoverable.
"""

from __future__ import annotations

import os
import time
import tomllib
from pathlib import Path

from weaver.errors import ConfigError

# TOML-defined short escapes; every other control char uses \\uXXXX.
_SHORT_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def escape_toml_string(value: str) -> str:
    """Escape ``value`` for embedding in a TOML basic (double-quoted) string."""

    out: list[str] = []
    for char in value:
        escaped = _SHORT_ESCAPES.get(char)
        if escaped is not None:
            out.append(escaped)
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    return "".join(out)


def guard_unparseable_toml(path: Path, *, label: str) -> None:
    """Refuse to overwrite a present-but-unparseable TOML file.

    Moves the corrupt file aside to ``<name>.corrupt-<timestamp>`` and raises;
    a retry of the same write then starts from a fresh file. Missing, empty,
    or valid files pass through untouched.

    Raises:
        ConfigError: When ``path`` exists but is not valid TOML. The message
            names the backup path so the user can recover old entries.
    """

    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    if not text.strip():
        return
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        backup = _backup_path(path)
        os.replace(path, backup)
        raise ConfigError(
            f"{label} at {path} is not valid TOML; refusing to overwrite it. "
            "Likely cause: a manual edit broke the file. "
            f"The original was preserved at {backup}. "
            "Next command: re-run this save to write a fresh file, then recover "
            "old entries from the backup by hand if needed."
        ) from None


def _backup_path(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.corrupt-{stamp}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.corrupt-{stamp}-{counter}")
        counter += 1
    return candidate
