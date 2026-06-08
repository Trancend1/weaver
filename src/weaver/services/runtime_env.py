"""Runtime environment dispatch (Sprint G5).

Single source of truth for ``WEAVER_ENV ∈ {dev, desktop, test}``. The mode
flips three runtime behaviors:

- bind safety (``cli/main.py`` refuses ``host != 127.0.0.1`` in desktop);
- ``/docs`` + ``/redoc`` exposure (off in desktop unless ``WEAVER_DOCS=true``);
- CORS middleware (same-origin only in desktop; off in dev).

The ``X-Weaver-Session`` token is a separate orthogonal control: it activates
whenever ``WEAVER_SESSION_TOKEN`` is set, regardless of mode. Desktop mode is
expected to set it; dev mode usually does not.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal

ENV_VAR = "WEAVER_ENV"
DOCS_VAR = "WEAVER_DOCS"
SESSION_TOKEN_VAR = "WEAVER_SESSION_TOKEN"

EnvMode = Literal["dev", "desktop", "test"]
_VALID_ENVS: tuple[EnvMode, ...] = ("dev", "desktop", "test")
DEFAULT_ENV: EnvMode = "dev"


def current_env(env: Mapping[str, str] | None = None) -> EnvMode:
    """Return the current runtime mode. Unknown values fall back to ``dev``."""
    source = os.environ if env is None else env
    raw = source.get(ENV_VAR, "").strip().lower()
    if raw in _VALID_ENVS:
        return raw  # type: ignore[return-value]
    return DEFAULT_ENV


def docs_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Whether ``/docs`` and ``/redoc`` should be served.

    Default behaviour:
    - ``dev``  → docs **on** (matches pre-G default).
    - ``test`` → docs **on**  (TestClient never exposes them publicly).
    - ``desktop`` → docs **off** unless ``WEAVER_DOCS=true`` overrides.
    """
    source = os.environ if env is None else env
    override = source.get(DOCS_VAR, "").strip().lower()
    if override in {"true", "1", "yes"}:
        return True
    if override in {"false", "0", "no"}:
        return False
    return current_env(source) != "desktop"


def session_token(env: Mapping[str, str] | None = None) -> str | None:
    """Return the session token when set; otherwise ``None``."""
    source = os.environ if env is None else env
    value = source.get(SESSION_TOKEN_VAR, "").strip()
    return value or None
