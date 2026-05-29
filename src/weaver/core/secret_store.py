"""Local secret store for provider API keys (ADR ``0020``).

Keys live **only** here — ``~/.weaver/secrets.toml`` (mode ``0o600``, outside the
repo) — never in ``project.toml`` / ``~/.weaver/config.toml`` and never in logs or
rendered output (CLAUDE.md §4.2, ADR ``0017``).

The store maps an **env-var name → secret value** under a ``[keys]`` table. At
startup :func:`apply_secrets_to_env` loads it and sets any name not already in
``os.environ`` — a real shell env var always wins. Providers keep reading
``os.environ`` and never learn the store exists.
"""

from __future__ import annotations

import contextlib
import os
import re
import stat
import tempfile
import tomllib
from pathlib import Path

from weaver.errors import ConfigError

KEYS_TABLE = "keys"
PATH_ENV_VAR = "WEAVER_SECRETS_PATH"
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def default_secrets_path() -> Path:
    """Return the secret-store path.

    Honors ``$WEAVER_SECRETS_PATH`` (for relocation / test isolation); otherwise
    ``~/.weaver/secrets.toml``.
    """

    override = os.environ.get(PATH_ENV_VAR)
    if override and override.strip():
        return Path(override).expanduser()
    return Path.home() / ".weaver" / "secrets.toml"


def load_secrets(path: Path | None = None) -> dict[str, str]:
    """Load the ``[keys]`` table, tolerant of a missing or empty file.

    Returns:
        Mapping of env-var name → value. Empty when the file is absent, empty, or
        unparseable (never raises on read so startup cannot be broken by a bad
        file).
    """

    secrets_path = path or default_secrets_path()
    if not secrets_path.is_file():
        return {}
    try:
        text = secrets_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.strip():
        return {}
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    table = data.get(KEYS_TABLE, {})
    if not isinstance(table, dict):
        return {}
    return {str(name): str(value) for name, value in table.items()}


def set_secret(env_var: str, value: str, *, path: Path | None = None) -> None:
    """Store ``value`` under env-var name ``env_var`` (atomic, ``0o600``).

    Raises:
        ConfigError: When ``env_var`` is not a valid environment-variable name or
            ``value`` is empty.
    """

    name = env_var.strip()
    if not _ENV_NAME_RE.match(name):
        raise ConfigError(
            f"Invalid environment-variable name `{env_var}`. "
            "Likely cause: names must match [A-Za-z_][A-Za-z0-9_]*. "
            "Next command: use a name like DEEPSEEK_API_KEY."
        )
    if not value:
        raise ConfigError(
            "Refusing to store an empty secret. "
            "Likely cause: no value was supplied. "
            "Next command: pass the API key value."
        )
    secrets = load_secrets(path)
    secrets[name] = value
    _write_secrets(secrets, path or default_secrets_path())


def delete_secret(env_var: str, *, path: Path | None = None) -> bool:
    """Remove ``env_var`` from the store. Returns True when a key was removed."""

    secrets = load_secrets(path)
    if env_var not in secrets:
        return False
    del secrets[env_var]
    _write_secrets(secrets, path or default_secrets_path())
    return True


def list_secret_names(path: Path | None = None) -> list[str]:
    """Return stored env-var **names** only (never values), sorted."""

    return sorted(load_secrets(path))


def apply_secrets_to_env(path: Path | None = None) -> None:
    """Inject stored secrets into ``os.environ`` without overriding real env vars.

    A name already present in the process environment is left untouched (shell
    env wins). Safe to call once at CLI/web startup.
    """

    for name, value in load_secrets(path).items():
        if name not in os.environ:
            os.environ[name] = value


def _write_secrets(secrets: dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"[{KEYS_TABLE}]"]
    for name in sorted(secrets):
        lines.append(f'{name} = "{_escape(secrets[name])}"')
    content = "\n".join(lines) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as file:
        temp_path = Path(file.name)
        file.write(content)
    _restrict_permissions(temp_path)
    os.replace(temp_path, path)
    _restrict_permissions(path)


def _restrict_permissions(path: Path) -> None:
    """Best-effort owner-only (``0o600``) permissions; no-op where unsupported."""

    # Windows / exotic filesystems cannot enforce POSIX modes — best-effort.
    with contextlib.suppress(OSError):
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
