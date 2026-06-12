"""Tests for the on-demand AI glossary-target suggestion service (Sprint R)."""

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

    def __init__(
        self, *, text: str = "", exc: Exception | None = None, healthy: bool = True
    ) -> None:
        self._text, self._exc, self._healthy = text, exc, healthy
        self.last_prompt: str | None = None

    def translate(self, request):  # pragma: no cover - unused
        raise NotImplementedError

    def healthcheck(self) -> ProviderStatus:
        return ProviderStatus(
            self._healthy, self.name, "stub-1", None if self._healthy else "down", 1
        )

    def complete(self, prompt, *, system=None, max_output_tokens):
        self.last_prompt = prompt
        if self._exc:
            raise self._exc
        return Completion(
            text=self._text, input_tokens=5, output_tokens=2, raw_response=self._text
        )


def _candidate_source(project_toml: Path) -> tuple[int, str]:
    with open_glossary_review_session(project_toml) as session:
        cand = session.next_pending()
        assert cand is not None
        return cand.id, cand.source


def test_suggest_returns_grounded_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    cid, source = _candidate_source(init.project_toml)
    stub = _StubProvider(text='{"target": "Demon King"}')

    out = suggest_glossary_target(init.project_toml, cid, cwd=tmp_path, provider=stub)

    assert isinstance(out, GlossarySuggestion)
    assert out.target == "Demon King"
    assert out.provider == "stub" and out.model == "stub-1"
    assert (out.input_tokens, out.output_tokens) == (5, 2)
    # grounded: the prompt the provider saw contains the candidate's source term
    assert source in (stub.last_prompt or "")


def test_suggest_unavailable_provider_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    cid, _ = _candidate_source(init.project_toml)
    with pytest.raises(ProviderUnavailable):
        suggest_glossary_target(
            init.project_toml, cid, cwd=tmp_path, provider=_StubProvider(healthy=False)
        )


@pytest.mark.parametrize(
    "bad",
    [
        "",  # empty completion
        "not json at all",  # non-JSON
        '{"nope": "x"}',  # missing target key
        '{"target": ""}',  # empty target
        '{"target": "line1\\nline2"}',  # multiline
        '{"target": "' + "x" * 200 + '"}',  # over-length
        '{"target": "This is a full sentence that explains the term."}',  # sentence-shaped
    ],
)
def test_suggest_rejects_unusable_output(tmp_path: Path, monkeypatch, bad: str) -> None:
    monkeypatch.chdir(tmp_path)
    init = initialize_project(FIXTURE_EPUB)
    cid, _ = _candidate_source(init.project_toml)
    with pytest.raises(GlossarySuggestionError):
        suggest_glossary_target(
            init.project_toml, cid, cwd=tmp_path, provider=_StubProvider(text=bad)
        )
