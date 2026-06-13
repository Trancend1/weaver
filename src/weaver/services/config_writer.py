"""Atomic writer for provider/model config (ADR ``0018``).

Single writer for the ``[provider]`` table of a ``project.toml`` (project scope)
and the ``[defaults]`` table of ``~/.weaver/config.toml`` (global scope), used by
both the web cockpit and the ``weaver new`` wizard fix.

Invariants (CLAUDE.md §4.2, ADR ``0017``/``0020``):

- **API keys are never written here.** Only ``type`` / ``model`` / ``base_url`` /
  ``api_key_env`` (project) or ``default_provider`` / ``default_model`` (global).
  The key *value* lives only in the secret store (``core/secret_store.py``);
  ``api_key_env`` records the *name* of the env var that holds it.
- **Atomic writes** via ``tempfile`` + ``os.replace``. No partial writes.
- **Unrelated keys preserved.** A line-based section edit keeps comments and
  every key the call does not touch (exceeds ADR ``0018``'s "comments may be
  lost" allowance — no data key is dropped).
- **Provider types are registry-driven** (ADR ``0020``) — no hardcoded enum.
"""

from __future__ import annotations

import os
import re
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from weaver.core.global_config import default_global_config_path
from weaver.errors import ConfigError
from weaver.providers.registry import (
    PROTOCOL_OPENAI_CHAT,
    known_protocols,
    known_provider_types,
    normalize_provider_config,
)

_PROTOCOL_REQUIRED_FIELDS = {
    PROTOCOL_OPENAI_CHAT: ("base_url", "api_key_env", "model"),
}


def set_provider(
    target: Path,
    *,
    provider_type: str | None = None,
    protocol: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
) -> None:
    """Write provider/model config to ``target`` (project or global scope).

    Scope is inferred from the path: when ``target`` resolves to
    ``~/.weaver/config.toml`` it writes the global ``[defaults]`` table
    (``provider_type`` → ``default_provider``, ``model`` → ``default_model``;
    ``base_url`` / ``api_key_env`` are ignored — not global concepts). Otherwise
    it writes the ``[provider]`` table of the given ``project.toml``.

    Args:
        target: A ``project.toml`` path (project scope) or the global config path.
        provider_type: New provider type (validated against the live registry),
            or None to leave unchanged.
        model: New model id, or None to leave unchanged.
        base_url: New base URL (project scope only), or None to leave unchanged.
        api_key_env: Name of the env var / secret holding the key (project scope
            only), or None to leave unchanged. The key value is never written.

    Raises:
        ConfigError: When ``provider_type`` is not a registered provider, when the
            project ``target`` does not exist, or when no field is supplied.
    """

    if (
        provider_type is None
        and protocol is None
        and model is None
        and base_url is None
        and api_key_env is None
    ):
        raise ConfigError(
            "No provider field supplied. "
            "Likely cause: set_provider called with all fields None. "
            "Next command: pass provider_type, protocol, model, base_url, and/or api_key_env."
        )

    is_global = target.resolve() == default_global_config_path().resolve()
    if is_global:
        section = "defaults"
        updates = _drop_none(default_provider=provider_type, default_model=model)
    else:
        if not target.is_file():
            raise ConfigError(
                f"Project config not found: {target}. "
                "Likely cause: project not initialized or wrong path. "
                "Next command: run `weaver init <input.epub>`."
            )
        section = "provider"
        updates = _drop_none(
            type=provider_type,
            protocol=protocol,
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
        )

    if not updates:
        return

    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    _validate_resulting_provider_config(
        existing,
        section=section,
        updates=updates,
        target=target,
    )
    new_text = _update_section(existing, section, updates)
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, new_text)


def _drop_none(**fields: str | None) -> dict[str, str]:
    return {key: value for key, value in fields.items() if value is not None}


def _validate_resulting_provider_config(
    text: str,
    *,
    section: str,
    updates: Mapping[str, str],
    target: Path,
) -> None:
    parsed = _parse_toml(text, target)
    existing_section = parsed.get(section, {})
    if not isinstance(existing_section, dict):
        raise ConfigError(
            f"Config section [{section}] in {target} is not a TOML table. "
            "Likely cause: provider config was hand-edited into an unsupported shape. "
            "Next command: restore the section as a TOML table, then save again."
        )
    resulting = {**existing_section, **updates}
    if section == "defaults":
        provider_type = _clean(resulting.get("default_provider"))
        if provider_type is None:
            return
        _validate_provider_shape({"type": provider_type, "model": resulting.get("default_model")})
        return
    _validate_provider_shape(resulting)


def _parse_toml(text: str, target: Path) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f"Could not parse {target}: {exc} (expected: valid TOML). "
            "Likely cause: provider config was hand-edited with invalid syntax. "
            "Next command: fix the TOML syntax, then save again."
        ) from exc


def _validate_provider_shape(config: Mapping[str, Any]) -> None:
    normalized = normalize_provider_config(config)
    protocol = _clean(normalized.get("protocol"))
    provider_type = _clean(normalized.get("type"))
    if protocol is not None:
        if protocol not in known_protocols():
            known = ", ".join(known_protocols())
            raise ConfigError(
                f"Unknown provider protocol `{protocol}`. "
                f"Likely cause: typo in provider config. Known protocols: {known}. "
                "Next command: set a supported provider protocol."
            )
        _require_protocol_fields(normalized, protocol)
        return
    if provider_type == "custom":
        _require_protocol_fields(normalized, PROTOCOL_OPENAI_CHAT)
        return
    if provider_type in known_provider_types():
        return
    raise ConfigError(
        "Provider configuration is incomplete. "
        "Likely cause: provider type has no registered adapter and no supported "
        "protocol with required endpoint/model/key fields. "
        "Next command: use a legacy alias (deepseek, gemini, ollama, fake), or "
        "set protocol plus the fields required by that protocol."
    )


def _require_protocol_fields(config: Mapping[str, Any], protocol: str) -> None:
    missing = [
        field
        for field in _PROTOCOL_REQUIRED_FIELDS.get(protocol, ())
        if not _clean(config.get(field))
    ]
    if missing:
        fields = ", ".join(f"`{field}`" for field in missing)
        raise ConfigError(
            "Provider configuration is incomplete. "
            f"Likely cause: protocol `{protocol}` requires {fields}. "
            "Next command: fill the required provider fields before saving."
        )


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _update_section(text: str, section: str, updates: dict[str, str]) -> str:
    """Return ``text`` with ``updates`` applied inside ``[section]``.

    Existing keys are replaced in place (preserving comments and order); missing
    keys are inserted just after the section header; a missing section is
    appended at EOF.
    """

    lines = text.splitlines()
    header = f"[{section}]"
    header_index = _find_header(lines, header)

    if header_index is None:
        return _append_section(text, header, updates)

    section_end = _section_end(lines, header_index)
    remaining = dict(updates)
    for index in range(header_index + 1, section_end):
        key = _line_key(lines[index])
        if key is not None and key in remaining:
            lines[index] = _format_key(key, remaining.pop(key))

    if remaining:
        insertion = [_format_key(key, value) for key, value in remaining.items()]
        lines[header_index + 1 : header_index + 1] = insertion

    trailing_newline = "\n" if text.endswith("\n") or not text else ""
    return "\n".join(lines) + trailing_newline


def _find_header(lines: list[str], header: str) -> int | None:
    for index, line in enumerate(lines):
        if line.strip() == header:
            return index
    return None


def _section_end(lines: list[str], header_index: int) -> int:
    for index in range(header_index + 1, len(lines)):
        if lines[index].lstrip().startswith("["):
            return index
    return len(lines)


def _line_key(line: str) -> str | None:
    match = re.match(r"\s*([A-Za-z0-9_-]+)\s*=", line)
    return match.group(1) if match else None


def _format_key(key: str, value: str) -> str:
    return f'{key} = "{_escape(value)}"'


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _append_section(text: str, header: str, updates: dict[str, str]) -> str:
    body = "\n".join(_format_key(key, value) for key, value in updates.items())
    prefix = text
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix and not prefix.endswith("\n\n"):
        prefix += "\n"
    return f"{prefix}{header}\n{body}\n"


def _atomic_write(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as file:
        temp_path = Path(file.name)
        file.write(content)
    os.replace(temp_path, path)
