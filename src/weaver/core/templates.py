"""Project template presets for ``weaver init --from-template``.

Each template provides genre-appropriate defaults for ``[glossary]`` and
``[qa]`` sections.  Templates are frozen at init time — changing a template
does not retroactively update existing projects.
"""

from __future__ import annotations

from typing import Any

from weaver.errors import ConfigError

TEMPLATES: dict[str, dict[str, Any]] = {
    "light-novel": {
        "glossary": {
            "require_review": True,
            "max_terms_per_segment": 30,
        },
        "qa": {
            "minimum_length_ratio": 0.25,
        },
    },
    "web-novel": {
        "glossary": {
            "require_review": False,
            "max_terms_per_segment": 15,
        },
        "qa": {
            "minimum_length_ratio": 0.2,
        },
    },
    "aozora-classic": {
        "glossary": {
            "require_review": True,
            "max_terms_per_segment": 40,
        },
        "qa": {
            "detect_untranslated_japanese": True,
            "minimum_length_ratio": 0.4,
        },
    },
}


def get_template(name: str) -> dict[str, Any]:
    """Return a deep copy of the named template preset.

    Args:
        name: Template name (``light-novel``, ``web-novel``, ``aozora-classic``).

    Returns:
        Dict with ``glossary`` and ``qa`` section overrides.

    Raises:
        ConfigError: When ``name`` is not a known template.
    """

    if name not in TEMPLATES:
        available = ", ".join(sorted(TEMPLATES))
        raise ConfigError(
            f"Unknown template `{name}`. "
            f"Likely cause: template name is misspelled. "
            f"Next command: use one of: {available}."
        )
    template = TEMPLATES[name]
    return {section: dict(values) for section, values in template.items()}


def list_template_names() -> list[str]:
    """Return sorted list of available template names."""

    return sorted(TEMPLATES)
