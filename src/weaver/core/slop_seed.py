"""Default banned-phrase seed for the anti-slop check (ADR 019 E3).

A small, high-confidence list of phrasings that are strong tells of machine-
translation slop in JP->EN light-novel work — over-literal calques that almost
never read as natural published prose. Kept deliberately tiny to avoid false
positives, and a **soft** trigger: a hit asks the model to reconsider the phrasing,
never a hard failure (some may be legitimate in context).

The seed applies **only** when a project declares ``[translation_profile]``; it is
fully overridable there (``banned_phrases = []`` disables it; a custom array
replaces it). See :func:`weaver.services.translation.build_translation_profile`.
"""

from __future__ import annotations

# Substring-matched case-insensitively against the translation.
DEFAULT_BANNED_PHRASES: tuple[str, ...] = (
    "it can't be helped",
    "as expected of",
    "to think that",
    "no choice but to",
    "a certain degree of",
)
