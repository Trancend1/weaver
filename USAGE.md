# Weaver — Optimal Usage Flow

---

## 0. Setup Awal (sekali)

```powershell
# Clone & install
git clone https://github.com/Trancend1/weaver.git
cd weaver
uv sync --extra dev

# Verifikasi
uv run weaver --version   # → weaver 0.4.0

# Set API key (pilih satu provider)
$env:DEEPSEEK_API_KEY = "sk-..."
$env:GEMINI_API_KEY   = "AIza..."

# Optional: global default supaya tidak ketik ulang tiap command
# File: ~/.weaver/config.toml
[defaults]
default_provider = "deepseek"
default_model    = "deepseek-chat"
output_dir       = "~/translations"
```

---

## 1. Diagnosa Environment

```powershell
weaver doctor                 # cek python, EDITOR, env vars, DB
weaver doctor --healthcheck   # + probe provider (butuh key valid)
```

Jika ada FAIL → perbaiki dulu, jangan lanjut.

---

## 2. Inisialisasi Project

**Cara cepat (power user):**

```powershell
weaver init my_novel.epub --from-template light-novel
```

**Cara wizard (pilihan interaktif):**

```powershell
pip install 'weaver[wizard]'
weaver new   # pilih provider, template, output dir
```

**Output:**

```
.weaver/my_novel/
├── project.toml          ← edit ini jika perlu
├── weaver.db
├── glossary_candidates.tsv
└── output/
```

**Edit `project.toml` sesuai kebutuhan:**

```toml
[provider]
name  = "deepseek"
model = "deepseek-chat"

[translation]
honorifics = "preserve"   # atau: localize, hybrid
target_lang = "en"

[glossary]
max_candidates = 200
```

---

## 3. Review Glossary (PENTING — lakukan sebelum translate)

Glossary approved sebelum translate → injected ke setiap prompt. Skip ini → kualitas turun.

```powershell
weaver inspect my_novel/project.toml   # lihat jumlah kandidat

weaver glossary review my_novel/project.toml
# Keyboard:
#   [a] approve   [e] edit   [r] reject   [s] skip
#   [f] find <kata>   [u] undo   [q] quit
```

**Cek konflik setelah review:**

```powershell
weaver glossary conflicts my_novel/project.toml
# Jika ada → resolve dulu atau translate akan exit code 6
```

---

## 4. Test Dulu — Sampled Translate

Sebelum full run, coba N segment:

```powershell
# Dry run: hitung token tanpa kirim ke API
weaver translate my_novel/project.toml --first-N 5 --dry-run

# Actual test: terjemahkan 5 segment saja
weaver translate my_novel/project.toml --first-N 5

# Preview hasilnya
weaver preview my_novel/project.toml --chapter 1
```

Jika hasilnya bagus → lanjut full run.

---

## 5. Full Translate

```powershell
weaver translate my_novel/project.toml
# Progress bar otomatis tampil
# Resumable: Ctrl+C kapanpun, lanjut dari sini
```

**Jika ada yang gagal:**

```powershell
weaver translate my_novel/project.toml --retry-failed
```

**Monitor progress:**

```powershell
weaver inspect my_novel/project.toml

# Atau TUI real-time (tekan r untuk refresh):
pip install 'weaver[tui]'
weaver dashboard my_novel/project.toml
```

---

## 6. Edit Manual (opsional)

Segment tertentu hasilnya kurang → override manual:

```powershell
# Edit segment pertama yang gagal
weaver edit my_novel/project.toml --first-failed

# Edit segment terbaru
weaver edit my_novel/project.toml --recent

# Edit segment spesifik by ID
weaver edit my_novel/project.toml <hex-id>
```

---

## 7. Compare Glossary Antar Chapter

Cek distribusi term antar chapter:

```powershell
weaver glossary diff my_novel/project.toml 1 2
# Output:
# Only in chapter 1 (3): 先生, 道場, 武士
# In both (5): 侍, ...
```

---

## 8. QA Validation

```powershell
# Cek 6 deterministic rules
weaver validate my_novel/project.toml

# Output JSON untuk CI/scripting
weaver validate my_novel/project.toml --json

# Lihat schema dulu
weaver validate --schema
```

Exit code 1 = ada critical finding → wajib perbaiki sebelum export.

---

## 9. Export Output

```powershell
# Markdown review (per chapter, cocok untuk proofreading)
weaver export my_novel/project.toml --mode markdown

# EPUB final
weaver export my_novel/project.toml --mode epub

# Validasi EPUB (butuh Java + epubcheck.jar)
weaver validate my_novel/project.toml --epub
```

**Output files:**

```
.weaver/my_novel/output/
├── markdown/
│   ├── chapter-001.md
│   └── chapter-002.md
└── epub/
    └── my_novel.translated.epub   ← file final
```

---

## Summary Flow

```
doctor → init → glossary review → conflicts check
    → dry-run (5 segment) → preview → full translate
    → [edit manual] → validate → export epub
```

---

## Tips Penting

| Situasi | Command |
|---------|---------|
| Resume setelah interrupt | `weaver translate` (otomatis skip yang sudah done) |
| Ganti provider tanpa edit TOML | `--provider gemini --model gemini-1.5-flash` |
| Debug error aneh | `weaver --debug translate ...` |
| Lihat semua command | `weaver --help` |
| Tab completion | `weaver --install-completion powershell` |
