"""Per-task routing resolver + set_routing writer tests (ADR 018 D4/D7)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from weaver.core.connection_registry import Connection, register_connection
from weaver.core.task_types import TaskType
from weaver.errors import ConfigError
from weaver.services.config_writer import set_routing
from weaver.services.routing import (
    resolve_active_ai,
    resolve_chain,
    resolve_consumer_config,
    resolve_provider_config,
)

_DUMMY = Path("project.toml")


@pytest.fixture(autouse=True)
def isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEAVER_CONNECTIONS_PATH", str(tmp_path / "connections.toml"))


def _register_openrouter() -> None:
    register_connection(
        Connection(
            name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            default_model="deepseek/deepseek-chat",
        )
    )


def test_resolve_no_routing_returns_legacy_provider() -> None:
    data = {
        "provider": {"type": "custom", "model": "m", "base_url": "https://x", "api_key_env": "K"}
    }
    cfg = resolve_provider_config(_DUMMY, TaskType.translate, data=data)
    assert cfg == data["provider"]


def test_resolve_routing_uses_connection_and_entry_model() -> None:
    _register_openrouter()
    data = {
        "provider": {"model": "legacy"},
        "routing": {"translate": {"connection": "openrouter", "model": "chosen-model"}},
    }
    cfg = resolve_provider_config(_DUMMY, TaskType.translate, data=data)
    assert cfg["protocol"] == "openai_chat"
    assert cfg["base_url"] == "https://openrouter.ai/api/v1"
    assert cfg["api_key_env"] == "OPENROUTER_API_KEY"
    assert cfg["model"] == "chosen-model"


def test_resolve_routing_falls_back_to_connection_default_model() -> None:
    _register_openrouter()
    data = {"routing": {"translate": {"connection": "openrouter"}}}
    cfg = resolve_provider_config(_DUMMY, TaskType.translate, data=data)
    assert cfg["model"] == "deepseek/deepseek-chat"


def test_resolve_unknown_connection_raises() -> None:
    data = {"routing": {"translate": {"connection": "ghost"}}}
    with pytest.raises(ConfigError, match="unknown connection"):
        resolve_provider_config(_DUMMY, TaskType.translate, data=data)


def test_resolve_routing_only_affects_named_task() -> None:
    _register_openrouter()
    data = {
        "provider": {"model": "legacy", "base_url": "https://x", "api_key_env": "K"},
        "routing": {"translate": {"connection": "openrouter"}},
    }
    # glossary_suggest has no routing entry → falls back to [provider]
    cfg = resolve_provider_config(_DUMMY, TaskType.glossary_suggest, data=data)
    assert cfg == data["provider"]


def test_active_ai_routing() -> None:
    _register_openrouter()
    data = {"routing": {"translate": {"connection": "openrouter", "model": "x"}}}
    ai = resolve_active_ai(_DUMMY, TaskType.translate, data=data)
    assert ai.source == "routing"
    assert ai.connection_name == "openrouter"
    assert ai.model == "x"
    assert ai.connection_exists is True


def test_active_ai_missing_connection_is_flagged() -> None:
    data = {"routing": {"translate": {"connection": "ghost", "model": "x"}}}
    ai = resolve_active_ai(_DUMMY, TaskType.translate, data=data)
    assert ai.connection_exists is False
    assert ai.connection_name == "ghost"


def test_active_ai_legacy_provider() -> None:
    data = {"provider": {"model": "pm"}}
    ai = resolve_active_ai(_DUMMY, TaskType.translate, data=data)
    assert ai.source == "provider"
    assert ai.connection_name is None
    assert ai.model == "pm"


def test_active_ai_unset() -> None:
    ai = resolve_active_ai(_DUMMY, TaskType.translate, data={})
    assert ai.source == "unset"
    assert ai.model == "—"


def test_consumer_inherits_translate_when_task_unset() -> None:
    # Connection-first project: only translate is routed. A secondary task
    # (glossary_suggest) with no own entry and empty [provider] inherits the
    # project's translate Active AI instead of failing with an incomplete config.
    _register_openrouter()
    data = {"routing": {"translate": {"connection": "openrouter", "model": "x"}}}
    cfg = resolve_consumer_config(_DUMMY, TaskType.glossary_suggest, data=data)
    assert cfg["base_url"] == "https://openrouter.ai/api/v1"
    assert cfg["model"] == "x"


def test_consumer_uses_own_routing_when_set() -> None:
    _register_openrouter()
    register_connection(
        Connection(name="other", base_url="https://other/v1", api_key_env="K2", default_model="m2")
    )
    data = {
        "routing": {
            "translate": {"connection": "openrouter", "model": "x"},
            "candidate": {"connection": "other", "model": "c"},
        }
    }
    cfg = resolve_consumer_config(_DUMMY, TaskType.candidate, data=data)
    assert cfg["base_url"] == "https://other/v1"
    assert cfg["model"] == "c"


def test_consumer_uses_legacy_provider_when_present() -> None:
    data = {
        "provider": {"type": "custom", "model": "m", "base_url": "https://x", "api_key_env": "K"}
    }
    cfg = resolve_consumer_config(_DUMMY, TaskType.glossary_suggest, data=data)
    assert cfg == data["provider"]


def test_set_routing_writes_block(tmp_path: Path) -> None:
    p = tmp_path / "project.toml"
    p.write_text('[provider]\nmodel = "m"\n', encoding="utf-8")
    set_routing(p, task="translate", connection="openrouter", model="deepseek/deepseek-chat")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    assert data["routing"]["translate"]["connection"] == "openrouter"
    assert data["routing"]["translate"]["model"] == "deepseek/deepseek-chat"
    assert data["provider"]["model"] == "m"  # legacy block preserved


def test_set_routing_omits_empty_model(tmp_path: Path) -> None:
    p = tmp_path / "project.toml"
    p.write_text("", encoding="utf-8")
    set_routing(p, task="translate", connection="openrouter", model="")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    assert "model" not in data["routing"]["translate"]


def test_set_routing_unknown_task_raises(tmp_path: Path) -> None:
    p = tmp_path / "project.toml"
    p.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError):
        set_routing(p, task="bogus", connection="c", model="m")


def test_set_routing_writes_fallback_array(tmp_path: Path) -> None:
    p = tmp_path / "project.toml"
    p.write_text("", encoding="utf-8")
    set_routing(
        p,
        task="translate",
        connection="openrouter",
        model="m",
        fallbacks=[("backup", "bm"), ("local", "")],
    )
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    fb = data["routing"]["translate"]["fallback"]
    assert fb[0] == {"connection": "backup", "model": "bm"}
    assert fb[1] == {"connection": "local"}  # empty model omitted


def test_set_routing_preserves_existing_fallback_when_none(tmp_path: Path) -> None:
    p = tmp_path / "project.toml"
    p.write_text("", encoding="utf-8")
    set_routing(
        p, task="translate", connection="openrouter", model="m", fallbacks=[("backup", "bm")]
    )
    # switch the primary model without passing fallbacks -> fallback survives
    set_routing(p, task="translate", connection="openrouter", model="m2")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    assert data["routing"]["translate"]["model"] == "m2"
    assert data["routing"]["translate"]["fallback"] == [{"connection": "backup", "model": "bm"}]


def test_set_routing_clears_fallback_with_empty_list(tmp_path: Path) -> None:
    p = tmp_path / "project.toml"
    p.write_text("", encoding="utf-8")
    set_routing(
        p, task="translate", connection="openrouter", model="m", fallbacks=[("backup", "bm")]
    )
    set_routing(p, task="translate", connection="openrouter", model="m", fallbacks=[])
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    assert "fallback" not in data["routing"]["translate"]


def test_set_routing_preserves_other_sections(tmp_path: Path) -> None:
    p = tmp_path / "project.toml"
    p.write_text(
        '[provider]\nmodel = "legacy"\n\n[translation]\nhonorifics = "preserve"\n', "utf-8"
    )
    set_routing(p, task="translate", connection="openrouter", model="m")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    assert data["provider"]["model"] == "legacy"
    assert data["translation"]["honorifics"] == "preserve"
    assert data["routing"]["translate"]["connection"] == "openrouter"


# --- workspace [defaults] tier ---------------------------------------------


def test_defaults_tier_used_when_no_routing_and_no_provider_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_openrouter()
    monkeypatch.setattr(
        "weaver.services.routing.load_global_config",
        lambda *a, **k: {
            "defaults": {"default_connection": "openrouter", "default_model": "from-defaults"}
        },
    )
    cfg = resolve_provider_config(_DUMMY, TaskType.translate, data={})
    assert cfg["base_url"] == "https://openrouter.ai/api/v1"
    assert cfg["model"] == "from-defaults"


def test_defaults_tier_not_used_when_provider_has_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_openrouter()
    monkeypatch.setattr(
        "weaver.services.routing.load_global_config",
        lambda *a, **k: {"defaults": {"default_connection": "openrouter"}},
    )
    data = {"provider": {"model": "legacy", "base_url": "https://x", "api_key_env": "K"}}
    cfg = resolve_provider_config(_DUMMY, TaskType.translate, data=data)
    assert cfg == data["provider"]


# --- fallback chain ---------------------------------------------------------


def test_resolve_chain_primary_only_when_no_fallback() -> None:
    _register_openrouter()
    data = {"routing": {"translate": {"connection": "openrouter", "model": "m"}}}
    chain = resolve_chain(_DUMMY, TaskType.translate, data=data)
    assert len(chain) == 1
    assert chain[0].connection_name == "openrouter"
    assert chain[0].model == "m"


def test_resolve_chain_includes_fallbacks_in_order() -> None:
    _register_openrouter()
    register_connection(Connection(name="backup", base_url="https://b/v1", api_key_env="B"))
    data = {
        "routing": {
            "translate": {
                "connection": "openrouter",
                "model": "m",
                "fallback": [{"connection": "backup", "model": "bm"}],
            }
        }
    }
    chain = resolve_chain(_DUMMY, TaskType.translate, data=data)
    assert [c.connection_name for c in chain] == ["openrouter", "backup"]
    assert chain[1].model == "bm"


def test_resolve_chain_skips_unknown_fallback_connection() -> None:
    _register_openrouter()
    data = {
        "routing": {
            "translate": {"connection": "openrouter", "fallback": [{"connection": "ghost"}]}
        }
    }
    chain = resolve_chain(_DUMMY, TaskType.translate, data=data)
    assert len(chain) == 1  # unknown fallback skipped; primary still resolves
