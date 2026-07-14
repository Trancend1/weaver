"""Unit tests for shared TOML write safety (v0.7.3 M2.1, audit A2+A7)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from weaver.core.toml_write import escape_toml_string, guard_unparseable_toml
from weaver.errors import ConfigError


@pytest.mark.parametrize(
    "value",
    [
        'plain "quoted" and \\backslash\\',
        "newline\nand\rreturn\tand tab",
        "bell\x07null\x00escape\x1bdel\x7f",
        "mixed \x01\x02\x03 controls",
        "",
    ],
)
def test_escape_round_trips_through_tomllib(value: str) -> None:
    doc = f'key = "{escape_toml_string(value)}"\n'
    assert tomllib.loads(doc)["key"] == value


def test_guard_passes_missing_empty_and_valid_files(tmp_path: Path) -> None:
    guard_unparseable_toml(tmp_path / "absent.toml", label="Test file")

    empty = tmp_path / "empty.toml"
    empty.write_text("   \n", encoding="utf-8")
    guard_unparseable_toml(empty, label="Test file")

    valid = tmp_path / "valid.toml"
    valid.write_text('[keys]\nA = "1"\n', encoding="utf-8")
    guard_unparseable_toml(valid, label="Test file")
    assert valid.is_file()  # untouched
    assert list(tmp_path.glob("*.corrupt-*")) == []


def test_guard_moves_corrupt_file_aside_and_names_backup(tmp_path: Path) -> None:
    corrupt = tmp_path / "broken.toml"
    corrupt.write_text('[keys]\nA = "unterminated\n', encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        guard_unparseable_toml(corrupt, label="Test file")

    backups = list(tmp_path.glob("broken.toml.corrupt-*"))
    assert len(backups) == 1
    assert str(backups[0]) in str(exc_info.value)
    assert backups[0].read_text(encoding="utf-8") == '[keys]\nA = "unterminated\n'
    assert not corrupt.exists()  # moved aside, retry starts fresh
