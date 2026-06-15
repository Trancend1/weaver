"""AI task taxonomy (ADR 018 D7/D8).

The first time Weaver distinguishes *what kind* of AI call is happening. A project
may route each task to a different connection + model. ``translate`` is the
primary workflow; ``glossary_suggest`` and ``candidate`` are existing on-demand
consumers that may later opt into per-task routing.
"""

from __future__ import annotations

from enum import Enum


class TaskType(Enum):
    """A routable AI task. Use ``.value`` for the TOML/wire string."""

    translate = "translate"
    glossary_suggest = "glossary_suggest"
    candidate = "candidate"
