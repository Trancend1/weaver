"""Unit tests for services/epubcheck.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from weaver.errors import ConfigError
from weaver.services.epubcheck import find_epubcheck_jar, run_epubcheck

FIXTURE_EPUB = Path(__file__).parents[3] / "tests" / "fixtures" / "aozora_sample.epub"


def test_jar_not_found_returns_unavailable(tmp_path: Path) -> None:
    with patch("weaver.services.epubcheck.find_epubcheck_jar", return_value=None):
        result = run_epubcheck(FIXTURE_EPUB)

    assert result.epubcheck_available is False
    assert result.passed is True
    assert result.errors == ()
    assert result.jar_path is None


def test_epubcheck_jar_env_var_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_jar = tmp_path / "epubcheck.jar"
    fake_jar.touch()
    monkeypatch.setenv("EPUBCHECK_JAR", str(fake_jar))

    found = find_epubcheck_jar()

    assert found == fake_jar


def test_java_not_on_path_raises_config_error(tmp_path: Path) -> None:
    fake_jar = tmp_path / "epubcheck.jar"
    fake_jar.touch()

    with (
        patch("weaver.services.epubcheck.find_epubcheck_jar", return_value=fake_jar),
        patch("subprocess.run", side_effect=FileNotFoundError("java not found")),
        pytest.raises(ConfigError, match="Java"),
    ):
        run_epubcheck(FIXTURE_EPUB)


def test_error_lines_parsed_into_errors_tuple(tmp_path: Path) -> None:
    fake_jar = tmp_path / "epubcheck.jar"
    fake_jar.touch()
    fake_proc = MagicMock()
    fake_proc.returncode = 1
    fake_proc.stdout = "ERROR: bad content type\nINFO: processed\n"
    fake_proc.stderr = "WARNING: deprecated feature\n"

    with (
        patch("weaver.services.epubcheck.find_epubcheck_jar", return_value=fake_jar),
        patch("subprocess.run", return_value=fake_proc),
    ):
        result = run_epubcheck(FIXTURE_EPUB)

    assert result.epubcheck_available is True
    assert result.passed is False
    assert any("ERROR" in e.upper() for e in result.errors)
    assert any("WARNING" in w.upper() for w in result.warnings)
