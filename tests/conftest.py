"""Session-wide test isolation.

Sets ``WEAVER_ENV=test`` so the FastAPI factory skips installing rotating
file handlers (G6) — tests should not write to the user's real app-data dir.
Individual desktop-security tests opt in by overriding ``WEAVER_ENV`` via
``monkeypatch.setenv``.
"""

from __future__ import annotations

import os


def pytest_configure(config):  # type: ignore[no-untyped-def]
    os.environ.setdefault("WEAVER_ENV", "test")
