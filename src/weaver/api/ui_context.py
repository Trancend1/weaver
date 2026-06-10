"""Presentation-only context helpers for the server-rendered UI shell.

These helpers collect layout metadata for Jinja templates. They intentionally
avoid business decisions: routes still decide which services to call and how to
handle errors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request

from weaver.api.jobs import JobRegistry
from weaver.errors import WeaverError
from weaver.services.project_discovery import find_project
from weaver.services.project_tree import project_tree


def _base_dir(request: Request) -> Path:
    return request.app.state.base_dir  # type: ignore[no-any-return]


def _jobs(request: Request) -> JobRegistry | None:
    return getattr(request.app.state, "jobs", None)


def global_layout(active_nav: str) -> dict[str, Any]:
    return {"layout_mode": "global", "active_nav": active_nav}


def ws_hub_layout(active_nav: str = "projects") -> dict[str, Any]:
    """Layout context for the global Workspace hub shell (ws-hub mode)."""
    return {"layout_mode": "ws-hub", "active_nav": active_nav}


def project_layout(
    request: Request,
    name: str,
    *,
    active_nav: str,
    sidebar_tree: object | None = None,
) -> dict[str, Any]:
    return _project_context(
        request,
        name,
        layout_mode="project",
        active_nav=active_nav,
        sidebar_tree=sidebar_tree,
    )


def workspace_layout(
    request: Request,
    name: str,
    *,
    active_nav: str = "workspace",
    active_chapter_id: str | None = None,
    sidebar_tree: object | None = None,
) -> dict[str, Any]:
    ctx = _project_context(
        request,
        name,
        layout_mode="workspace",
        active_nav=active_nav,
        sidebar_tree=sidebar_tree,
    )
    ctx["active_chapter_id"] = active_chapter_id
    return ctx


def _project_context(
    request: Request,
    name: str,
    *,
    layout_mode: str,
    active_nav: str,
    sidebar_tree: object | None,
) -> dict[str, Any]:
    base = _base_dir(request)
    tree = sidebar_tree
    sidebar_error = None
    if tree is None:
        dp = find_project(base, name)
        if dp is None:
            sidebar_error = f"No project named {name!r}."
        elif dp.error:
            sidebar_error = dp.error
        else:
            try:
                tree = project_tree(dp.project_toml, cwd=base, jobs=_jobs(request))
            except WeaverError as exc:
                sidebar_error = str(exc)
    return {
        "layout_mode": layout_mode,
        "active_nav": active_nav,
        "project_name": name,
        "sidebar_tree": tree,
        "sidebar_error": sidebar_error,
    }
