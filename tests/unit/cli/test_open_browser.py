"""Tests for opening the cockpit URL in the real default browser."""

from __future__ import annotations

import webbrowser

import pytest

from weaver.cli.open_browser import open_in_external_browser


class _FakeController:
    def __init__(self, *, succeed: bool) -> None:
        self.succeed = succeed
        self.opened: list[str] = []
        self.browser_env_during_open: str | None = "unset"

    def open(self, url: str, new: int = 0, autoraise: bool = True) -> bool:
        import os

        self.browser_env_during_open = os.environ.get("BROWSER")
        self.opened.append(url)
        return self.succeed


def test_opens_via_default_controller(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeController(succeed=True)
    monkeypatch.setattr(webbrowser, "get", lambda name=None: fake)

    assert open_in_external_browser("http://127.0.0.1:8765") is True
    assert fake.opened == ["http://127.0.0.1:8765"]


def test_editor_browser_env_is_bypassed_then_restored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate VS Code injecting its Simple-Browser handler.
    monkeypatch.setenv("BROWSER", "code --open-url")
    fake = _FakeController(succeed=True)
    monkeypatch.setattr(webbrowser, "get", lambda name=None: fake)

    open_in_external_browser("http://127.0.0.1:8765")

    import os

    # During the open call the override must be gone...
    assert fake.browser_env_during_open is None
    # ...and restored afterwards so we don't mutate the process environment.
    assert os.environ["BROWSER"] == "code --open-url"


def test_returns_false_when_no_browser_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(name: str | None = None) -> object:
        raise webbrowser.Error("no browser")

    monkeypatch.setattr(webbrowser, "get", _raise)
    assert open_in_external_browser("http://127.0.0.1:8765") is False


def test_never_raises_on_controller_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Boom:
        def open(self, url: str, new: int = 0, autoraise: bool = True) -> bool:
            raise webbrowser.Error("boom")

    monkeypatch.setattr(webbrowser, "get", lambda name=None: _Boom())
    # Must swallow the controller error and report failure, not propagate.
    assert open_in_external_browser("http://127.0.0.1:8765") is False
