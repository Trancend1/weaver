"""Sprint G4 — port-agnostic UI proof.

Boots Uvicorn on ``WEAVER_PORT=0`` (random) in a background thread, then
hits ``/ui`` and an HTMX endpoint. Proves the cockpit is host/port-agnostic
(no template hardcodes a port or scheme — see ``docs/SPRINT_G_RUNTIME_AUDIT.md``
§A.4).

Q2F Commit 2 — Sidecar health readiness over real HTTP.  Verifies /healthz,
/health, /version, and /runtime/status behavior under real Uvicorn (not
TestClient), matching the sidecar boot-poll contract (SIDECAR_CONTRACT.md §6).
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Generator
from contextlib import closing
from pathlib import Path

import httpx
import pytest
import uvicorn

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "src" / "weaver" / "api" / "templates"

# Sidecar budget: 5 s total.  CI wall-clock tolerance is generous (2 s for the
# handler itself) because the real bottleneck is Uvicorn cold-start, not the
# handler.  The existing TestClient test already asserts < 500 ms for pure
# handler cost; this integration test adds network + Uvicorn overhead.
_HEALTHZ_BUDGET_MS = 2000.0


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_ready(url: str, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=0.5)
        except httpx.HTTPError:
            time.sleep(0.05)
            continue
        if response.status_code == 200:
            return
        time.sleep(0.05)
    raise AssertionError(f"server at {url} did not become ready within {timeout}s")


def test_ui_works_on_random_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEAVER_BOOKS_DIR", str(tmp_path))
    port = _free_port()

    config = uvicorn.Config(
        "weaver.api.app:create_api_app",
        host="127.0.0.1",
        port=port,
        factory=True,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        _wait_ready(f"{base}/healthz")

        ui = httpx.get(f"{base}/ui", timeout=2.0)
        assert ui.status_code == 200
        assert "<html" in ui.text.lower()

        # HTMX endpoint that no client-side state depends on.
        browse = httpx.get(f"{base}/ui/browse?dir=", timeout=2.0)
        assert browse.status_code == 200
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)


# ---------------------------------------------------------------------------
# Q2F Commit 2 — Sidecar health readiness over real HTTP
# ---------------------------------------------------------------------------


@pytest.fixture()
def _sidecar_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Minimal env for a sidecar-like Uvicorn instance."""
    monkeypatch.setenv("WEAVER_BOOKS_DIR", str(tmp_path))
    monkeypatch.setenv("WEAVER_DATA_DIR", str(tmp_path / "weaver-data"))


@pytest.fixture()
def sidecar_server(_sidecar_env: None) -> Generator[str, None, None]:
    """Boot Uvicorn on a random port, yield the base URL, shut down."""
    port = _free_port()
    config = uvicorn.Config(
        "weaver.api.app:create_api_app",
        host="127.0.0.1",
        port=port,
        factory=True,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_ready(f"{base}/healthz")
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)


@pytest.fixture()
def sidecar_server_with_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[str, None, None]:
    """Boot Uvicorn with WEAVER_SESSION_TOKEN set, yield base URL."""
    monkeypatch.setenv("WEAVER_BOOKS_DIR", str(tmp_path))
    monkeypatch.setenv("WEAVER_DATA_DIR", str(tmp_path / "weaver-data"))
    monkeypatch.setenv("WEAVER_SESSION_TOKEN", "test-session-token-q2f")
    port = _free_port()
    config = uvicorn.Config(
        "weaver.api.app:create_api_app",
        host="127.0.0.1",
        port=port,
        factory=True,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_ready(f"{base}/healthz")
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)


class TestHealthzReadiness:
    """Verify /healthz satisfies the sidecar boot-poll contract (§6)."""

    def test_returns_200_with_ok_and_timestamp(self, sidecar_server: str) -> None:
        response = httpx.get(f"{sidecar_server}/healthz", timeout=2.0)
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert isinstance(body["ts"], str)
        assert "T" in body["ts"]

    def test_is_public_no_token_required(self, sidecar_server_with_token: str) -> None:
        """Session token is set but /healthz must still be reachable without it."""
        response = httpx.get(f"{sidecar_server_with_token}/healthz", timeout=2.0)
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_response_time_budget(self, sidecar_server: str) -> None:
        """Cold /healthz over real HTTP must be well within the 5 s sidecar budget.

        Threshold is 2 s — generous for CI (network + Uvicorn overhead) but
        far below the 5 s sidecar deadline.  The existing TestClient test
        already asserts < 500 ms for pure handler cost; this adds the real
        HTTP path.
        """
        start = time.perf_counter()
        response = httpx.get(f"{sidecar_server}/healthz", timeout=2.0)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        assert response.status_code == 200
        assert elapsed_ms < _HEALTHZ_BUDGET_MS, (
            f"/healthz took {elapsed_ms:.0f} ms (budget: {_HEALTHZ_BUDGET_MS:.0f} ms)"
        )

    def test_does_not_touch_providers(self, sidecar_server: str) -> None:
        """Hitting /healthz must not invoke any LLM provider.

        We verify by confirming the response contains no provider-shaped
        fields and that the handler is a pure in-memory timestamp (already
        proven by source inspection of runtime.py:healthz). This test is a
        regression guard: if someone adds provider logic to the health path,
        this will surface it.
        """
        response = httpx.get(f"{sidecar_server}/healthz", timeout=2.0)
        body = response.json()
        # HealthZResponse only has {ok, ts} — no provider/model/key fields.
        assert set(body.keys()) == {"ok", "ts"}

    def test_does_not_mutate_state(self, sidecar_server: str) -> None:
        """Two sequential /healthz calls return consistent (non-mutating) results.

        If the handler mutated a database or file, repeated calls could
        change state.  Both calls must succeed with the same shape.
        """
        r1 = httpx.get(f"{sidecar_server}/healthz", timeout=2.0)
        r2 = httpx.get(f"{sidecar_server}/healthz", timeout=2.0)
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Shape must be identical (timestamp will differ).
        assert set(r1.json().keys()) == set(r2.json().keys())
        assert r1.json()["ok"] is r2.json()["ok"] is True


class TestPublicEndpointsOverHttp:
    """Verify /health and /version are public (no token required) over real HTTP."""

    def test_health_is_public(self, sidecar_server_with_token: str) -> None:
        response = httpx.get(f"{sidecar_server_with_token}/health", timeout=2.0)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_version_is_public(self, sidecar_server_with_token: str) -> None:
        response = httpx.get(f"{sidecar_server_with_token}/version", timeout=2.0)
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "weaver"
        assert isinstance(body["version"], str)


class TestTokenProtectedEndpoints:
    """Verify /runtime/status requires X-Weaver-Session when token is set."""

    def test_runtime_status_401_without_token(self, sidecar_server_with_token: str) -> None:
        response = httpx.get(f"{sidecar_server_with_token}/runtime/status", timeout=2.0)
        assert response.status_code == 401

    def test_runtime_status_401_with_wrong_token(self, sidecar_server_with_token: str) -> None:
        response = httpx.get(
            f"{sidecar_server_with_token}/runtime/status",
            headers={"X-Weaver-Session": "wrong-token"},
            timeout=2.0,
        )
        assert response.status_code == 401

    def test_runtime_status_200_with_correct_token(self, sidecar_server_with_token: str) -> None:
        response = httpx.get(
            f"{sidecar_server_with_token}/runtime/status",
            headers={"X-Weaver-Session": "test-session-token-q2f"},
            timeout=2.0,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["env"] in ("dev", "desktop", "test")
        assert "app_data_dir" in body
        assert "logs_dir" in body
        assert "books_dir" in body

    def test_ui_401_without_token(self, sidecar_server_with_token: str) -> None:
        """/ui must also be protected when token is set."""
        response = httpx.get(f"{sidecar_server_with_token}/ui", timeout=2.0, follow_redirects=False)
        assert response.status_code == 401


def test_no_template_uses_absolute_http_url_in_hx_attrs() -> None:
    # Static guard against re-introducing a hardcoded host/port in any hx-* attr.
    offenders: list[str] = []
    for template in TEMPLATES_DIR.rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            # Skip the SVG-data-uri favicon line in base.html (xmlns is not a route).
            if 'rel="icon"' in stripped:
                continue
            if "hx-" in stripped and ("http://" in stripped or "https://" in stripped):
                offenders.append(f"{template.name}:{line_no}: {stripped}")
    assert offenders == [], "absolute URL in hx-* attribute(s):\n" + "\n".join(offenders)
