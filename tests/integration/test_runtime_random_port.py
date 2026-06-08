"""Sprint G4 — port-agnostic UI proof.

Boots Uvicorn on ``WEAVER_PORT=0`` (random) in a background thread, then
hits ``/ui`` and an HTMX endpoint. Proves the cockpit is host/port-agnostic
(no template hardcodes a port or scheme — see ``docs/SPRINT_G_RUNTIME_AUDIT.md``
§A.4).

Also includes a static-grep guard: any hx-* attribute pointing at an absolute
``http://`` URL is rejected at test time, so a future template change can't
silently break sidecar mode.
"""

from __future__ import annotations

import socket
import threading
import time
from contextlib import closing
from pathlib import Path

import httpx
import pytest
import uvicorn

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "src" / "weaver" / "api" / "templates"


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
