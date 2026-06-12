# Sprint R — AI Glossary-Target Suggestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an on-demand "Suggest with AI" button to glossary candidate review that proposes an editable EN target for a JP term, grounded in example sentences, using the user's configured provider.

**Architecture:** A domain-agnostic `complete()` transport primitive on the provider protocol; a `glossary_suggestion` service that owns the term prompt + strict-JSON parse/validation; a thin HTMX router endpoint that fills the existing editable target field. Ephemeral (no persistence/migration). Provider is fully config-driven via `build_provider()` — no hidden vendor default.

**Tech Stack:** Python 3.11, FastAPI + Jinja2/HTMX, pytest, ruff, pyright. Providers: deepseek (OpenAI-compatible, also serves `custom`), gemini, ollama, fake.

**Spec:** `docs/superpowers/specs/2026-06-12-glossary-ai-target-suggestion-design.md`
**ADR:** `docs/decisions/014-provider-complete-primitive-and-glossary-suggestion.md`

---

## Task 0: Branch hygiene (resolve the #3 dependency)

**Context:** The current branch `feat/glossary-terms-search-examples` carries the un-committed #2/#3 work (terms search/pagination + lazy examples), including `services/glossary_review.py::examples_for_source` / `_segment_examples`, which **this sprint depends on** (grounding). The two Sprint R design docs (spec + ADR) are untracked in the same tree.

**Decision (documented deviation from "branch Sprint R from main"):** Because Sprint R hard-depends on #3's read-only `_segment_examples`, branch Sprint R **stacked on** the #2/#3 branch, not from `main`. When the #2/#3 PR merges to `main`, rebase Sprint R onto `main`. This keeps each PR one concern (Sprint R's diff, post-merge, shows only Sprint R files). Building from `main` now would fail to import `examples_for_source`.

- [ ] **Step 1: Commit #2/#3 on its branch (Sprint R docs excluded)**

```bash
git add src/weaver/storage/glossary.py src/weaver/services/glossary_terms.py \
  src/weaver/services/glossary_review.py src/weaver/api/routers/ui_admin.py \
  src/weaver/api/templates/partials/_glossary_terms.html \
  src/weaver/api/templates/partials/_glossary_candidates.html \
  src/weaver/api/templates/partials/_glossary_examples.html \
  tests/unit/storage/test_glossary.py tests/unit/services/test_glossary_terms.py \
  tests/unit/services/test_glossary_review.py tests/unit/api/test_ui_glossary.py
git commit -m "feat(glossary): approved-terms search + pagination and lazy candidate examples"
```

- [ ] **Step 2: Create the Sprint R branch stacked on #2/#3 (untracked docs travel along)**

```bash
git checkout -b feat/sprint-r-glossary-ai-suggestion
git add docs/superpowers/specs/2026-06-12-glossary-ai-target-suggestion-design.md \
  docs/decisions/014-provider-complete-primitive-and-glossary-suggestion.md \
  docs/superpowers/plans/2026-06-12-sprint-r-glossary-ai-suggestion.md
git commit -m "docs(glossary-ai): Sprint R spec, ADR 014, implementation plan"
```

- [ ] **Step 3: Verify clean base**

Run: `git status --short --branch && uv run pytest tests/unit/services/test_glossary_review.py -q`
Expected: clean tree on `feat/sprint-r-glossary-ai-suggestion`; examples tests pass (confirms #3 helper present).

---

## Task 1: `Completion` type + abstract `complete()` + FakeProvider

**Files:**
- Modify: `src/weaver/providers/types.py`
- Modify: `src/weaver/providers/base.py`
- Modify: `src/weaver/providers/fake.py`
- Modify: `src/weaver/providers/registry.py:72-77` (`_build_fake`)
- Test: `tests/unit/providers/test_fake.py` (create if absent)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/providers/test_fake.py
from weaver.providers.fake import FakeProvider
from weaver.providers.types import Completion


def test_fake_complete_is_deterministic_and_parseable() -> None:
    provider = FakeProvider(completion='{"target": "[FAKE]"}')
    out = provider.complete("any prompt mentioning json", max_output_tokens=64)
    assert isinstance(out, Completion)
    assert out.text == '{"target": "[FAKE]"}'
    assert out.input_tokens is None and out.output_tokens is None
    # deterministic across calls
    assert provider.complete("other", max_output_tokens=8).text == '{"target": "[FAKE]"}'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/providers/test_fake.py::test_fake_complete_is_deterministic_and_parseable -v`
Expected: FAIL — `cannot import name 'Completion'` / `FakeProvider` has no `complete`.

- [ ] **Step 3: Add the `Completion` type**

```python
# src/weaver/providers/types.py  (append after TranslationResponse)
@dataclass(frozen=True)
class Completion:
    """Raw text completion + token usage from a provider's `complete()` primitive.

    Domain-agnostic transport result: `text` is the model's verbatim output.
    `input_tokens`/`output_tokens` are None when the provider does not report usage.
    """

    text: str
    input_tokens: int | None
    output_tokens: int | None
    raw_response: str
```

- [ ] **Step 4: Add the abstract method on the base**

```python
# src/weaver/providers/base.py
# add import:
from weaver.providers.types import Completion, TranslationRequest, TranslationResponse

# add inside class LLMProvider, after healthcheck():
    @abstractmethod
    def complete(
        self, prompt: str, *, system: str | None = None, max_output_tokens: int
    ) -> Completion:
        """Return a raw text completion + token usage for an opaque prompt.

        Transport primitive only — it carries no domain knowledge. Callers build
        their own prompt and parse/validate the result in a service. Implementations
        may raise any `weaver.errors.ProviderError` subclass on failure.
        """
```

- [ ] **Step 5: Implement FakeProvider.complete + `completion` config**

```python
# src/weaver/providers/fake.py
# import: from weaver.providers.types import Completion, TranslationRequest, TranslationResponse

# add `completion` param to __init__ signature and store it:
    def __init__(
        self,
        *,
        pattern: str = "[FAKE] {source}",
        fail_rate: float = 0.0,
        seed: int = 0,
        model: str = "fake-1",
        completion: str = '{"target": "[FAKE]"}',
    ) -> None:
        ...
        self._completion = completion

# add the method after translate():
    def complete(
        self, prompt: str, *, system: str | None = None, max_output_tokens: int
    ) -> Completion:
        if self._fail_rate > 0.0 and self._random.random() < self._fail_rate:
            raise ProviderResponseError(
                "FakeProvider synthetic failure. "
                "Likely cause: fail_rate>0 sampled this call. "
                "Next command: rerun with FakeProvider(fail_rate=0)."
            )
        return Completion(
            text=self._completion, input_tokens=None, output_tokens=None,
            raw_response=self._completion,
        )
```

```python
# src/weaver/providers/registry.py  _build_fake — thread the new option:
def _build_fake(config: Mapping[str, Any]) -> LLMProvider:
    model = str(config.get("model", "fake-1"))
    pattern = str(config.get("pattern", "[FAKE] {source}"))
    completion = str(config.get("completion", '{"target": "[FAKE]"}'))
    fail_rate = read_float(config, "fail_rate", 0.0, minimum=0.0, maximum=1.0)
    seed = read_int(config, "seed", 0)
    return FakeProvider(
        pattern=pattern, fail_rate=fail_rate, seed=seed, model=model, completion=completion
    )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/providers/test_fake.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/weaver/providers/types.py src/weaver/providers/base.py \
  src/weaver/providers/fake.py src/weaver/providers/registry.py tests/unit/providers/test_fake.py
git commit -m "feat(providers): add domain-agnostic complete() primitive + FakeProvider impl"
```

---

## Task 2: DeepSeekProvider.complete (also serves `custom`)

**Files:**
- Modify: `src/weaver/providers/deepseek.py`
- Test: `tests/unit/providers/test_deepseek.py` (add to existing; create if absent)

- [ ] **Step 1: Write the failing tests (mock the OpenAI client boundary)**

```python
# tests/unit/providers/test_deepseek.py
import pytest
from weaver.errors import ProviderResponseError
from weaver.providers.deepseek import DeepSeekConfig, DeepSeekProvider
from weaver.providers.types import Completion


class _Msg:
    def __init__(self, content): self.content = content
class _Choice:
    def __init__(self, content): self.message = _Msg(content)
class _Usage:
    def __init__(self, p, c): self.prompt_tokens = p; self.completion_tokens = c
class _Resp:
    def __init__(self, content, p=11, c=3):
        self.choices = [_Choice(content)]; self.usage = _Usage(p, c)


class _FakeClient:
    def __init__(self, resp=None, exc=None):
        self._resp, self._exc, self.calls = resp, exc, []
        self.chat = self
        self.completions = self
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc: raise self._exc
        return self._resp


def _provider(client) -> DeepSeekProvider:
    return DeepSeekProvider(config=DeepSeekConfig(), client=client)


def test_deepseek_complete_returns_text_and_usage() -> None:
    client = _FakeClient(resp=_Resp('{"target": "Demon King"}', p=11, c=3))
    out = _provider(client).complete("return json target", system="sys", max_output_tokens=64)
    assert isinstance(out, Completion)
    assert out.text == '{"target": "Demon King"}'
    assert (out.input_tokens, out.output_tokens) == (11, 3)
    sent = client.calls[0]
    assert sent["max_tokens"] == 64
    assert sent["messages"][0] == {"role": "system", "content": "sys"}
    assert sent["messages"][-1]["content"] == "return json target"


def test_deepseek_complete_jsonmode_rejection_is_visible_not_silent() -> None:
    # A custom/OpenAI-compatible endpoint that rejects response_format=json_object
    # must surface as a provider error — never a silent fallback/empty success.
    class _BadRequestError(Exception):
        pass
    client = _FakeClient(exc=_BadRequestError("response_format json_object unsupported"))
    with pytest.raises(ProviderResponseError):
        _provider(client).complete("p mentioning json", max_output_tokens=8)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/providers/test_deepseek.py -v -k complete`
Expected: FAIL — `DeepSeekProvider` has no `complete`.

- [ ] **Step 3: Implement complete()**

```python
# src/weaver/providers/deepseek.py
# import Completion alongside the existing types:
from weaver.providers.types import Completion, TranslationRequest, TranslationResponse

# add after translate():
    def complete(
        self, prompt: str, *, system: str | None = None, max_output_tokens: int
    ) -> Completion:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self._chat_completion(messages=messages, max_tokens=max_output_tokens)
        content = _extract_content(response)
        return Completion(
            text=content,
            input_tokens=_usage(response, "prompt_tokens"),
            output_tokens=_usage(response, "completion_tokens"),
            raw_response=content,
        )
```

Note: `_chat_completion` already wraps every client exception in `_translate_openai_error`, which maps a json-mode/bad-request rejection to `ProviderResponseError` — so the §custom error-visibility requirement holds with no extra code. The test pins it.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/providers/test_deepseek.py -v -k complete`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/weaver/providers/deepseek.py tests/unit/providers/test_deepseek.py
git commit -m "feat(providers): DeepSeek/custom complete() with visible json-mode errors"
```

---

## Task 3: GeminiProvider.complete

**Files:**
- Modify: `src/weaver/providers/gemini.py`
- Test: `tests/unit/providers/test_gemini.py` (add; create if absent)

- [ ] **Step 1: Write the failing test (mock the genai model)**

```python
# tests/unit/providers/test_gemini.py
from weaver.providers.gemini import GeminiConfig, GeminiProvider
from weaver.providers.types import Completion


class _Meta:
    def __init__(self, p, c): self.prompt_token_count = p; self.candidates_token_count = c
class _Resp:
    def __init__(self, text, p=9, c=2):
        self.text = text; self.candidates = []; self.usage_metadata = _Meta(p, c)


class _FakeModel:
    def __init__(self, resp): self._resp = resp; self.calls = []
    def generate_content(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs)); return self._resp


def test_gemini_complete_combines_system_and_returns_usage() -> None:
    model = _FakeModel(_Resp('{"target": "Hero"}', p=9, c=2))
    provider = GeminiProvider(config=GeminiConfig(), client=model)
    out = provider.complete("user prompt json", system="SYS", max_output_tokens=32)
    assert isinstance(out, Completion)
    assert out.text == '{"target": "Hero"}'
    assert (out.input_tokens, out.output_tokens) == (9, 2)
    prompt_sent, kwargs = model.calls[0]
    assert prompt_sent == "SYS\n\nuser prompt json"
    assert kwargs["generation_config"] == {"max_output_tokens": 32}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/providers/test_gemini.py -v -k complete`
Expected: FAIL — no `complete`.

- [ ] **Step 3: Implement complete()**

```python
# src/weaver/providers/gemini.py
from weaver.providers.types import Completion, TranslationRequest, TranslationResponse

# add after translate():
    def complete(
        self, prompt: str, *, system: str | None = None, max_output_tokens: int
    ) -> Completion:
        full = f"{system}\n\n{prompt}" if system else prompt
        try:
            response = self._client.generate_content(
                full, generation_config={"max_output_tokens": max_output_tokens}
            )
        except Exception as exc:  # noqa: BLE001 — mapped to a typed ProviderError
            raise _translate_gemini_error(exc) from exc
        text = _extract_text(response)
        return Completion(
            text=text,
            input_tokens=_usage(response, "prompt_token_count"),
            output_tokens=_usage(response, "candidates_token_count"),
            raw_response=text,
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/providers/test_gemini.py -v -k complete`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/weaver/providers/gemini.py tests/unit/providers/test_gemini.py
git commit -m "feat(providers): Gemini complete() honoring max_output_tokens"
```

---

## Task 4: OllamaProvider.complete

**Files:**
- Modify: `src/weaver/providers/ollama.py`
- Test: `tests/unit/providers/test_ollama.py` (add; create if absent)

- [ ] **Step 1: Write the failing test (mock httpx client)**

```python
# tests/unit/providers/test_ollama.py
import httpx
from weaver.providers.ollama import OllamaConfig, OllamaProvider
from weaver.providers.types import Completion


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ollama_complete_returns_text_and_usage() -> None:
    seen = {}
    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        seen["payload"] = _json.loads(request.content)
        return httpx.Response(
            200,
            json={"response": '{"target": "cat"}', "prompt_eval_count": 7, "eval_count": 2},
        )
    provider = OllamaProvider(config=OllamaConfig(), client=_client(handler))
    out = provider.complete("p json", system="SYS", max_output_tokens=16)
    assert isinstance(out, Completion)
    assert out.text == '{"target": "cat"}'
    assert (out.input_tokens, out.output_tokens) == (7, 2)
    assert seen["payload"]["prompt"] == "SYS\n\np json"
    assert seen["payload"]["options"]["num_predict"] == 16
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/providers/test_ollama.py -v -k complete`
Expected: FAIL — no `complete`.

- [ ] **Step 3: Implement complete() (small generate variant honoring num_predict)**

```python
# src/weaver/providers/ollama.py
from weaver.providers.types import Completion, TranslationRequest, TranslationResponse

# add after translate():
    def complete(
        self, prompt: str, *, system: str | None = None, max_output_tokens: int
    ) -> Completion:
        full = f"{system}\n\n{prompt}" if system else prompt
        payload = self._generate_raw(full, num_predict=max_output_tokens)
        text = _extract_text(payload)
        return Completion(
            text=text,
            input_tokens=_usage(payload, "prompt_eval_count"),
            output_tokens=_usage(payload, "eval_count"),
            raw_response=text,
        )

# add a helper next to _generate (keeps _generate untouched for translate):
    def _generate_raw(self, prompt: str, *, num_predict: int) -> dict[str, Any]:
        url = f"{self._config.base_url.rstrip('/')}/api/generate"
        payload = {
            "model": self._config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self._config.temperature,
                "top_p": self._config.top_p,
                "num_predict": num_predict,
            },
        }
        try:
            response = self._client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(
                f"Ollama request timed out: {exc}. "
                "Likely cause: model loading or generation exceeded timeout. "
                "Next command: raise `translation.timeout_seconds` or use a smaller model."
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailable(
                f"Cannot reach Ollama at {self._config.base_url}: {exc}. "
                "Likely cause: Ollama daemon is not running. "
                "Next command: start Ollama (`ollama serve`), then rerun."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderResponseError(
                f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text}. "
                "Likely cause: model name unknown or request malformed. "
                "Next command: run `ollama list` and confirm the model is pulled."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                f"Ollama HTTP error: {exc}. "
                "Likely cause: network or daemon error. "
                "Next command: check `ollama serve` logs, then rerun."
            ) from exc
```

Note: `_generate` (used by `translate`) and `_generate_raw` (used by `complete`) duplicate the
HTTP error mapping. If the duplication bothers a reviewer, a follow-up can fold `_generate`
onto `_generate_raw` — out of scope here to keep `translate` untouched.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/providers/test_ollama.py -v -k complete`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/weaver/providers/ollama.py tests/unit/providers/test_ollama.py
git commit -m "feat(providers): Ollama complete() with num_predict cap"
```

---

## Task 5: Term-suggestion prompt + version constant

**Files:**
- Modify: `src/weaver/providers/prompts.py`
- Test: `tests/unit/providers/test_prompts.py` (add; create if absent)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/providers/test_prompts.py
from weaver.providers.prompts import (
    GLOSSARY_SUGGEST_PROMPT_VERSION,
    render_glossary_suggestion_prompt,
)


def test_glossary_suggestion_prompt_is_grounded_and_jsonmode_safe() -> None:
    prompt = render_glossary_suggestion_prompt(
        source="魔王", category="title", examples=["その時、魔王が現れた。"],
        source_lang="ja", target_lang="en",
    )
    assert "魔王" in prompt
    assert "その時、魔王が現れた。" in prompt
    assert "json" in prompt.lower()          # json-mode-strict endpoints require it
    assert '{"target"' in prompt              # the strict shape is requested
    assert isinstance(GLOSSARY_SUGGEST_PROMPT_VERSION, str)


def test_glossary_suggestion_prompt_handles_no_examples() -> None:
    prompt = render_glossary_suggestion_prompt(
        source="勇者", category=None, examples=[], source_lang="ja", target_lang="en",
    )
    assert "勇者" in prompt
    assert "json" in prompt.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/providers/test_prompts.py -v -k glossary`
Expected: FAIL — names not defined.

- [ ] **Step 3: Implement the prompt renderer**

```python
# src/weaver/providers/prompts.py  (append)
GLOSSARY_SUGGEST_PROMPT_VERSION = "glossary-suggest-1.0"


def render_glossary_suggestion_prompt(
    *,
    source: str,
    category: str | None,
    examples: list[str],
    source_lang: str,
    target_lang: str,
) -> str:
    """Build the term-suggestion prompt (domain content; provider sees an opaque string).

    Requests a strict minimal JSON object so the service can parse + validate. The
    literal word "json" is present so OpenAI-compatible json-mode endpoints accept it.
    """
    lines = [
        f"You are a translation-glossary assistant for {source_lang} to {target_lang}.",
        f'Propose a concise {target_lang} glossary target for this {source_lang} term.',
        "Return ONLY a strict JSON object of the form {\"target\": \"...\"} and nothing else.",
        "The target must be a short term or noun phrase, not a sentence, not multiline.",
        "",
        f"Term: {source}",
    ]
    if category:
        lines.append(f"Category: {category}")
    if examples:
        lines.append("Example sentences (for context):")
        lines.extend(f"- {ex}" for ex in examples)
    return "\n".join(lines)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/providers/test_prompts.py -v -k glossary`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/weaver/providers/prompts.py tests/unit/providers/test_prompts.py
git commit -m "feat(providers): glossary target-suggestion prompt (strict json, grounded)"
```

---

## Task 6: `glossary_suggestion` service + strict validation

**Files:**
- Create: `src/weaver/services/glossary_suggestion.py`
- Modify: `src/weaver/errors.py` (add `GlossarySuggestionError`)
- Test: `tests/unit/services/test_glossary_suggestion.py`

- [ ] **Step 1: Add the error type**

```python
# src/weaver/errors.py — add near the other provider/glossary errors:
class GlossarySuggestionError(WeaverError):
    """The AI returned no usable glossary target (empty/non-JSON/sentence/over-long)."""
```

- [ ] **Step 2: Write the failing tests (inject a stub provider — the boundary)**

```python
# tests/unit/services/test_glossary_suggestion.py
from __future__ import annotations

from pathlib import Path

import pytest

from weaver.errors import GlossarySuggestionError, ProviderUnavailable
from weaver.providers.base import LLMProvider, ProviderStatus
from weaver.providers.types import Completion
from weaver.services.glossary_review import open_glossary_review_session
from weaver.services.glossary_suggestion import GlossarySuggestion, suggest_glossary_target
from weaver.services.project import initialize_project

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


class _StubProvider(LLMProvider):
    name = "stub"
    def __init__(self, *, text: str = "", exc: Exception | None = None,
                 healthy: bool = True) -> None:
        self._text, self._exc, self._healthy = text, exc, healthy
        self.last_prompt: str | None = None
    def translate(self, request):  # pragma: no cover - unused
        raise NotImplementedError
    def healthcheck(self) -> ProviderStatus:
        return ProviderStatus(self._healthy, self.name, "stub-1",
                              None if self._healthy else "down", 1)
    def complete(self, prompt, *, system=None, max_output_tokens):
        self.last_prompt = prompt
        if self._exc:
            raise self._exc
        return Completion(text=self._text, input_tokens=5, output_tokens=2,
                          raw_response=self._text)


def _candidate_source(project_toml: Path) -> tuple[int, str]:
    with open_glossary_review_session(project_toml) as session:
        cand = session.next_pending()
        assert cand is not None
        return cand.id, cand.source


def test_suggest_returns_grounded_target(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path)
    cid, source = _candidate_source(init.project_toml)
    stub = _StubProvider(text='{"target": "Demon King"}')

    out = suggest_glossary_target(init.project_toml, cid, cwd=tmp_path, provider=stub)

    assert isinstance(out, GlossarySuggestion)
    assert out.target == "Demon King"
    assert out.provider == "stub" and out.model == "stub-1"
    assert (out.input_tokens, out.output_tokens) == (5, 2)
    # grounded: the prompt the provider saw contains the candidate's source term
    assert source in (stub.last_prompt or "")


def test_suggest_unavailable_provider_raises(tmp_path: Path) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path)
    cid, _ = _candidate_source(init.project_toml)
    with pytest.raises(ProviderUnavailable):
        suggest_glossary_target(
            init.project_toml, cid, cwd=tmp_path, provider=_StubProvider(healthy=False)
        )


@pytest.mark.parametrize("bad", [
    "",                       # empty completion
    "not json at all",        # non-JSON
    '{"nope": "x"}',          # missing target key
    '{"target": ""}',         # empty target
    '{"target": "line1\\nline2"}',  # multiline
    '{"target": "' + "x" * 200 + '"}',  # over-length
    '{"target": "This is a full sentence that explains the term."}',  # sentence-shaped
])
def test_suggest_rejects_unusable_output(tmp_path: Path, bad: str) -> None:
    init = initialize_project(FIXTURE_EPUB, cwd=tmp_path)
    cid, _ = _candidate_source(init.project_toml)
    with pytest.raises(GlossarySuggestionError):
        suggest_glossary_target(
            init.project_toml, cid, cwd=tmp_path, provider=_StubProvider(text=bad)
        )
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/unit/services/test_glossary_suggestion.py -v`
Expected: FAIL — module/function not defined.

- [ ] **Step 4: Implement the service**

```python
# src/weaver/services/glossary_suggestion.py
"""On-demand AI glossary-target suggestion (Sprint R).

Builds a term-suggestion prompt grounded in the candidate's source term and its
example sentences, calls the user's configured provider via the domain-agnostic
`complete()` primitive, and parses a strict minimal JSON object {"target": "..."}.

Ephemeral: nothing is persisted here. The human's approve/edit (the existing flow)
is what writes the glossary term. The provider is resolved from the user's
`[provider]` config — there is no hidden default vendor.
"""

from __future__ import annotations

import json
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from weaver.core.config import load_project_config
from weaver.errors import GlossarySuggestionError
from weaver.providers import LLMProvider, build_provider
from weaver.providers.prompts import (
    GLOSSARY_SUGGEST_PROMPT_VERSION,
    render_glossary_suggestion_prompt,
)
from weaver.services.glossary_review import _segment_examples
from weaver.services.project_paths import resolve_database_path
from weaver.storage.db import connect_readonly_database
from weaver.storage.glossary import get_glossary_candidate
from weaver.storage.projects import ProjectRecord, get_project

EXAMPLE_LIMIT = 3
MAX_TARGET_CHARS = 80
MAX_OUTPUT_TOKENS = 120
_SENTENCE_END = ".!?。！？"

__all__ = ["GlossarySuggestion", "suggest_glossary_target", "GLOSSARY_SUGGEST_PROMPT_VERSION"]


@dataclass(frozen=True)
class GlossarySuggestion:
    target: str
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None


def suggest_glossary_target(
    project_toml: Path,
    candidate_id: int,
    *,
    cwd: Path | None = None,
    provider: LLMProvider | None = None,
) -> GlossarySuggestion:
    data = load_project_config(project_toml)
    provider_config = data["provider"]
    model = str(provider_config.get("model", ""))
    db_path = resolve_database_path(project_toml, cwd=cwd)

    active = build_provider(provider_config) if provider is None else provider
    status = active.healthcheck()
    if not status.healthy:
        from weaver.errors import ProviderUnavailable

        raise ProviderUnavailable(
            f"Provider {active.name} is unavailable: {status.message or 'no detail'}. "
            "Likely cause: API key missing/invalid or endpoint unreachable. "
            "Next command: run `weaver inspect --healthcheck <project.toml>`."
        )

    with closing(connect_readonly_database(db_path)) as connection:
        project = _load_single_project(connection)
        candidate = get_glossary_candidate(connection, candidate_id=candidate_id)
        examples = _segment_examples(
            connection, project_id=project.id, source=candidate.source, limit=EXAMPLE_LIMIT
        )

    prompt = render_glossary_suggestion_prompt(
        source=candidate.source,
        category=candidate.category,
        examples=examples,
        source_lang=project.source_lang,
        target_lang=project.target_lang,
    )
    completion = active.complete(
        prompt,
        system=f"Glossary assistant ({GLOSSARY_SUGGEST_PROMPT_VERSION}).",
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    target = _parse_target(completion.text)
    return GlossarySuggestion(
        target=target,
        provider=active.name,
        model=str(getattr(status, "model", "") or model),
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
    )


def _parse_target(text: str) -> str:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise _unusable("the AI response was not valid JSON") from exc
    if not isinstance(data, dict) or "target" not in data or not isinstance(data["target"], str):
        raise _unusable("the AI response had no `target` string")
    target = data["target"].strip()
    if not target:
        raise _unusable("the AI returned an empty target")
    if "\n" in target:
        raise _unusable("the AI returned a multiline target")
    if len(target) > MAX_TARGET_CHARS:
        raise _unusable("the AI returned an over-long target")
    if target[-1] in _SENTENCE_END:
        raise _unusable("the AI returned a sentence, not a glossary term")
    return target


def _unusable(reason: str) -> GlossarySuggestionError:
    return GlossarySuggestionError(
        f"AI returned no usable suggestion: {reason}. "
        "Likely cause: the model did not follow the glossary-target format. "
        "Next command: retry, or type the target manually."
    )


def _load_single_project(connection) -> ProjectRecord:
    row = connection.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row is None:
        from weaver.errors import ConfigError

        raise ConfigError(
            "Project database has no project row. "
            "Likely cause: database not initialized by `weaver init`. "
            "Next command: run `weaver init <input.epub>`."
        )
    return get_project(connection, int(row["id"]))
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/unit/services/test_glossary_suggestion.py -v`
Expected: PASS (all parametrized rejection cases + grounded + unavailable).

- [ ] **Step 6: Commit**

```bash
git add src/weaver/services/glossary_suggestion.py src/weaver/errors.py \
  tests/unit/services/test_glossary_suggestion.py
git commit -m "feat(glossary): on-demand AI target suggestion service with strict validation"
```

---

## Task 7: Router endpoint `POST .../suggest` + Gate B1 + secret-grep

**Files:**
- Modify: `src/weaver/api/routers/ui_admin.py`
- Test: `tests/unit/api/test_ui_glossary_suggest.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/api/test_ui_glossary_suggest.py
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import weaver.api.routers.ui_admin as ui_admin
from weaver.api.app import create_api_app
from weaver.services.glossary_suggestion import GlossarySuggestion
from weaver.services.project import initialize_project


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    fixtures = Path(__file__).parent.parent.parent / "fixtures"
    epubs = list(fixtures.glob("*.epub"))
    if not epubs:
        pytest.skip("no EPUB fixture available")
    initialize_project(epubs[0], cwd=tmp_path)
    return TestClient(create_api_app(tmp_path))


def _name(c: TestClient) -> str:
    return c.get("/projects").json()["projects"][0]["name"]


def _cid(c: TestClient, name: str) -> int:
    page = c.get(f"/projects/{name}/glossary/candidates").json()
    if not page["candidates"]:
        pytest.skip("fixture produced no glossary candidates")
    return page["candidates"][0]["id"]


def test_suggest_fills_target_and_shows_cost(client: TestClient, monkeypatch) -> None:
    name = _name(client)
    cid = _cid(client, name)
    monkeypatch.setattr(
        ui_admin, "suggest_glossary_target",
        lambda *a, **k: GlossarySuggestion("Demon King", "deepseek", "deepseek-chat", 11, 3),
    )
    r = client.post(f"/ui/projects/{name}/glossary/candidates/{cid}/suggest")
    assert r.status_code == 200
    assert 'value="Demon King"' in r.text       # editable field pre-filled (gate 4)
    assert "deepseek" in r.text and "deepseek-chat" in r.text  # cost/provenance (gate 6)
    assert "14 tokens" in r.text or "~14" in r.text


def test_suggest_failure_is_visible_not_silent(client: TestClient, monkeypatch) -> None:
    from weaver.errors import GlossarySuggestionError
    name = _name(client)
    cid = _cid(client, name)
    def _boom(*a, **k):
        raise GlossarySuggestionError("AI returned no usable suggestion: empty.")
    monkeypatch.setattr(ui_admin, "suggest_glossary_target", _boom)
    r = client.post(f"/ui/projects/{name}/glossary/candidates/{cid}/suggest")
    assert r.status_code == 200          # fragment swap, error shown in-place
    assert "no usable suggestion" in r.text
    assert 'value="' not in r.text or 'value=""' in r.text  # no garbage pre-fill


def test_gate_b1_glossary_render_calls_no_provider(client: TestClient, monkeypatch) -> None:
    name = _name(client)
    called = {"n": 0}
    def _spy(*a, **k):
        called["n"] += 1
        return GlossarySuggestion("X", "fake", "fake-1", None, None)
    monkeypatch.setattr(ui_admin, "suggest_glossary_target", _spy)
    client.get(f"/ui/projects/{name}/glossary")               # render
    client.get(f"/ui/projects/{name}/glossary/candidates")    # fragment
    client.get(f"/ui/projects/{name}/glossary/terms")         # fragment
    assert called["n"] == 0                                   # Gate B1: zero on render
    client.post(f"/ui/projects/{name}/glossary/candidates/{_cid(client, name)}/suggest")
    assert called["n"] == 1                                   # only on explicit POST


def test_suggest_response_leaks_no_secret_value(client: TestClient, monkeypatch) -> None:
    name = _name(client)
    cid = _cid(client, name)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-SECRET-should-never-render")
    monkeypatch.setattr(
        ui_admin, "suggest_glossary_target",
        lambda *a, **k: GlossarySuggestion("Hero", "deepseek", "deepseek-chat", 1, 1),
    )
    r = client.post(f"/ui/projects/{name}/glossary/candidates/{cid}/suggest")
    assert "sk-SECRET-should-never-render" not in r.text
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/api/test_ui_glossary_suggest.py -v`
Expected: FAIL — endpoint 404 / `suggest_glossary_target` not importable from `ui_admin`.

- [ ] **Step 3: Implement the endpoint**

```python
# src/weaver/api/routers/ui_admin.py
# add import near the other glossary service imports:
from weaver.services.glossary_suggestion import suggest_glossary_target

# add the endpoint after glossary_candidate_action():
@router.post(
    "/ui/projects/{name}/glossary/candidates/{candidate_id}/suggest",
    response_class=HTMLResponse,
)
def glossary_candidate_suggest(
    name: str, candidate_id: int, request: Request
) -> HTMLResponse:
    """On-demand AI target suggestion for one candidate (explicit click only).

    Renders the candidate edit-form fragment with the target pre-filled + a cost line.
    A provider is called ONLY here (never on render — Gate B1). Failures are shown in
    the fragment; the input is left empty (never a silent/garbage fill).
    """
    base = _base_dir(request)
    ctx: dict[str, object] = {"name": name, "candidate_id": candidate_id}
    try:
        suggestion = suggest_glossary_target(
            _project_toml(request, name), candidate_id, cwd=base
        )
    except WeaverError as exc:
        ctx["error"] = str(exc)
        return templates.TemplateResponse(request, "partials/_glossary_candidate_edit.html", ctx)
    ctx["suggestion"] = suggestion
    return templates.TemplateResponse(request, "partials/_glossary_candidate_edit.html", ctx)
```

Note: `WeaverError` is already imported in `ui_admin.py`; `ProviderUnavailable`/`GlossarySuggestionError` are subclasses, so both map to the in-fragment error path. The template (Task 8) renders `~{{ (in or 0) + (out or 0) }} tokens`.

- [ ] **Step 4: Create the edit-form fragment so the router can render (see Task 8 Step 3), then run**

Run: `uv run pytest tests/unit/api/test_ui_glossary_suggest.py -v`
Expected: PASS once Task 8's partial exists. (If running Task 7 before Task 8, create the partial now from Task 8 Step 3.)

- [ ] **Step 5: Commit**

```bash
git add src/weaver/api/routers/ui_admin.py tests/unit/api/test_ui_glossary_suggest.py
git commit -m "feat(glossary): POST suggest endpoint (Gate B1, visible failure, no secret leak)"
```

---

## Task 8: Templates — edit-form slot + Suggest button

**Files:**
- Create: `src/weaver/api/templates/partials/_glossary_candidate_edit.html`
- Modify: `src/weaver/api/templates/partials/_glossary_candidates.html`
- Test: `tests/unit/api/test_ui_glossary.py` (extend)

- [ ] **Step 1: Write the failing UI tests**

```python
# tests/unit/api/test_ui_glossary.py  (append)
def test_candidate_row_has_suggest_button_and_edit_slot(gloss_client: TestClient) -> None:
    name = _name(gloss_client)
    page = gloss_client.get(f"/ui/projects/{name}/glossary").text
    assert "Suggest with AI" in page
    assert "(LLM call)" in page                      # cost visible BEFORE click (gate 6a)
    assert 'id="cand-edit-' in page                  # swappable edit slot
    assert "/glossary/candidates/" in page and "/suggest" in page
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/api/test_ui_glossary.py::test_candidate_row_has_suggest_button_and_edit_slot -v`
Expected: FAIL — markers absent.

- [ ] **Step 3: Create the edit-form partial**

```html
<!-- src/weaver/api/templates/partials/_glossary_candidate_edit.html -->
{# Swappable edit-form slot for one candidate. Rendered inline in the candidates
   table (no suggestion yet) and as the POST .../suggest response (target pre-filled
   + cost line, or an error). The Save & approve form is unchanged — only its input
   value and an optional meta line differ. #}
<div id="cand-edit-{{ candidate_id }}">
  {% if error %}<p class="cand-error error" role="alert">⚠ {{ error }}</p>{% endif %}
  <form class="row-form" hx-post="/ui/projects/{{ name }}/glossary/candidates/{{ candidate_id }}/edit"
        hx-swap="none" hx-disabled-elt="find button">
    <input name="target" value="{{ suggestion.target if suggestion else '' }}"
           placeholder="target (EN)" aria-label="Target (English)">
    <button type="submit" data-gc-action="edit">Save &amp; approve</button>
  </form>
  <button type="button" class="link-btn"
          hx-post="/ui/projects/{{ name }}/glossary/candidates/{{ candidate_id }}/suggest"
          hx-target="#cand-edit-{{ candidate_id }}" hx-swap="innerHTML"
          aria-label="Suggest a target with AI for this term">Suggest with AI <span class="hint">(LLM call)</span></button>
  {% if suggestion %}
  <p class="meta" aria-live="polite">via {{ suggestion.provider }} · {{ suggestion.model }} ·
    ~{{ (suggestion.input_tokens or 0) + (suggestion.output_tokens or 0) }} tokens</p>
  {% endif %}
  <p class="hint">Fills the editable target. You still Save &amp; approve.</p>
</div>
```

- [ ] **Step 4: Wire the partial into the candidates table (replace the inline edit form)**

In `src/weaver/api/templates/partials/_glossary_candidates.html`, replace the target `<td>` body (the `row-form` for edit + its `<p class="hint">`) with an include that passes the row's id:

```html
        <td>
          {% with candidate_id = c.id, suggestion = none, error = none %}
            {% include "partials/_glossary_candidate_edit.html" %}
          {% endwith %}
        </td>
```

(Keep the existing `<td>` for review pills — approve/reject — unchanged. `name` is already in
the candidates context.)

- [ ] **Step 5: Run to verify UI tests pass + existing candidate tests still pass**

Run: `uv run pytest tests/unit/api/test_ui_glossary.py tests/unit/api/test_ui_glossary_suggest.py -v`
Expected: PASS. (`test_candidate_edit_204_then_term_appears_in_terms_fragment` still passes — the edit form action/markup is preserved.)

- [ ] **Step 6: Commit**

```bash
git add src/weaver/api/templates/partials/_glossary_candidate_edit.html \
  src/weaver/api/templates/partials/_glossary_candidates.html tests/unit/api/test_ui_glossary.py
git commit -m "feat(glossary): Suggest-with-AI button + editable target slot per candidate"
```

---

## Task 9: Docs sync + final gate

**Files:**
- Modify: `CLAUDE.md` (§2 — add Sprint R), `AGENTS.md` (mirror), `docs/DECISIONS.md` (index ADR 014)
- Modify: `docs/PROVIDER_AND_MODEL_CONFIG.md` (note: suggestion uses the configured provider; no default)

- [ ] **Step 1: Update docs**

- `docs/DECISIONS.md`: add a row/line for ADR `014` (provider `complete()` primitive + glossary suggestion).
- `CLAUDE.md` §2: add a Sprint R line (status, scope, non-goals, ADR 014). Mirror into `AGENTS.md`.
- `docs/PROVIDER_AND_MODEL_CONFIG.md`: one paragraph — the glossary AI suggestion calls **the configured `[provider]`** (no hidden default; `custom` supported via `base_url`+`api_key_env`).

- [ ] **Step 2: Run the full gate**

```bash
uv run ruff check src tests
uv run ruff format --check src
uv run pyright src/weaver tests
uv run pytest -q
```

Expected: ruff clean; format clean; pyright `0 errors`; full suite green (prior 1379 passed + the
new provider/service/router/UI tests, 4 skipped).

- [ ] **Step 3: Targeted gate assertions (spec acceptance)**

```bash
# Gate B1 + secret-grep + validation + provider primitive
uv run pytest tests/unit/api/test_ui_glossary_suggest.py \
  tests/unit/services/test_glossary_suggestion.py \
  tests/unit/providers/test_fake.py tests/unit/providers/test_deepseek.py \
  tests/unit/providers/test_gemini.py tests/unit/providers/test_ollama.py \
  tests/unit/providers/test_prompts.py -v
```

Expected: all pass — Gate B1 (zero provider calls on render), failure-visible, no-secret-leak,
strict-validation rejections, deterministic fake, json-mode-error-visible.

- [ ] **Step 4: Commit + write handoff note (§8)**

```bash
git add CLAUDE.md AGENTS.md docs/DECISIONS.md docs/PROVIDER_AND_MODEL_CONFIG.md
git commit -m "docs(glossary-ai): record Sprint R + ADR 014; provider-config note"
```

Handoff: surfaces touched, gate evidence (paste test counts), known gaps (gemini/ollama
`complete()` exercised only via mocked clients — live runs are manual), next step (open the
Sprint R PR once #2/#3 merges; rebase onto `main`).

---

## Self-Review

**Spec coverage:** §2 provider-flexibility → Task 6 (build_provider, no default) + ADR. §3.1
`complete()` → Tasks 1–4. §3.2 service → Task 6. §3.3 prompt → Task 5. §3.4 UI → Tasks 7–8.
§4 error handling → Task 6 (`_parse_target`, healthcheck) + Task 7 (in-fragment error). §5
validation → Task 6 parametrized rejections. §6 Gate B1 → Task 7 spy test. §7 six gates →
Tasks 6–8 + tests. §8 testing → every task TDD. §9 non-goals → no migration/persistence/batch
(none added). §10 surfaces → Tasks 1–9. Custom/json-mode visibility (user note) → Task 2 test.
Branch hygiene → Task 0.

**Placeholder scan:** none — every code/test step shows full content.

**Type consistency:** `Completion(text, input_tokens, output_tokens, raw_response)` used
consistently (Tasks 1–4, 6). `GlossarySuggestion(target, provider, model, input_tokens,
output_tokens)` consistent (Tasks 6–8). `complete(prompt, *, system, max_output_tokens)`
signature identical across base + 4 impls + stub. `render_glossary_suggestion_prompt(source,
category, examples, source_lang, target_lang)` consistent (Tasks 5–6). `suggest_glossary_target(
project_toml, candidate_id, *, cwd, provider)` consistent (Tasks 6–7).

**Note for executor:** Task 7 and Task 8 are mutually dependent (router renders the Task 8
partial). If executing strictly in order, create the partial (Task 8 Step 3) before running
Task 7 Step 4 — flagged in Task 7 Step 4.
