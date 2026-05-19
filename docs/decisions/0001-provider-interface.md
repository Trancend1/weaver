# 0001: Provider Interface

Date: 2026-05-19
Status: accepted

## Context

Weaver must call multiple LLM backends (DeepSeek, Gemini, Ollama, and a deterministic Fake) without leaking vendor specifics into the translation orchestrator. CI runs without network access, and the maintainer's primary hardware cannot host a useful local model, so a zero-dependency provider must satisfy the same contract as the real ones. Adding a new vendor must not require touching `services/translation.py`. API keys must never live in `project.toml`; only environment variables.

## Decision

Define a single abstract base class `LLMProvider` in [src/weaver/providers/base.py](../../src/weaver/providers/base.py) with two methods:

- `translate(request: TranslationRequest) -> TranslationResponse` — synchronous, may raise any subclass of `weaver.errors.ProviderError`.
- `healthcheck() -> ProviderStatus` — must not raise; failures are reported in `ProviderStatus(healthy=False, message=...)`.

Concrete providers subclass `LLMProvider`, declare a `name` attribute (`fake`, `deepseek`, `gemini`, `ollama`), and register through `weaver.providers.registry.build_provider(config: Mapping[str, Any]) -> LLMProvider` keyed on `provider.type`. Cloud providers use the upstream vendor SDK (`openai`, `google-generativeai`); Ollama speaks HTTP via `httpx`; `FakeProvider` is deterministic with a configurable response pattern and synthetic-failure rate for retry-path testing. API keys come from environment variables named `<PROVIDER>_API_KEY`.

Token usage flows back via `TranslationResponse.input_tokens` / `output_tokens` (None when the provider does not report); cloud providers fill these in for cost tracking.

## Consequences

**Easier:** New providers ship as one module plus a `register_provider(...)` call. The orchestrator never branches on provider type. CI is fully offline through `FakeProvider`. `healthcheck()` powers both `weaver inspect --healthcheck` and the `translate` pre-flight gate that exits `3` on dead providers.

**Harder:** Each vendor brings its own pinned SDK, retry semantics, and error vocabulary that must be mapped onto `ProviderError`/`ProviderTimeout`/`ProviderUnavailable`/`ProviderResponseError`. Synchronous-only — adding async would be a breaking change to every concrete provider. No rate-limit awareness inside the orchestrator; deferred until a real user hits a wall. The factory is a hand-coded registry, not a plugin loader — explicit imports in `providers/__init__.py` are required.
