# Weaver Security And Performance

Operational guide for production readiness. Calibrated for a local CLI tool, not a hosted SaaS. Most "security" concerns in cloud products do not apply here. Some local-tool concerns are unique and addressed below.

## Threat Model

Weaver's threat model differs from a typical SaaS:

- **No multi-tenant data.** Each user's project files are on their disk only.
- **No central server.** No service to hack, no DB to exfiltrate.
- **No user account system.** No credentials to leak.
- **Network use is opt-in.** Cloud providers require user-supplied API keys.

Real threats that remain:

1. **API key leakage.** User-supplied keys could appear in logs, error reports, or shared project files.
2. **Prompt injection via source text.** EPUB content controls some of the LLM input.
3. **Malicious EPUB.** A crafted EPUB could exploit XML parser vulnerabilities or write outside the project directory.
4. **Legal exposure.** Distributing a tool for translating copyrighted novels invites takedown.
5. **Supply chain attack.** A compromised dependency on PyPI could affect users.

## Security Controls

### API Protection (Cloud Providers)

- API keys come from environment variables only. Never read from `project.toml`. Never written to logs.

  | Provider | Environment Variable | Where to get |
  |----------|---------------------|--------------|
  | DeepSeek | `DEEPSEEK_API_KEY` | platform.deepseek.com |
  | Gemini | `GEMINI_API_KEY` | aistudio.google.com (free) |
  | Ollama | N/A | local, no key |

- Logs grep-tested in CI: any string matching common API key patterns (`sk-`, `AIza`) fails the build.
- Error messages mask keys: `Authorization: Bearer sk-***`.
- Cloud provider calls are HTTPS only. HTTP base URLs in config raise an error unless `provider.allow_insecure = true` (debug only).
- No outbound calls to any endpoint not configured in `project.toml`.

### Session Security

Not applicable. There are no sessions. CLI invocations are independent.

### AI Abuse Prevention

- No shared API keys. Weaver does not act as a gateway for users' translation costs.
- No request multiplication. One segment = one LLM call (plus optional repair retry). No silent retries that explode cost.
- Rate limiting deferred until cloud providers require it. When added, applied client-side.
- Token usage tracking is on by default for cloud providers. User sees cost before, during, after run.

### Prompt Injection Handling

Source text in JP novels can contain instructions like "ignore previous instructions" (rare in real novels but possible in user-supplied content). Defenses:

- Source text is delivered to the model inside an explicit delimiter block:

```
<source>
{escaped_source_text}
</source>
```

- The system prompt explicitly tells the model: text inside `<source>` is data, not instructions.
- The JSON-output contract limits damage. Even if a model is jailbroken, the output is parsed as JSON or marked failed.
- Repair retry uses the same delimiter discipline.
- Glossary terms are injected as a separate block, never inline in the source text.

Acceptable residual risk: an LLM is occasionally tricked. The deterministic QA layer (JP residue check, length ratio) catches gross failures. Translators reviewing Markdown output catch the rest.

### File Upload Security

Not applicable in the conventional sense. Weaver reads from local paths only.

Concerns:

- **Malicious EPUB parsing.** Use a hardened XML parser. `defusedxml` for any XML parsing. `ebooklib` uses `lxml`; disable external entity resolution.
- **Path traversal in EPUB internal hrefs.** When the renderer writes a translated EPUB, output paths are constructed within the project's `output_dir` only. Internal hrefs in the source EPUB are not used as file paths during write.
- **Zip bombs.** EPUBs are zip files. Pre-check uncompressed size before extraction. Reject EPUBs that decompress to more than 200 MB.

### File Upload Security (Project Sharing)

Users sometimes share `.weaver/` project directories with collaborators. Security considerations:

- `project.toml` should never contain API keys (enforced).
- `raw_response` columns in the database contain LLM responses, which may contain sensitive context. Users can disable raw response logging via `[logging] raw_responses = false`.
- A `weaver export --sanitize` command (future) strips logs and raw responses for sharing.

### RBAC Strategy

Not applicable. Single-user local tool.

### Infrastructure Hardening

Not applicable for MVP-0. Weaver does not run servers.

If a `weaver cloud` hosted service is ever built (not planned):

- Strict per-user API key isolation.
- HTTPS-only public endpoints.
- Database encryption at rest.
- Audit logs for all cross-user operations.
- Standard OWASP-grade application security.

That product is out of scope.

### Monitoring And Logging

Local-only logging:

- Logs written to `.weaver/<project>/logs/weaver-{date}.log`.
- Rotation: daily file; retention 30 days.
- Log levels per [CLAUDE.md §4.2](../CLAUDE.md).
- No outbound log transmission. No Sentry, no telemetry by default.
- Optional anonymous telemetry post-MVP-1 with explicit opt-in.

### Rate Limiting

Cloud provider rate limiting is the provider's responsibility. Weaver respects 429 responses with exponential backoff. After `max_retries` exceeded, segment marked failed.

No rate limiting on `weaver` invocations themselves. The user controls their own machine.

## Performance Budgets

Targets validated on a moderately-spec'd developer laptop (16 GB RAM, modern x86-64 or Apple Silicon).

### Wall-Clock Budgets

| Operation | Project size | Target |
|-----------|-------------|--------|
| `weaver init` | 200-chapter EPUB | < 30 s |
| Glossary extraction during init | 200-chapter EPUB | < 20 s |
| `weaver inspect` | 10,000-segment project | < 1 s |
| `weaver status` | 10,000-segment project | < 1 s |
| Resume scan on startup | 10,000-segment project | < 5 s |
| `weaver translate` per segment (fake provider) | one segment | < 50 ms |
| `weaver export markdown` | 10,000 segments | < 10 s |
| `weaver export epub` | 10,000 segments | < 30 s |
| `weaver validate` | 10,000 segments | < 15 s |

Throughput depends on provider latency, which Weaver does not control.

### Memory Budgets

| Operation | Target |
|-----------|--------|
| Peak resident memory during any command | < 1 GB |
| Streaming through large EPUBs | < 256 MB |

### Disk Budgets

| Item | Limit |
|------|-------|
| SQLite DB for a 10k-segment project | < 100 MB |
| Logs (post-rotation) | < 50 MB |
| Output Markdown for a 10k-segment project | < 50 MB |
| Output EPUB | < 1.5 × source EPUB size |

### Benchmark Suite

A `bench/` directory holds benchmark scripts. CI runs them on PRs that touch core paths. Regressions exceeding 20% require explicit PR justification.

## Query Optimization

SQLite-level rules:

- Indexes on every column used in `WHERE` clauses for hot paths (status, chapter_id, project_id).
- `EXPLAIN QUERY PLAN` reviewed for any new query touching the segments table.
- No `SELECT *` in service-layer code. Specify columns.
- Bulk operations use `executemany` with a single transaction.

Performance test pattern:

```python
def test_resume_scan_under_5s_at_10k_segments(seed_db_10k_segments):
    start = time.monotonic()
    scan_in_progress_segments(seed_db_10k_segments)
    assert time.monotonic() - start < 5.0
```

## Caching Strategy

Minimal. The product is not latency-critical at MVP-0.

- LRU cache on glossary term lookups during context building.
- No caching of LLM responses (they should be deterministic-enough at temp=0 if the user wants caching).
- No caching of EPUB parses (parsed once during init, stored in DB).

## CDN Usage

Not applicable. There is no web frontend.

If a docs site is published via GitHub Pages, GitHub's CDN suffices.

## Lighthouse Targets

Not applicable until a web surface exists. If a marketing or docs site is built later:

- Performance: ≥ 95.
- Accessibility: ≥ 95.
- Best Practices: ≥ 95.
- SEO: ≥ 90.

These are not aspirational; static docs sites easily hit them.

## Frontend Performance

Not applicable. CLI tool.

## Backend Performance

The "backend" is the user's own machine. Optimization rules:

- Hot-path code stays in pure Python — no native extensions unless a benchmark proves them necessary.
- Avoid creating millions of objects in a single command. Stream where possible.
- Profile before optimizing. `py-spy` or `cProfile` first; intuition second.
- Optimize for cold start. A CLI command spends real time on Python import; lazy-load heavy modules.

## Cost-Performance Balancing

Cloud provider cost considerations:

- Default to providers with the best cost/quality ratio (DeepSeek as of late 2025).
- Token usage tracked per call.
- Pre-flight cost estimate in `weaver inspect`:
  ```
  Estimated cost: $2.40 (1.8M input tokens × $0.14/M + 0.6M output × $0.28/M)
  ```
- Users can set a `max_cost_usd` in `project.toml`. Translation halts if estimate exceeds this.

## Most Dangerous Vulnerabilities (Likely Production Failures)

In order of severity:

### 1. Path Traversal During EPUB Read

**Risk:** A malicious EPUB contains entries like `../../etc/passwd`.

**Mitigation:** All file extraction uses `Path.resolve()` and verifies the resolved path is within the EPUB's temporary extraction directory. `ebooklib` handles this internally but Weaver adds a defense-in-depth check. Tested.

### 2. XXE / External Entity Attack

**Risk:** EPUB XHTML or container.xml contains external entity references.

**Mitigation:** Use `defusedxml` for any direct XML parsing. Disable entity resolution at the parser layer.

### 3. API Key Leakage In Shared Logs

**Risk:** User shares a log file for debugging, key included.

**Mitigation:**
- Keys never logged.
- CI grep test on log producers.
- `weaver sanitize-logs <path>` utility (post-MVP-1) to scrub before sharing.

### 4. Output Overwrite Without Backup

**Risk:** A failed export overwrites a previously-good export.

**Mitigation:**
- Atomic write: write to temp file, then rename.
- Backup previous export to `output_dir/.backup/` before overwriting.
- Tested.

### 5. Database Corruption On Power Loss

**Risk:** Translation in flight, machine loses power, DB corrupts.

**Mitigation:**
- WAL mode (already specified).
- Single-transaction per segment.
- Startup integrity check (PRAGMA integrity_check); refuse to run if corrupt; recommend backup file restore.

### 6. Prompt Injection From Source Text

**Risk:** Source text manipulates the model.

**Mitigation:** Delimiter discipline, structural prompts, JSON output contract, deterministic QA layer.

### 7. Cost Explosion From Long Documents

**Risk:** User points Weaver at a 5,000-page novel using GPT-4. Bill arrives.

**Mitigation:**
- Pre-flight cost estimate.
- `max_cost_usd` config option.
- Token usage shown live during translation.

### 8. Dependency Compromise

**Risk:** A PyPI dependency becomes malicious.

**Mitigation:**
- `uv.lock` pins exact versions and hashes.
- Dependabot / Renovate alerts.
- Minimal dependency tree (currently planned: typer, rich, pydantic, ebooklib, fugashi, ipadic-neologd, openai, defusedxml).
- Vendored fallback for any dependency under 100 lines of code.

## Likely Production Failure Points

In rough order of probability:

1. **Ollama not running or wrong model.** User-side config issue. Mitigated with clear healthcheck error messages. Low priority for hardware-limited developers — FakeProvider or cloud providers substitute.
2. **DeepSeek API key missing or expired.** Mitigated with explicit error: `DEEPSEEK_API_KEY not set — run: export DEEPSEEK_API_KEY=your_key` / "Provider returned 401: check key validity at platform.deepseek.com".
2a. **Gemini API key missing or expired.** Same pattern: `GEMINI_API_KEY not set — get a free key at aistudio.google.com` / "Provider returned 403: check key at aistudio.google.com".
3. **EPUB has unusual structure** (no spine, no nav, embedded JS). Mitigated by reader gracefully skipping unsupported blocks and logging warnings.
4. **Translation prompt produces malformed JSON.** Mitigated by single repair retry, then failed-marker.
5. **User's disk fills up mid-translation.** Mitigated by writing transactionally; the in-flight translation is lost but no prior work is corrupted.
6. **User kills `weaver translate` ungracefully.** Mitigated by `in_progress` → `pending` on restart.
7. **Terminal does not support `rich` features.** Mitigated by falling back to plain text when `sys.stdout.isatty()` is false.
8. **`fugashi` tokenizer dictionary not installed.** Mitigated with `weaver --doctor` health check (post-MVP-1) that diagnoses common setup issues.

## Cost Explosion Risks

Scenarios where users hit unexpected costs:

| Scenario | Trigger | Mitigation |
|----------|---------|------------|
| Retry storm on flaky cloud provider | Network issues + `max_retries = 5` | Cap total retries per run, not per segment |
| Very long source segments | Single segment > 10k tokens | Per-segment token cap with explicit error if exceeded |
| Accidentally pointing at expensive model | User config error | Pre-flight estimate shows cost prominently |
| Translating thousands of segments without realizing | User confusion | `weaver inspect` shows segment count and cost estimate before `translate` |

## Security Audit Cadence

- Pre-release: run `pip-audit`, `safety` on dependencies.
- Quarterly: review of CVEs in dependency tree.
- On any contribution that touches I/O: explicit security review per the PR checklist in [CLAUDE.md §4.2](../CLAUDE.md).

## Things Not Worth Doing Yet

Common SaaS security work that does not apply to a local CLI:

- WAF.
- DDoS protection.
- SAML/SSO.
- SOC 2.
- Pentests.

If `weaver cloud` ever exists, these become relevant. Not before.
