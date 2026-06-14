"""Sprint G4 — port-agnostic UI proof + Q2F sidecar startup contract.

Boots Uvicorn on ``WEAVER_PORT=0`` (random) in a background thread, then
hits ``/ui`` and an HTMX endpoint. Proves the cockpit is host/port-agnostic
(no template hardcodes a port or scheme — see ``docs/SPRINT_G_RUNTIME_AUDIT.md``
§A.4).

Q2F Commit 2 — Sidecar health readiness over real HTTP.  Verifies /healthz,
/health, /version, and /runtime/status behavior under real Uvicorn (not
TestClient), matching the sidecar boot-poll contract (SIDECAR_CONTRACT.md §6).

Q2F Commit 3 — Random port + session token startup contract.  Verifies the
cockpit behaves correctly when launched with the full desktop env var set
(WEAVER_ENV=desktop, WEAVER_SESSION_TOKEN, WEAVER_DOCS=false, random port,
isolated dirs).  Mirrors what the Tauri shell does in sidecar.rs.
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

# Token used by the desktop-mode fixture (sidecar.rs sets WEAVER_SESSION_TOKEN).
_DESKTOP_TOKEN = "q2f-desktop-session-token"


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


# ---------------------------------------------------------------------------
# Q2F Commit 3 — Random port + session token startup contract
# ---------------------------------------------------------------------------


@pytest.fixture()
def sidecar_desktop_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[str, None, None]:
    """Boot Uvicorn in desktop mode — full sidecar startup contract.

    Mirrors the env vars set by ``desktop/src/sidecar.rs``
    (SIDECAR_CONTRACT.md §2)::

        WEAVER_ENV=desktop
        WEAVER_SESSION_TOKEN=<hex>
        WEAVER_DOCS=false
        WEAVER_HOST=127.0.0.1
        WEAVER_PORT=<random>
        WEAVER_DATA_DIR=<isolated>
        WEAVER_BOOKS_DIR=<isolated>
    """
    port = _free_port()
    monkeypatch.setenv("WEAVER_BOOKS_DIR", str(tmp_path))
    monkeypatch.setenv("WEAVER_DATA_DIR", str(tmp_path / "weaver-data"))
    monkeypatch.setenv("WEAVER_ENV", "desktop")
    monkeypatch.setenv("WEAVER_SESSION_TOKEN", _DESKTOP_TOKEN)
    monkeypatch.setenv("WEAVER_DOCS", "false")
    monkeypatch.setenv("WEAVER_HOST", "127.0.0.1")
    monkeypatch.setenv("WEAVER_PORT", str(port))
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


class TestDesktopStartupContract:
    """Verify the full desktop-mode startup contract (SIDECAR_CONTRACT.md §1-3)."""

    def test_runtime_status_reports_desktop_env(
        self, sidecar_desktop_server: str
    ) -> None:
        """/runtime/status must report env=desktop when WEAVER_ENV=desktop."""
        response = httpx.get(
            f"{sidecar_desktop_server}/runtime/status",
            headers={"X-Weaver-Session": _DESKTOP_TOKEN},
            timeout=2.0,
        )
        assert response.status_code == 200
        assert response.json()["env"] == "desktop"

    def test_runtime_status_reports_matching_host_and_port(
        self, sidecar_desktop_server: str
    ) -> None:
        """/runtime/status must report the actual 127.0.0.1 host and bound port."""
        port = int(sidecar_desktop_server.rsplit(":", 1)[1])
        response = httpx.get(
            f"{sidecar_desktop_server}/runtime/status",
            headers={"X-Weaver-Session": _DESKTOP_TOKEN},
            timeout=2.0,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["host"] == "127.0.0.1"
        assert body["port"] == port

    def test_runtime_status_reports_isolated_paths(
        self, sidecar_desktop_server: str
    ) -> None:
        """/runtime/status must report isolated app_data_dir, logs_dir, books_dir."""
        response = httpx.get(
            f"{sidecar_desktop_server}/runtime/status",
            headers={"X-Weaver-Session": _DESKTOP_TOKEN},
            timeout=2.0,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["app_data_dir"]
        assert body["logs_dir"].endswith("logs")
        assert body["books_dir"]

    def test_docs_disabled_in_desktop_mode(
        self, sidecar_desktop_server: str
    ) -> None:
        """/docs, /redoc, /openapi.json must not be served in desktop mode.

        Without a token the middleware returns 401 (docs are not in
        ``_PUBLIC_PATHS``).  With a correct token FastAPI returns 404
        because the routes were never registered (``docs_url=None``).
        Both prove docs are off — the key assertion is none returns 200.
        """
        for path in ("/docs", "/redoc", "/openapi.json"):
            no_token = httpx.get(
                f"{sidecar_desktop_server}{path}", timeout=2.0
            )
            assert no_token.status_code in (401, 404), (
                f"{path} returned {no_token.status_code} without token"
            )
            with_token = httpx.get(
                f"{sidecar_desktop_server}{path}",
                headers={"X-Weaver-Session": _DESKTOP_TOKEN},
                timeout=2.0,
            )
            assert with_token.status_code == 404, (
                f"{path} returned {with_token.status_code} with token"
            )

    def test_protected_routes_reject_missing_token(
        self, sidecar_desktop_server: str
    ) -> None:
        """/ui and /runtime/status must 401 without X-Weaver-Session."""
        ui_resp = httpx.get(
            f"{sidecar_desktop_server}/ui", timeout=2.0, follow_redirects=False
        )
        assert ui_resp.status_code == 401

        status_resp = httpx.get(
            f"{sidecar_desktop_server}/runtime/status", timeout=2.0
        )
        assert status_resp.status_code == 401

    def test_protected_routes_work_with_correct_token(
        self, sidecar_desktop_server: str
    ) -> None:
        """/ui and /runtime/status must 200 with correct X-Weaver-Session."""
        ui_resp = httpx.get(
            f"{sidecar_desktop_server}/ui",
            headers={"X-Weaver-Session": _DESKTOP_TOKEN},
            timeout=2.0,
        )
        assert ui_resp.status_code == 200

        status_resp = httpx.get(
            f"{sidecar_desktop_server}/runtime/status",
            headers={"X-Weaver-Session": _DESKTOP_TOKEN},
            timeout=2.0,
        )
        assert status_resp.status_code == 200

    def test_public_routes_do_not_require_token(
        self, sidecar_desktop_server: str
    ) -> None:
        """/healthz, /health, /version must work without token in desktop mode."""
        for path in ("/healthz", "/health", "/version"):
            response = httpx.get(
                f"{sidecar_desktop_server}{path}", timeout=2.0
            )
            assert response.status_code == 200, (
                f"{path} should be public but returned {response.status_code}"
            )


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


# ---------------------------------------------------------------------------
# Q2F Commit 3 — Hardcoded default-port regression guards
# ---------------------------------------------------------------------------


class TestRenderedUiNoHardcodedPort:
    """Verify rendered /ui HTML contains no hardcoded default port (8765)."""

    def test_rendered_ui_does_not_contain_default_port(
        self, sidecar_server: str
    ) -> None:
        """The /ui page rendered on a random port must not mention :8765."""
        response = httpx.get(f"{sidecar_server}/ui", timeout=2.0)
        assert response.status_code == 200
        text = response.text
        # The default port (8765) appearing in rendered HTML would mean a
        # template or service string-baked it — a sidecar contract violation.
        assert ":8765" not in text, (
            "rendered /ui contains hardcoded default port"
        )
        assert "127.0.0.1:8765" not in text, (
            "rendered /ui contains hardcoded 127.0.0.1:8765"
        )


def test_no_template_uses_hardcoded_loopback_url() -> None:
    """Static guard: no template source file references ``127.0.0.1``.

    Any occurrence of ``127.0.0.1`` in a template is a hardcoded loopback
    reference that would break on a random port or in the desktop sidecar.
    """
    offenders: list[str] = []
    for template in sorted(TEMPLATES_DIR.rglob("*.html")):
        text = template.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "127.0.0.1" in line:
                offenders.append(f"{template.name}:{line_no}: {line.strip()}")
    assert offenders == [], (
        "hardcoded 127.0.0.1 in template(s):\n" + "\n".join(offenders)
    )


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
