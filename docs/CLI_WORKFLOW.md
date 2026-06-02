# CLI Workflow

The CLI is the complete, scriptable surface. It stays wire-compatible across the reset (ADR 002) — the web cockpit drives the same services, never the reverse. Full command reference + flags + exit codes: [README.md](../README.md). This doc is the day-to-day flow.

## End-to-end flow

```
doctor → init → glossary review → conflicts check
   → dry-run (sample) → preview → full translate
   → [edit manual] → validate → export epub
```

### 1. Diagnose environment
```bash
weaver doctor                 # python, EDITOR, env vars, DB integrity, provider config
weaver doctor --healthcheck   # + live provider probe (needs a valid key)
```
Fix any FAIL before continuing.

### 2. Initialize a project
```bash
weaver init my_novel.epub --from-template light-novel   # power user
weaver new                                               # interactive wizard (weaver[wizard])
```
Creates `.weaver/<name>/` with `project.toml`, `weaver.db`, glossary candidates. Edit `project.toml` to set `[provider]`, `[translation] honorifics = preserve|localize|hybrid`, `[glossary]`, `[qa]`.

### 3. Review glossary (before translate)
Approved terms are injected into every prompt — skipping this lowers quality.
```bash
weaver inspect my_novel/project.toml          # candidate count
weaver glossary review my_novel/project.toml  # [a]approve [e]edit [r]reject [s]skip [f]ind [u]ndo [q]uit
weaver glossary conflicts my_novel/project.toml   # unresolved → translate exits 6
```

### 4. Sample before full run
```bash
weaver translate my_novel/project.toml --first-N 5 --dry-run   # count tokens, no API call
weaver translate my_novel/project.toml --first-N 5             # translate 5 only
weaver preview   my_novel/project.toml --chapter 1
```

### 5. Full translate (resumable)
```bash
weaver translate my_novel/project.toml          # Ctrl+C anytime; resumes
weaver translate my_novel/project.toml --retry-failed
weaver translate my_novel/project.toml --provider gemini --model gemini-1.5-flash   # override, no TOML edit
```
Monitor with `weaver inspect` or the read-only TUI `weaver dashboard` (`weaver[tui]`).

### 6. Manual edit (optional)
```bash
weaver edit my_novel/project.toml --first-failed   # or --next-stale / --recent / <hex-id>
```
Manual status survives `--retry-failed`.

### 7. Validate & export
```bash
weaver validate my_novel/project.toml            # 6 deterministic checks; exit 1 = critical
weaver validate my_novel/project.toml --json     # schema_version: 1
weaver export   my_novel/project.toml --mode markdown   # per-chapter review
weaver export   my_novel/project.toml --mode epub       # final .translated.epub
weaver validate my_novel/project.toml --epub     # EPUBCheck (needs Java + epubcheck.jar)
```

## Shortcuts
`weaver tx`=translate, `ins`=inspect, `gl`=glossary. `weaver --debug <cmd>` prints the full traceback. `weaver --install-completion <shell>` once per shell.

## CLI limitations
- Import is **EPUB only** (TXT/HTML are MVP gaps).
- CLI export is **Markdown + EPUB** (legacy single-source `weaver export`). Per-volume **EPUB/TXT/HTML** export lives in the FastAPI cockpit (`POST /projects/{name}/export/...`, Sprint 8); **DOCX** is deferred.
- No character DB / translation-memory commands yet (MVP gaps — see [MVP_SCOPE.md](MVP_SCOPE.md)).

## Maintenance rules
- Every existing command + flag must keep working (wire-compatible). New behavior is additive: new flags/commands, never a breaking change to an existing one.
- CLI code stays in `cli/` — no web app/router code, no SQLite access. Logic lives in `services/`.
- Errors via `WeaverError`; user-facing message = what failed / likely cause / next command.
