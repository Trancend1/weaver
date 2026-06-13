<!-- Generated: 2026-06-13 | Files scanned: src/weaver/api/templates/, src/weaver/api/routers/ui*.py, src/weaver/api/static/app.css, remote origin/main:docs/{WEB_WORKFLOW,SECURITY_AND_PERFORMANCE,INSTALL_DESKTOP}.md | Token estimate: ~900 -->
# Frontend

## Stack
Server-rendered Jinja2 + HTMX. Vendored `htmx.min.js` (no CDN). No Node, no SPA, no frontend build step. Design tokens single-sourced in `src/weaver/api/static/app.css :root`. Tauri desktop wraps the same `/ui` cockpit in WebView2; it does not create a separate frontend.

## Template Tree (55 templates under `src/weaver/api/templates/`)
```txt
base.html
+- dashboard.html
+- project.html
+- project_analytics.html
+- project_exports.html
+- workspace.html              (chapter editor; #seg-{id} swap target)
+- epub_preview.html
+- reading_preview.html
+- candidates.html
+- character_drafts.html
+- glossary.html
+- qa.html
+- review_queue.html
+- jobs_list.html
+- job_detail.html
+- queue_hub.html
+- resources_hub.html
+- providers_hub.html
+- exports_hub.html
+- new.html
+- characters.html
+- memory.html
+- error.html / not_found.html

partials/
  _workspace_grid.html, _workspace_sidebar.html, _workspace_context.html
  _segment.html, _segment_statusline.html, _segment_list.html
  _browse.html, _tree.html, _snapshot.html, _sidebar.html, _sidebar_item.html
  _qa_summary.html, _qa_issues.html, _qa_tree_badges.html
  _glossary_terms.html, _glossary_candidates.html, _glossary_candidate_edit.html
  _glossary_diff.html, _glossary_examples.html, _secrets.html
  _candidates_list.html, _drafts_list.html, _export_preflight.html,
  _export_gate_blocked.html, _export_job.html
  _history.html, _memory.html, _import_error.html, _job_error.html, _job.html,
  _job_with_grid.html, _provider_status.html, _icons.html,
  _empty_state.html, _page_header.html
```

## Stable HTMX Hooks (do not rename/remove)
- Global: `#tree`, `#ws-grid`, `#job-panel`, `#export-panel`, `#browser`, `#selected_source`, `#source_path`.
- QA: `#qa-badge-status`, `#qa-issues`, `qa-badge-vol-*`, `qa-badge-ch-*`.
- Workspace: `#seg-{id}` (full segment row swap), `#seg-statusline-{id}` (not a swap target), `#seg-{id}-history`, `#seg-{id}-candidates`, `#seg-{id}-gen-loader`.

## Page Layout Modes (`api/ui_context.py`)
- `global` (topbar only): `/ui`, `/ui/new`, hubs (including `/ui/providers` for provider/model + secret config).
- `project` (topbar + 264px sidebar): project, glossary, characters, memory, quality.
- `workspace` (topbar + 56px icon rail): chapter editor.

## Cockpit Workflow
```txt
create/browse/import -> project overview -> workspace translate/edit/review
  -> glossary/characters/TM resources -> QA report/preflight -> export
cross-project hubs: queue/resources/providers/exports (read-only index paths)
```
- Web cockpit drives the same services as CLI; it is not a second backend.
- Long-running actions use JobRegistry + SSE; job panels surface progress/failure.
- Provider/AI actions require explicit POST; no background provider calls from render.

## Workspace Rules
- Save form POSTs return `_segment.html` swapped into `#seg-{id}`.
- Review pills update optimistically in `workspace.html` (`applyReview`) and POST with `hx-swap="none"`; failed POST surfaces via `review-save-failed`.
- Review labels/colours come from `api/status_labels.py` (single source).
- Do not recreate deleted preview-modal routes/buttons or removed workspace header/sidebar clutter.

## UX / Security / Performance Constraints
- Render at 390px+, keyboard navigable; hover / `:active` / `:focus-visible` / `:disabled` defined.
- States: empty (`_empty_state.html`), error (`.error role="alert"`), loading (HTMX indicator + native `<progress>`).
- Motion <= 140 ms with `prefers-reduced-motion` honored.
- No toasts/`alert()`, no marketing AI language, no sparkles/chat UI.
- No secrets in rendered HTML, SSE payloads, logs, or config responses.
- Gate B1: hubs/render/list paths must not hash source files, migrate DBs, run QA, call providers, or reset jobs.

## Desktop Surface
- Windows WebView2 shell launches FastAPI sidecar, injects `X-Weaver-Session`, and shows crash screen with console tail/log path if backend start fails.
- App data/logs live under `%APPDATA%\Weaver\`; Python backend must still be on PATH in Sprint O baseline.

## Test Pins
- `tests/unit/api/test_ui_shell.py`, `test_ui_layout.py`, `test_ui_qa.py`, `test_ui_delete.py` pin user-facing strings + layout markers.
- Browser/manual checks should cover 390px responsive layout, keyboard navigation, HTMX swaps, failed POST visibility, and no secret rendering.
