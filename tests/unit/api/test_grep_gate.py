"""Grep-gate: prevent new raw-SQL / writable-open / silent-failure patterns.

These tests are exact-count pins.  Q2 removes the existing occurrences; after
Q2 the expected counts drop to zero and new occurrences are rejected.
"""

from __future__ import annotations

from pathlib import Path

ROUTERS_DIR = Path(__file__).parents[3] / "src" / "weaver" / "api" / "routers"


ROUTER_SOURCE = ""
if ROUTERS_DIR.is_dir():
    ROUTER_SOURCE = "\n".join(
        f.read_text(encoding="utf-8") for f in sorted(ROUTERS_DIR.glob("*.py"))
    )


# Current counts as of Q1 (2026-06-10).  Increase = regression.
# Q2 will drive these to zero.
EXPECTED_CONN_EXECUTE = 3  # ui.py
EXPECTED_CONNECT_DATABASE = 12  # ui.py (8) + jobs.py (2) + candidates.py (2)
EXPECTED_SUPPRESS_HTTP = 5  # ui.py
EXPECTED_EXCEPT_WEAVER_PASS = 2  # ui.py:1074, ui.py:1342


def _count_substring(text: str, needle: str) -> int:
    count = 0
    pos = 0
    while True:
        idx = text.find(needle, pos)
        if idx == -1:
            break
        count += 1
        pos = idx + 1
    return count


def test_no_new_conn_execute_in_routers() -> None:
    assert _count_substring(ROUTER_SOURCE, "conn.execute(") <= EXPECTED_CONN_EXECUTE


def test_no_new_connect_database_in_routers() -> None:
    assert _count_substring(ROUTER_SOURCE, "connect_database(") <= EXPECTED_CONNECT_DATABASE


def test_no_new_suppress_httpexception_in_routers() -> None:
    assert _count_substring(ROUTER_SOURCE, "suppress(HTTPException)") <= EXPECTED_SUPPRESS_HTTP


def test_no_new_except_weaver_pass_in_routers() -> None:
    # Count two-line "except WeaverError:\n        pass" combos
    lines = ROUTER_SOURCE.splitlines()
    combo_count = sum(
        1
        for i in range(len(lines) - 1)
        if "except WeaverError:" in lines[i] and lines[i + 1].strip() == "pass"
    )
    assert combo_count <= EXPECTED_EXCEPT_WEAVER_PASS
