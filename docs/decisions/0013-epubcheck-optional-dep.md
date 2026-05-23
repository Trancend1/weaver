# 0013: EPUBCheck as Optional Subprocess Dependency

Date: 2026-05-23
Status: accepted

## Context

`weaver export --mode epub` produces an EPUB, but Weaver has no way to verify the output is structurally valid. EPUBCheck is the W3C-maintained reference validator. It is a Java JAR, not a Python package, so it cannot be declared in `pyproject.toml`. Many translators will not have Java installed; the feature must degrade gracefully.

## Decision

Add `--epub` flag to `weaver validate`. When set, the command:

1. Derives the expected EPUB path from `project.toml`: `{output_dir}/epub/{source_stem}.translated.epub`.
2. If the file does not exist, prints "Run `weaver export --mode epub` first." and exits 1.
3. Calls `run_epubcheck(epub_path)` from `services/epubcheck.py`.

`find_epubcheck_jar()` checks: `EPUBCHECK_JAR` env var → `~/.local/share/epubcheck/epubcheck.jar` → `/usr/local/share/epubcheck/epubcheck.jar` → `%LOCALAPPDATA%\epubcheck\epubcheck.jar`. If no jar is found, `run_epubcheck` returns `EpubCheckResult(epubcheck_available=False)` — the command prints a warning and exits 0 (graceful).

If Java is not on `PATH`, `subprocess.run` raises `FileNotFoundError`, which is caught and re-raised as `ConfigError("EPUBCheck requires Java 8+.")` (exit 7).

Output lines containing `ERROR` (case-insensitive) → `errors` tuple; `WARNING` → `warnings` tuple.

No Python dep is added. EPUBCheck is discovered and invoked at runtime only.

## Consequences

Easier: structured EPUB validation available without changing the tool's install footprint. Graceful degradation means CI (no Java) never fails unexpectedly.

Harder: users must install Java and download the EPUBCheck JAR separately. The `EPUBCHECK_JAR` env var or a known install path must be set. Output parsing is heuristic (line-contains) rather than structured — may miss edge cases if EPUBCheck changes its output format.
