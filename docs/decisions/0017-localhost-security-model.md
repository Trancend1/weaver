# 0017: Local Web Cockpit Security Model

Date: 2026-05-29
Status: accepted

## Context

The Phase 12 web cockpit (ADR `0016`) exposes project state, configuration, and a file browser over HTTP. A web surface that reads the local filesystem and writes config is a new attack surface for a tool that was previously CLI-only. Weaver is a single-user local desktop tool, not a hosted service — the threat model is "do not accidentally expose the user's machine or leak secrets," not "defend a public endpoint."

The existing rule (CLAUDE.md §4.2) is absolute: **API keys via env vars only, never config files, never logged.**

## Decision

The cockpit server enforces:

- **Bind `127.0.0.1` only.** Never `0.0.0.0`. No remote access, no LAN exposure. Port default `8765`, overridable via `weaver serve --port`.
- **No authentication.** Single-user local tool; auth would add friction with no threat it mitigates on loopback.
- **File browser sandbox.** The `/api/browse` directory listing is rooted at `--books-dir` (default: current working directory). Paths are resolved and validated to stay within the root; `..` traversal escapes are rejected. Listing is filtered to directories and `.epub` files.
- **Upload limits.** Uploads accept `.epub` only, with a size cap. Uploaded files are copied to `.weaver/_uploads/` staging (decision D2), then `init` runs from there — never executed or extracted to arbitrary paths.
- **Secret handling.** API keys are never written to `project.toml` or `~/.weaver/config.toml` (ADR `0018` writes only `type`/`model`/`base_url`). Keys are never rendered to a page, included in an SSE event, or written to a request/response log. Provider healthcheck/config UI shows only whether an env var is *present*, never its value.

## Consequences

Easier: loopback bind + sandbox keeps the blast radius to the local user with near-zero config. Reusing the env-only key rule means the web layer never touches secrets.

Harder: no remote access by design — users wanting access from another device must use SSH port-forwarding themselves (out of scope). The file-browser sandbox must be tested against traversal payloads. Any future feature that would render or transmit a key must supersede this ADR.
