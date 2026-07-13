"""Workspace connection registry (ADR 018 D2).

A **connection** is *where + how* to reach an LLM endpoint: a name, an endpoint
URL, the env-var *name* that holds its key, and an optional default model. It is a
workspace-level, non-secret resource stored in ``~/.weaver/connections.toml``
(mode ``0o600``), parallel to ``secrets.toml``. The key **value** never lives
here — only ``api_key_env`` (a name); the value stays in the secret store.

Protocol is implied: ``openai_chat`` is the only real transport (ADR 018 D1), so
the user never picks one. Health and model counts are *derived* (probed on demand),
never stored here.
"""

from __future__ import annotations

import contextlib
import os
import re
import stat
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from weaver.errors import ConfigError

CONNECTIONS_TABLE = "connections"
PATH_ENV_VAR = "WEAVER_CONNECTIONS_PATH"
DEFAULT_PROTOCOL = "openai_chat"
DEFAULT_TIMEOUT_SECONDS = 60.0
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class Connection:
    """A registered endpoint: where + how, never the key value."""

    name: str
    base_url: str
    api_key_env: str
    default_model: str = ""
    protocol: str = DEFAULT_PROTOCOL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    requires_key: bool = True
    headers: dict[str, str] = field(default_factory=dict)


def default_connections_path() -> Path:
    """Return the registry path.

    Honors ``$WEAVER_CONNECTIONS_PATH`` (relocation / test isolation); otherwise
    ``~/.weaver/connections.toml``.
    """

    override = os.environ.get(PATH_ENV_VAR)
    if override and override.strip():
        return Path(override).expanduser()
    return Path.home() / ".weaver" / "connections.toml"


def load_connections(path: Path | None = None) -> dict[str, Connection]:
    """Load all connections, tolerant of a missing/empty/unparseable file.

    Never raises on read so a bad file cannot break startup or the hub render.
    """

    registry_path = path or default_connections_path()
    if not registry_path.is_file():
        return {}
    try:
        text = registry_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.strip():
        return {}
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    table = data.get(CONNECTIONS_TABLE, {})
    if not isinstance(table, dict):
        return {}
    out: dict[str, Connection] = {}
    for name, raw in table.items():
        if isinstance(raw, dict):
            out[str(name)] = _connection_from_toml(str(name), raw)
    return out


def list_connections(path: Path | None = None) -> list[Connection]:
    """Return all registered connections, sorted by name."""

    # Parse the registry once; the previous form parsed connections.toml twice
    # (once to sort, once to index) on every providers/routing render.
    connections = load_connections(path)
    return [connections[name] for name in sorted(connections)]


def get_connection(name: str, *, path: Path | None = None) -> Connection | None:
    """Return one connection by name, or ``None`` when absent."""

    return load_connections(path).get(name)


def register_connection(connection: Connection, *, path: Path | None = None) -> None:
    """Add or replace a connection (upsert). Validates name + endpoint.

    Raises:
        ConfigError: When the name is not a valid slug or ``base_url`` is empty.
    """

    name = connection.name.strip()
    if not _NAME_RE.match(name):
        raise ConfigError(
            f"Invalid connection name `{connection.name}`. "
            "Likely cause: names are lowercase slugs ([a-z0-9] then [a-z0-9_-]). "
            "Next command: use a name like `openrouter` or `local_ollama`."
        )
    if not connection.base_url.strip():
        raise ConfigError(
            "A connection needs an endpoint. "
            "Likely cause: the Endpoint field was left empty. "
            "Next command: enter the endpoint URL, e.g. https://openrouter.ai/api/v1."
        )
    connections = load_connections(path)
    connections[name] = connection
    _write_connections(connections, path or default_connections_path())


def delete_connection(name: str, *, path: Path | None = None) -> bool:
    """Remove a connection. Returns True when one was removed."""

    connections = load_connections(path)
    if name not in connections:
        return False
    del connections[name]
    _write_connections(connections, path or default_connections_path())
    return True


def _connection_from_toml(name: str, raw: dict[str, object]) -> Connection:
    headers_raw = raw.get("headers", {})
    headers = (
        {str(k): str(v) for k, v in headers_raw.items()} if isinstance(headers_raw, dict) else {}
    )
    return Connection(
        name=name,
        base_url=str(raw.get("base_url", "")),
        api_key_env=str(raw.get("api_key_env", "")),
        default_model=str(raw.get("default_model", "")),
        protocol=str(raw.get("protocol", DEFAULT_PROTOCOL)) or DEFAULT_PROTOCOL,
        timeout_seconds=_as_float(raw.get("timeout_seconds"), DEFAULT_TIMEOUT_SECONDS),
        requires_key=bool(raw.get("requires_key", True)),
        headers=headers,
    )


def _as_float(value: object, fallback: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback


def _write_connections(connections: dict[str, Connection], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = []
    for name in sorted(connections):
        blocks.append(_serialize(connections[name]))
    content = "\n".join(blocks) + ("\n" if blocks else "")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temp_path = Path(file.name)
        file.write(content)
    _restrict_permissions(temp_path)
    os.replace(temp_path, path)
    _restrict_permissions(path)


def _serialize(connection: Connection) -> str:
    lines = [f"[{CONNECTIONS_TABLE}.{connection.name}]"]
    lines.append(f'protocol = "{_escape(connection.protocol)}"')
    lines.append(f'base_url = "{_escape(connection.base_url)}"')
    lines.append(f'api_key_env = "{_escape(connection.api_key_env)}"')
    lines.append(f'default_model = "{_escape(connection.default_model)}"')
    lines.append(f"timeout_seconds = {connection.timeout_seconds}")
    lines.append(f"requires_key = {'true' if connection.requires_key else 'false'}")
    if connection.headers:
        pairs = ", ".join(
            f'"{_escape(k)}" = "{_escape(v)}"' for k, v in sorted(connection.headers.items())
        )
        lines.append(f"headers = {{ {pairs} }}")
    return "\n".join(lines) + "\n"


def _restrict_permissions(path: Path) -> None:
    """Best-effort owner-only (``0o600``); no-op where unsupported (Windows)."""

    with contextlib.suppress(OSError):
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
