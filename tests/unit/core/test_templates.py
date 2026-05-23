"""Tests for project template presets."""

from __future__ import annotations

import pytest

from weaver.core.templates import get_template, list_template_names
from weaver.errors import ConfigError


def test_known_template_loads() -> None:
    template = get_template("light-novel")
    assert template["glossary"]["max_terms_per_segment"] == 30
    assert template["glossary"]["require_review"] is True
    assert template["qa"]["minimum_length_ratio"] == 0.25


def test_unknown_template_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="Unknown template"):
        get_template("nonexistent")


def test_list_template_names_returns_sorted() -> None:
    names = list_template_names()
    assert names == ["aozora-classic", "light-novel", "web-novel"]


def test_get_template_returns_copy() -> None:
    a = get_template("web-novel")
    b = get_template("web-novel")
    a["glossary"]["max_terms_per_segment"] = 999
    assert b["glossary"]["max_terms_per_segment"] == 15
