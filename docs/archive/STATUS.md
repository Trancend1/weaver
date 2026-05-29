# Weaver — Status v0.4.0

**Branch:** `feat/cli-workflow` · **Tests:** 258 passed · **Gate:** AC-1..AC-9 PASS

---

## Sprint History

| Sprint | Version | Selesai |
|--------|---------|---------|
| Phase 0–10 (Core) | 0.1.0 | Foundations → QA Engine → Release |
| Sprint 11a (CLI A) | 0.2.x | Flags, completion, doctor, aliases |
| Sprint 11b (CLI B) | 0.3.0 | Global config, templates, preview, sampled translate |
| Sprint 11c (CLI C) | 0.4.0 | Wizard, TUI dashboard, glossary diff, EPUBCheck, honorifics |

---

## Fitur Lengkap yang Sudah Bisa Dilakukan

### Inisialisasi & Setup

- `weaver init <epub>` — buat project, segmentasi EPUB, ekstrak kandidat glossary
- `weaver init <epub> --from-template light-novel|web-novel|aozora-classic` — pakai preset config
- `weaver new` *(wizard)* — guided setup interaktif: pilih provider → template → output dir → init *(requires `pip install 'weaver[wizard]'`)*

### Inspeksi & Monitoring

- `weaver inspect <project.toml>` — status project (chapters, segments, % done, glossary)
- `weaver inspect --healthcheck` — probe provider availability
- `weaver doctor` — diagnosa env vars, DB integrity, provider config
- `weaver doctor <project.toml> --healthcheck` — termasuk network probe
- `weaver dashboard <project.toml>` — TUI read-only mirror of inspect; `r` refresh, `q` quit *(requires `pip install 'weaver[tui]'`)*
- `weaver preview <project.toml> [--segment ID] [--chapter K] [--pager auto]` — render source + translation pairs inline

### Terjemahan

- `weaver translate <project.toml>` — terjemahkan semua segment pending; resumable
- `weaver translate --retry-failed` — ulangi segment gagal
- `weaver translate --provider X --model Y` — override tanpa edit TOML
- `weaver translate --dry-run` — hitung token tanpa kirim ke provider
- `weaver translate --verbose` — echo per-segment I/O
- `weaver translate --first-N 10` — terjemahkan hanya N segment pertama (sampled)
- Batch: `weaver translate proj1.toml proj2.toml` — proses sequential

### Glossary

- `weaver glossary review` — approve/edit/reject/skip/undo kandidat interaktif; `[f]ind` hotkey + `--find <teks>`; counter `Reviewed N of M`
- `weaver glossary edit` — buka glossary TSV di `$EDITOR`; destructive confirm sebelum simpan
- `weaver glossary conflicts` — tampilkan approved term yang konflik
- `weaver glossary diff <project.toml> 1 2` — bandingkan coverage term antar chapter

### Edit Manual

- `weaver edit <project.toml> <segment-id>` — override satu segment via `$EDITOR`
- `weaver edit --first-failed` / `--next-stale` / `--recent` — pilih segment tanpa copy-paste ID

### Export

- `weaver export <project.toml> --mode markdown` — per-chapter Markdown review files
- `weaver export --mode markdown --translation-only` — skip source text
- `weaver export <project.toml> --mode epub` — tulis translated EPUB (`.translated.epub`)

### Validasi & QA

- `weaver validate <project.toml>` — 6 deterministic QA checks
- `weaver validate --json` — output JSON dengan `schema_version: 1`
- `weaver validate --schema` — print stable JSON shape tanpa butuh project
- `weaver validate --epub` — jalankan EPUBCheck (graceful skip jika jar tidak ada)

### Config & Honorifics

- `~/.weaver/config.toml` — global default (provider, model, output_dir, editor)
- Env vars: `WEAVER_DEFAULT_PROVIDER`, `WEAVER_DEFAULT_MODEL`, `WEAVER_OUTPUT_DIR`
- Precedence: `CLI flag > env var > project.toml > global config > built-in default`
- `honorifics = "preserve"|"localize"|"hybrid"` di `[translation]` project.toml

### UX & Developer Tools

- Shell completion: `weaver --install-completion bash|zsh|fish|powershell`
- Aliases: `weaver tx` = translate, `weaver ins` = inspect, `weaver gl` = glossary
- `weaver --debug <command>` — full Python traceback
- `--help` dengan contoh (`epilog=`) di setiap command

---

## Provider Support

| Provider | Auth | Status |
|----------|------|--------|
| `deepseek` | `DEEPSEEK_API_KEY` | Default cloud |
| `gemini` | `GEMINI_API_KEY` | Free-tier cloud |
| `ollama` | None (local) | Local LLM |
| `fake` | None | CI/dev |

---

## Optional Extras

```bash
pip install 'weaver[tui]'     # weaver dashboard
pip install 'weaver[wizard]'  # weaver new
pip install 'weaver[all]'     # keduanya
```

---

## Exit Codes

| Code | Kondisi |
|------|---------|
| 0 | Sukses |
| 1 | QA critical finding |
| 3 | Provider unavailable |
| 4 | EPUB tidak bisa dibaca |
| 5 | Segment ID tidak ditemukan |
| 6 | Glossary conflict |
| 7 | Config/input error |
