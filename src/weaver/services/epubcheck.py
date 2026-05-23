"""EPUBCheck integration — optional Java-based EPUB validator."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from weaver.errors import ConfigError

_EPUBCHECK_SEARCH_PATHS = [
    Path.home() / ".local" / "share" / "epubcheck" / "epubcheck.jar",
    Path("/usr/local/share/epubcheck/epubcheck.jar"),
]

_WIN_LOCALAPPDATA = os.environ.get("LOCALAPPDATA", "")
if _WIN_LOCALAPPDATA:
    _EPUBCHECK_SEARCH_PATHS.insert(0, Path(_WIN_LOCALAPPDATA) / "epubcheck" / "epubcheck.jar")


@dataclass(frozen=True)
class EpubCheckResult:
    """Result of running EPUBCheck on an EPUB file."""

    epub_path: Path
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    epubcheck_available: bool
    jar_path: Path | None


def find_epubcheck_jar() -> Path | None:
    """Return the first EPUBCheck jar found, or None."""
    env_jar = os.environ.get("EPUBCHECK_JAR")
    if env_jar:
        p = Path(env_jar)
        if p.exists():
            return p
    for candidate in _EPUBCHECK_SEARCH_PATHS:
        if candidate.exists():
            return candidate
    return None


def run_epubcheck(epub_path: Path) -> EpubCheckResult:
    """Run EPUBCheck on epub_path and return a structured result.

    If the jar is not found, returns a result with epubcheck_available=False
    and passed=True (graceful degradation).

    Raises:
        ConfigError: When Java is not on PATH.
    """
    jar = find_epubcheck_jar()
    if jar is None:
        return EpubCheckResult(
            epub_path=epub_path,
            passed=True,
            errors=(),
            warnings=(),
            epubcheck_available=False,
            jar_path=None,
        )

    try:
        proc = subprocess.run(
            ["java", "-jar", str(jar), str(epub_path)],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ConfigError(
            "EPUBCheck requires Java 8+. "
            "Likely cause: java is not on PATH. "
            "Next command: install Java from https://adoptium.net and retry."
        ) from exc

    combined = proc.stdout + proc.stderr
    errors = tuple(line.strip() for line in combined.splitlines() if "ERROR" in line.upper())
    warnings = tuple(line.strip() for line in combined.splitlines() if "WARNING" in line.upper())

    return EpubCheckResult(
        epub_path=epub_path,
        passed=proc.returncode == 0,
        errors=errors,
        warnings=warnings,
        epubcheck_available=True,
        jar_path=jar,
    )
