# Proposal: Novel Translation Workflow Enhancement untuk Weaver

**Status:** Proposed Insight (untuk review owner Weaver)
**Tanggal:** 2026-06-16
**Versi Weaver saat ini:** 0.7.1 (released) + 0.7.2 (Connection-First Routing, di branch `feat/connection-first-routing`)
**Referensi:** `opennovel-reference.md` (insight doc owner), opennovel.co, novellist.co, readomni.com (OmniTranslate)

---

## 0. Ringkasan Eksekutif

`opennovel-reference.md` adalah arsitektur 7-komponen yang solid (Persistent Memory, Glossary, Translation Memory, Story Context, Character Profile, Translation Profile, Entity Extraction) untuk **novel panjang**. Weaver sudah punya **60-70%** dari fondasi itu — terutama di sisi Glossary, Translation Memory (exact-match), dan Character DB. Yang **missing** bukan fondasi, tapi **progressive context** (cross-chapter / cross-volume memory) dan **richer profile schema**.

Proposal ini:

1. **Review ulang** setiap komponen di `opennovel-reference.md` terhadap realita platform (opennovel.co, OmniTranslate) — apa yang cocok, apa yang outdated, apa yang missing.
2. **Mapping gap** ke codebase Weaver — file:line, integration points.
3. **Roadmap realistis** yang **menghormati hard rules** Weaver (ADR 018 D9: no circuit breaker, no cost dashboard, no native non-OpenAI families, single-user, no telemetry).
4. **Quick wins** (effort rendah, impact tinggi) yang bisa di-PR sekarang.
5. **Differentiation opportunities** — apa yang Weaver bisa lakukan **lebih baik** dari opennovel/OmniTranslate (kolaborasi, per-task routing, provenance).

---

## 1. Detailed Review: opennovel-reference.md

Reference doc Anda mengusulkan arsitektur 7-komponen. Di bawah ini per-komponen: definisi asli, realita di platform, dan relevansi untuk Weaver.

### 1.1 Component 1 — Persistent Name Memory

**Definisi reference:** Map `李晨 → "Li Chen"`. AI tidak boleh bikin variasi baru ("Lee Chen", "Lichen"). Wajib pakai stored translation.

**Realita platform:**
- **opennovel.co** glossary punya 3 kategori: `character`, `title`, `term`. Gender per-character (male/female/undecided).
- **OmniTranslate** punya richer schema: `raw_term` + `translation` + `description` + `tags` + `priority` (`#important`). Mendukung scope: Global vs per-thread.
- Keduanya support CSV import/export.

**Weaver saat ini:**
- `characters` table: `jp_name`, `en_name`, `gender`, `role`, `notes`, UNIQUE per project. (`storage/characters.py`)
- `glossary_terms` table: `source`, `target`, `category`, `notes`, `case_sensitive`, UNIQUE per project. (`storage/glossary.py`)
- Injected ke prompt dengan **substring filter**, cap 20 terms. (`services/translation.py:148`)
- Conflict detection di `raise_on_glossary_conflicts`. (`services/glossary.py`)

**Gap:**
- `characters` schema tipis — tidak ada `aliases`, `pronouns_preferred`, `voice_style`, `relationships`, `first_introduction`, `description`, `appearance`. Hanya `notes` sebagai freeform bag.
- `glossary_terms` tidak punya `priority`/`weight`, `pronunciation`, `contextual_usage_rules`. Tidak ada versioning.
- Tidak ada **two-tier scope** (global + per-project). Reference doc Phase 5 menyebut "Shared Glossary" sebagai future enhancement; ini belum ada di Weaver.

**Rekomendasi:**
- Quick win: tambah field `pronouns`, `aliases (JSON array)`, `voice_notes` ke `characters` (migration v13). Backward-compat: existing rows render existing prompt unchanged.
- Medium: `priority` field di `glossary_terms` (boolean `#important` flag) yang di-tag khusus di prompt ("use this term even in complex sentences").
- Phase N: global glossary di `~/.weaver/global_glossary.toml` yang merge dengan per-project, dengan override semantics.

---

### 1.2 Component 2 — Glossary

**Definisi reference:** Tabel source→translation. Override model preference.

**Realita platform:**
- **opennovel.co**: CSV import, AI-assisted "Detect New Terms and Characters" (pre-translation gate), 500-term Cultivation Pack.
- **OmniTranslate**: AI-assisted extraction (Basic vs Advanced, +2 credits/1K chars), Term Conventions, **reverse-lookup dari reader** (highlight translated text → jump ke glossary entry → edit). Pakai **sophisticated UI**: term-bolded in reader, click-to-edit.

**Weaver saat ini:**
- **Strong** — `glossary_candidates` workflow: regex auto-extract (katakana, CJK, honorific suffixes) + optional MeCab/fugashi proper-noun tagging.
- AI-suggested targets via `complete()` (ADR 014), strict JSON `{"target": "..."}`.
- Interactive review session: `approve`/`edit`/`reject`/`undo`. (`services/glossary_review.py`)
- Cockpit UI: search/paginate/bulk, keyboard shortcuts (j/k/a/r/e/x). (`_glossary_terms.html`)

**Gap:**
- Tidak ada **in-reader term highlight** + click-to-edit. Loop "salah nama → buka glossary tab → search → edit" masih panjang.
- Tidak ada **Continuous extraction** (entity yang muncul di chapter baru otomatis di-flag).
- Tidak ada **premade genre packs** (Cultivation Pack).
- Tidak ada **reverse-lookup** (selected phrase in translation → "what was the original term?").

**Rekomendasi:**
- Quick win: in-reader term highlight (CSS) + click → opens edit modal dengan prefill source/target. Update `_segment.html`. (Effort: rendah)
- Medium: continuous entity extraction loop. Setelah `translate_one_segment` success, call `complete()` untuk "extract new proper nouns in this segment" → insert ke `glossary_candidates` dengan `frequency++`. User review di candidates page. Pattern reuse dari `glossary_suggestion.py`.
- Phase N: premade packs (cultivation-xianxia, modern-romance, sci-fi) sebagai JSON shipped in `weaver/glossary_packs/`. `weaver glossary pack install cultivation-xianxia`.

---

### 1.3 Component 3 — Translation Memory

**Definisi reference:** Kalimat berulang → stored translation. Similarity > 90% → reuse. Mengurangi token + editing.

**Realita platform:**
- **opennovel.co**: Auto-Translate ePub export; tidak expose explicit TM.
- **OmniTranslate**: tidak ada explicit TM UI, tapi "Lite View" + cache + chunk-level reuse di-implicit via batch translate.

**Weaver saat ini:**
- **Strong exact-match.** `translation_memory` table keyed by `source_hash` (UNIQUE per project). `lookup_translation_memory` short-circuits provider call. (`services/translation.py:495-509`)
- Manual edit adalah source of truth (`protect_manual=True` blocks provider overwrites).
- Reuse counter exposed via `translations.provider='memory'`.
- TMX/CSV import/export: **belum ada** (Phase 5 reference doc).

**Gap:**
- **No fuzzy match.** Hanya exact `source_hash`. Tidak ada normalized-prefix index, tidak ada embedding, tidak ada fuzzy ratio.
- **No cross-project TM.**
- **No TMX import/export** (industry standard, ada di Phase 5 reference).

**Rekomendasi:**
- Quick win: TMX import/export (`storage/translation_memory.py` extend + `services/translation_memory.py` add import/export). Mendukung `weaver memory export/tmx` + `weaver memory import/tmx`.
- Medium: fuzzy match tier. Tambah normalized-prefix index (e.g., lowercase, strip punctuation, first N chars). Lookup: exact → normalized → fuzzy (token overlap ratio > 0.85). Pure Python, no embeddings, no extra deps. Cap ke 1 candidate + warn.
- Phase N: cross-project TM (`--project-allowlist` flag di `weaver translate`).

---

### 1.4 Component 4 — Story Context Memory

**Definisi reference:** Cross-chapter context. JSON `{current_arc, main_characters, recent_events}`. Digabung dengan current chapter → translation prompt.

**Realita platform:**
- **opennovel.co**: tidak ada explicit "story context" UI. Auto-Translate pakai last N translated segments secara implisit.
- **OmniTranslate**: "Batch Analyze" (extracted glossary from raws before translation) adalah proxy untuk story context — tapi glossary, bukan narrative.

**Weaver saat ini:**
- **Weak.** Hanya **5 previous segments dalam chapter yang sama** di-inject di `<context>` block. (`services/translation.py:179-187`)
- Tidak ada cross-chapter context.
- Tidak ada volume-level summary.
- Tidak ada project-wide "story so far" memory.

**Gap (HIGH PRIORITY):**
- Untuk novel panjang (200+ chapter, 1000+ segments), 5 segments per chapter **tidak cukup** untuk menjaga konsistensi nama/lokasi yang muncul di chapter berbeda.
- Hallucination risk tinggi saat chapter 50 mereferensikan event chapter 10.

**Rekomendasi (HIGH VALUE):**

Tiga layer story context, masing-masing dengan budget token sendiri:

1. **Layer 1 — Chapter-internal context** (SUDAH ADA): last 5 segments, 600 token cap.
2. **Layer 2 — Cross-chapter rolling window** (QUICK WIN): last K translated segments di project, dengan chapter marker, hard cap 800 token. Filter ke segments yang punya entity overlap (substring match) dengan current chapter. Inject sebagai `<story_context>` block di prompt. In-memory atau cached (bukan DB hit per segment).
3. **Layer 3 — Compressed project summary** (MEDIUM): LLM-summarize project every N successful segments (default N=20), simpan di `story_summaries` table (migration v13). Summary yang di-compress di-inject saat chapter change. Cadence: post-success hook di `translate_one_segment`. Pattern reuse dari `glossary_suggestion.py` (`complete()` primitive).

**Catatan penting:** Owner Weaver sudah menyatakan cross-chapter context **bukan on the roadmap** (no ADR filed). Proposal ini merekomendasikan **membuat ADR baru** untuk memasukkan ini.

---

### 1.5 Component 5 — Character Profile Memory

**Definisi reference:** `{name: {gender, title, ...}}`. Pronoun akurat, gelar konsisten.

**Realita platform:**
- **opennovel.co**: character entry + gender only.
- **OmniTranslate**: raw + translation + description + tags. Mendukung **character relationships** (limited).

**Weaver saat ini:**
- **Thin.** `characters` table: `jp_name`, `en_name`, `gender`, `role`, `notes`. Injected substring-matched, cap 20.
- QA check: `character_name_missing`. (`qa/consistency_checks.py:46`)
- `character_page_drafts` untuk XHTML character page extraction (Sprint 3A).

**Gap:**
- No `description` (1-3 sentences).
- No `appearance` (visual cues).
- No `voice_style` (formality, accent, quirks).
- No `pronouns` (he/she/they).
- No `aliases` (e.g., protagonist punya nama asli + nama samaran).
- No `relationships` (mother_of, rival_of, etc.).
- No `first_introduction_chapter` (untuk reference balik).
- No `title` (Young Master, Sect Leader, dll — saat ini masuk glossary `title` category, tapi tidak linked ke character).

**Rekomendasi:**

Migration v13 — extend `characters` table:

```sql
ALTER TABLE characters ADD COLUMN description TEXT;
ALTER TABLE characters ADD COLUMN voice_style TEXT;
ALTER TABLE characters ADD COLUMN aliases_json TEXT;        -- JSON array
ALTER TABLE characters ADD COLUMN pronouns TEXT;            -- "he" | "she" | "they"
ALTER TABLE characters ADD COLUMN first_intro_chapter_id TEXT REFERENCES chapters(id);
ALTER TABLE characters ADD COLUMN updated_at TIMESTAMP;
```

Baru `_characters.html` di workspace, dengan section: Profile (gender, pronouns, title), Voice, Description, Aliases, Relationships. Update `<characters>` block di prompt untuk include voice_style + description (cap 20, hard 400 char per entry).

`title` di glossary → tambah foreign-key reference ke `characters.id` (optional, migration v13). Saat glossary `title` di-inject, linked character ikut ter-include di `<characters>` block.

---

### 1.6 Component 6 — Translation Profile

**Definisi reference:** Project-level style. Light novel (casual) vs Wuxia/Xianxia (formal, retain honorifics) vs Western Fantasy (literary).

**Realita platform:**
- **opennovel.co**: model Standard vs Boosted; honorific policy per-novel.
- **OmniTranslate**: **Term Conventions** (paling sophisticated) — plain-English rules yang di-scope (`starts with`, `ends with`, `contains`). Global inheritance + per-thread override.

**Weaver saat ini:**
- `[translation]` table di `project.toml`: hanya `honorifics = preserve|localize|hybrid`.
- Prompt `<policy>` block: hanya emit honorific policy.
- **Tidak ada** style profile, punctuation policy, name-rendering policy.

**Gap:**
- Reference doc mengusulkan `tone` + `dialog_style` + `descriptive`. Weaver tidak punya structured profile.

**Rekomendasi:**

Quick win — extend `[translation]` table di `project.toml`:

```toml
[translation]
honorifics = "preserve"        # sudah ada

[translation_profile]
tone = "formal"                # "casual" | "formal" | "literary" | "archaic"
dialog_style = "natural"       # "natural" | "stiff" | "verbose"
name_rendering = "first_full_then_short"  # or "always_full", "shorthand_from_chapter_2"
punctuation = "en_dash_smart_quotes"      # or "em_dash_straight_quotes", "minimal"
tense = "past"                 # "past" | "present" | "historical_present"
descriptive = true             # boolean: more adjectives/sensory detail
```

Update `balanced_system.txt` + `balanced_user.jinja2` untuk emit `<profile>` block. Pure config, **zero schema change**. Effort rendah.

**Future (Phase N)**: term conventions ala OmniTranslate (scoped rules, plain English). Implement as `[translation_profile.conventions]` array. Stored in config, injected verbatim di prompt sebagai `<conventions>` block.

---

### 1.7 Component 7 — Automatic Entity Extraction

**Definisi reference:** Detect new terms otomatis. User Accept/Reject. Memory auto-updated.

**Realita platform:**
- **opennovel.co**: "Detect New Terms and Characters" button (manual trigger), pre-translation gate.
- **OmniTranslate**: Basic vs Advanced extraction; "detect before translating" mode; Consistency Sweep post-hoc.

**Weaver saat ini:**
- **One-shot at `init`.** Regex (katakana, CJK, honorific suffixes) + optional MeCab/fugashi proper-noun. (`services/glossary.py`)
- Stored di `glossary_candidates` dengan `frequency` count.
- **Tidak ada continuous discovery** dari translated segments.

**Gap:**
- Entity yang muncul **setelah init** (chapter 50+) tidak di-detect otomatis.
- Tidak ada entity linking ke existing characters/glossary (a new term may already exist dengan nama berbeda).
- Tidak ada **post-translation discovery loop** (extract dari translation result, propose ke user).

**Rekomendasi:**

Quick win — continuous extraction loop:

Hook di `translate_one_segment` post-success (line ~559-569 di `services/translation.py`):

1. Setelah `record_translation`, jika total translated segments di chapter ini > threshold (default 5), schedule async extraction: `complete()` dengan prompt "extract proper nouns and world terms from this segment not already in [known_glossary]".
2. Output → insert ke `glossary_candidates` dengan `frequency=1`.
3. Reuse existing UI (cockpit candidates page) untuk user review.

Pattern sudah ada di `glossary_suggestion.py`. **Zero new infrastructure.** Hanya hook + cadence config.

**Cadence config** (per-project, `[memory]` section):

```toml
[memory]
extraction_cadence = "per_chapter"   # "off" | "per_chapter" | "per_volume" | "per_project"
```

---

### 1.8 Translation Pipeline (dari reference)

Reference doc:
```
Open Chapter → Load Profile → Load Memory → Load Glossary → Load TM → Load Story Context → Build Prompt → Translate → Validate → Extract → Update Memory → Save
```

**Weaver saat ini** (di `translate_one_segment`, `services/translation.py:433-573`):
```
1. update_segment_status("in_progress")
2. TM lookup (short-circuit)
3. build_context (glossary + characters + last 5 segments)
4. resolve_chain (routing)
5. primary + fallback
6. record_translation
7. save_translation_memory
8. update status
```

**Gap pada pipeline:**
- **No "Load Story Context"** step. (Layer 2/3 dari §1.4)
- **No "Validate"** step. (LLM-based consistency check, see §3 below)
- **No "Extract"** post-step. (Continuous entity extraction, see §1.7)
- **No "Update Memory"** step. (TM updated, tapi story memory tidak.)

**Rekomendasi:**

Refactor `translate_one_segment` (atau wrap dengan pipeline runner) untuk tambah 3 hooks opsional, masing-masing gated by config dan biaya token terlihat:

```python
# Pseudo (services/translation.py:540-570)
if translation_succeeded:
    record_translation(...)
    save_translation_memory(...)

    if config.memory.extraction_cadence != "off" and chapter_segment_count % cadence == 0:
        schedule_entity_extraction(segment_id, project_id)  # async via JobRegistry

    if config.memory.story_summarization and chapter_segment_count % summary_cadence == 0:
        schedule_story_summarization(project_id)            # async via JobRegistry
```

**Cadence default: off** (zero behavior change for existing users). Opt-in per project.

---

## 2. Detailed Findings: Realita OpenNovel & NovelList

Research dari opennovel.co, novellist.co, readomni.com (OmniTranslate), webnovelsai.com, dan whatnovel.com. Disini yang **belum** di opennovel-reference.md tapi **penting untuk Weaver**.

### 2.1 Yang opennovel-reference.md KELIRU / Outdated

| Reference doc claim | Realita |
|---|---|
| "Persistent Memory" sebagai satu komponen | Bukan satu — minimal 3 sub-komponen: glossary scope, story context, character profile. OpenNovel pecah jadi 3 entitas UI terpisah. |
| "Translation Profile" sebagai `{tone, dialog_style}` | OmniTranslate punya **Term Conventions** — jauh lebih sophisticated (scoped rules, inheritance). |
| "Entity Extraction" sebagai Accept/Reject UI | OpenNovel pre-translation gate; OmniTranslate punya Basic/Advanced + Consistency Sweep. |
| "Phase 5: Shared Glossary" | OpenNovel sudah punya **Cultivation Pack** (500+ terms) sebagai Google Sheet. Bukan future — sudah jadi differentiator. |
| "Cross-Chapter Validation" sebagai future enhancement | OpenNovel punya Auto-Translate (background batch, partial-failure UX). Bukan sekadar validasi — eksekusi paralel. |

### 2.2 Yang TIDAK ADA di reference doc tapi ADA di platform

(Detail per item ada di research report saya. Di bawah ini ringkasan + implikasi untuk Weaver.)

1. **Two-tier glossary scope (Global + per-thread)** — OmniTranslate. → Weaver opportunity: `~/.weaver/global_glossary.toml` + per-project override.
2. **Term Conventions** (scoped rules) — OmniTranslate. → Weaver opportunity: `[translation_profile.conventions]` array, plain English rules.
3. **In-reader term highlight + click-to-edit** — OmniTranslate. → Weaver quick win: CSS + JS edit modal.
4. **Reverse-lookup (translated phrase → source term)** — OmniTranslate. → Weaver opportunity: segment action menu.
5. **Auto-substitute on term change** — OmniTranslate: update term → all existing translations di-rewrite in-place via string replacement. → Weaver opportunity: `weaver memory rewrite --term X --new Y`.
6. **Pre-translation glossary gate** — OpenNovel Auto-Translate refuses to start until glossary reviewed. → Weaver opportunity: `weaver batch translate` dengan `--require-glossary-reviewed` flag.
7. **Background batch with partial-failure UX** — OpenNovel, OmniTranslate. → Weaver sudah punya JobRegistry + SSE; perlu polish: failed units di-top of result list, retry-from-failure action.
8. **Chunk-level actions** (regenerate/enhance/edit per paragraph) — OmniTranslate. → Weaver sudah punya `segments` table; expose per-segment actions di workspace (`_segment.html`) — "Regenerate this segment" sudah ada implicitly via "Suggest another translation"; tambah "Regenerate (replace current)" + "Edit manual" actions.
9. **ePub export** — OpenNovel, OmniTranslate. → Weaver **SUDAH punya** (`renderers/epub.py`, `services/export_book.py`). ✅
10. **Multilingual target language** — OpenNovel EN/ES. → Weaver sudah punya `[project] target_lang` di `core/config.py`. Tidak ada UI/language switcher; tidak masalah untuk v1.
11. **Genre glossary packs** — OpenNovel Cultivation Pack. → Weaver opportunity: `weaver glossary pack install cultivation-xianxia` (shipped TOML).
12. **Per-task model routing** — **TIDAK ADA di platform manapun**. Weaver sudah punya (`[routing.<task>]`). Ini **differentiation opportunity** untuk Weaver.
13. **Collaborative glossary** — **TIDAK ADA di platform manapun** (semua single-user). → Weaver differentiation opportunity (Phase N, butuh user accounts).
14. **Per-attempt provenance (audit trail)** — **TIDAK ADA di platform**. Weaver sudah punya `translations` table (append-only, `raw_response`, `provenance_json` di `translation_candidates`). Ini **differentiation opportunity** untuk debugging + fine-tune dataset.
15. **AI quality judging** (paired comparison) — OmniTranslate. → Weaver opportunity: track `(prompt, candidate_a, candidate_b, accepted, edited_to)` di `translations` table, build fine-tune dataset.
16. **Publisher/legal-source linking** ("Where to Read" tab) — OpenNovel. → Weaver opportunity: `legal_sources = [...]` di project metadata, ditampilkan di project overview.
17. **Fuzzy TM** (similarity > 90%) — **TIDAK ADA di platform manapun**. OpenNovel reference doc menyebut ini; Weaver opportunity sebagai quick win.
18. **TMX import/export** — **TIDAK ADA di platform** (mereka proprietary). Industry standard. Weaver opportunity sebagai quick win.
19. **In-place chapter edit + word replacement** — OpenNovel. → Weaver SUDAH punya manual edit (`services/workspace_edit.py`) + TM auto-update. ✅

### 2.3 Insight Tambahan dari NovelList

NovelList (novellist.co) adalah **discovery/community companion** ke OpenNovel, bukan translator terpisah. Insight yang relevan untuk Weaver:

- **Forums per-novel** — diskusi per-novel, glossary tab community-curated. → Weaver tidak butuh ini (single-user tool), tapi inspired **novel-level metadata** (`legal_sources`, `publisher`, `cover_url`).
- **"Where to Read" tab** — link ke legal raw sources (Ridi, Munpia, Kakao, jjwxc). → Weaver bisa punya `legal_sources` field di project.toml. Promote publisher-friendly stance.
- **Cover image linking** — readers attach official cover art. → Weaver project sudah support cover via EPUB import; expose `cover_url` override di project metadata.

---

## 3. Detailed Review: Weaver Current State vs OpenNovel Pattern

Tabel lengkap: apa yang Weaver SUDAH punya, apa yang BELUM, dan effort estimate.

| # | Capability | opennovel-ref | OpenNovel/Omni | **Weaver** | Gap | Effort |
|---|---|---|---|---|---|---|
| 1 | Glossary (terms) | ✓ | ✓ | ✅ **Strong** | priority field, packs | M |
| 2 | Character DB | ✓ | ✓ | ✅ **Thin** | description, voice, aliases, pronouns | S |
| 3 | Translation Memory (exact) | ✓ | ✓ | ✅ **Strong** | TMX I/O | S |
| 4 | Translation Memory (fuzzy) | ✓ (similarity > 90%) | ❌ | ❌ | full gap | M |
| 5 | Cross-chapter context | ✓ (Story Context) | implicit | ❌ (only 5 prev segs) | full gap | M |
| 6 | Project summary (LLM-summarized) | implicit | ❌ | ❌ | full gap | M |
| 7 | Translation Profile (style) | ✓ | partial | ❌ (only honorifics) | full gap | S |
| 8 | Term Conventions (scoped rules) | ❌ | ✓ (Omni) | ❌ | full gap | L (Phase N) |
| 9 | Two-tier glossary scope (Global + Project) | Phase 5 | ✓ (Omni) | ❌ | full gap | M |
| 10 | Continuous entity extraction | ✓ | ✓ (per-chap) | ❌ (init only) | partial gap | S |
| 11 | Consistency validation (deterministic) | future | ✓ | ✅ **Strong** (11 rules) | LLM-based consistency | M |
| 12 | In-reader term highlight | ❌ | ✓ (Omni) | ❌ | full gap | S |
| 13 | Click-to-edit glossary from reader | ❌ | ✓ (Omni) | ❌ | full gap | S |
| 14 | Reverse-lookup (phrase → source) | ❌ | ✓ (Omni) | ❌ | full gap | S |
| 15 | Auto-substitute on term change | ❌ | ✓ (Omni) | ❌ | full gap | M |
| 16 | Pre-translation glossary gate | ❌ | ✓ (OpenNovel Auto) | ❌ | partial gap | S |
| 17 | Background batch + partial-failure UX | ❌ | ✓ (both) | ⚠️ JobRegistry ✅, UX polish ❌ | UX only | S |
| 18 | Chunk-level actions (regen/enhance/edit) | ❌ | ✓ (Omni) | ⚠️ segments exists, actions partial | expose per-seg actions | S |
| 19 | ePub export | future | ✓ (both) | ✅ (`renderers/epub.py`) | none | — |
| 20 | Multilingual target lang | ❌ | ✓ (OpenNovel EN/ES) | ⚠️ `target_lang` di config, no UI | minor | S |
| 21 | Genre glossary packs | Phase 5 | ✓ (Cultivation) | ❌ | full gap | M (Phase N) |
| 22 | Per-task model routing | ❌ | ❌ | ✅ **Unique** (ADR 018) | — | **DIFF** |
| 23 | Collaborative glossary | ❌ | ❌ | ❌ | full gap | XL (out of scope) |
| 24 | Per-attempt provenance | ❌ | ❌ | ✅ **Unique** (`translations` table) | — | **DIFF** |
| 25 | AI quality judging (paired comparison) | ❌ | ✓ (Omni) | ❌ | opportunity | M (Phase N) |
| 26 | Publisher / legal-source linking | ❌ | ✓ (OpenNovel) | ❌ | opportunity | S |
| 27 | Cover image override | ❌ | ✓ (OpenNovel) | ⚠️ from EPUB import only | minor | S |
| 28 | Single-user (no auth) | implicit | ✓ (both) | ✅ (single-user per CLAUDE.md) | none | — |

**Effort legend:** S = small (1-3 days), M = medium (1-2 weeks), L = large (3+ weeks), XL = out of scope.

**Ringkasan:** 60-70% fondasi sudah ada. Gap utama:
- **HIGH**: Cross-chapter context (#5), Story summary (#6), Character profile richness (#2).
- **MEDIUM**: Fuzzy TM (#4), Continuous extraction (#10), In-reader UX (#12-15).
- **LOW (quick wins)**: TMX I/O (#3), Translation Profile (#7), Per-seg actions (#18).

---

## 4. Proposed Roadmap (Realistis dengan Hard Rules Weaver)

Hard rules yang harus dihormati (CLAUDE.md §3.4/§3.5 + ADR 018 D9):
- ❌ No circuit breaker
- ❌ No health-score formula
- ❌ No presets
- ❌ No cost/observability dashboard
- ❌ No `routing_decisions` ledger
- ❌ No rotation window
- ❌ No native non-OpenAI families
- ❌ No telemetry
- ❌ No multi-user SaaS
- ❌ No cloud sync
- ❌ No external queue/worker daemon
- ✅ Protocols = `openai_chat` + `fake` only
- ✅ All AI features: explicit POST only, never on render (Gate B1)
- ✅ Single-user

Roadmap di bawah ini **mematuhi** semua hard rules di atas.

### Phase A — Quick Wins (1-2 sprints)

**Effort per item: S (1-3 days)**

1. **TMX Import/Export** (`storage/translation_memory.py` extend)
   - `weaver memory export/tmx` + `weaver memory import/tmx`
   - Mendukung format TMX 1.4b untuk interop dengan SDL Trados, OmegaT, etc.
   - Pure Python, no extra deps.

2. **Translation Profile section** (`[translation_profile]` di `project.toml`)
   - 6 fields: `tone`, `dialog_style`, `name_rendering`, `punctuation`, `tense`, `descriptive`.
   - Pure config, no schema change.
   - Update `balanced_system.txt` + `balanced_user.jinja2` untuk emit `<profile>` block.

3. **In-reader term highlight + click-to-edit** (`_segment.html` + `app.css`)
   - CSS: glossary terms bolded di translation view.
   - JS: click → opens edit modal dengan prefill source/target, POST ke existing glossary upsert endpoint.
   - Zero new infrastructure.

4. **Continuous entity extraction (opt-in)** (`services/translation.py:540-570` post-success hook)
   - New `services/entity_extraction.py` mirroring `glossary_suggestion.py` pattern.
   - Cadence config: `[memory] extraction_cadence = "off"|"per_chapter"|"per_volume"`.
   - Default: `off`. Zero behavior change.

5. **Reverse-lookup (phrase → source term)** (`workspace_context.py` extension)
   - User selects phrase di translation → POST `/segments/{id}/reverse-lookup`.
   - LLM returns most likely source term(s); offers "Add to glossary" action.

6. **Pre-translation glossary gate** (`batch_translate.py` extension)
   - `--require-glossary-reviewed` flag.
   - Refuses to start jika ada `glossary_candidates.status='pending'` count > threshold.

7. **Per-segment "regenerate (replace current)" action** (`_segment.html`)
   - Tambah button next to existing "Suggest another translation".
   - Reuse `translate_one_segment` dengan `force=True` flag.

8. **`legal_sources` field di project.toml**
   - `legal_sources = ["https://www.example.com/novel/123"]` di `[project]` table.
   - Display di project overview (`project.html`).

### Phase B — Story Context (1-2 sprints)

**Effort per item: M (1-2 weeks)**

9. **Cross-chapter rolling window** (`services/story_context.py` + prompt block)
   - Last K translated segments across project, filtered by entity overlap (substring match JP proper nouns dari current chapter).
   - Hard cap: 800 tokens.
   - New `<story_context>` block di `balanced_user.jinja2`.
   - In-memory cache (LRU per project, key = `project_id`).
   - Config: `[memory] cross_chapter_window = 5` (default 5 segments, max 20).
   - **Bypass on TM hit** (sama seperti existing context).
   - **Membutuhkan ADR baru** (cross-chapter context bukan di roadmap saat ini).

10. **Project summary (LLM-summarized)** (`services/story_summarizer.py` + new `story_summaries` table)
    - `complete()` call untuk summarize last N translated segments.
    - Cadence: per-chapter close atau per-N segments (default N=20).
    - Stored in `story_summaries(project_id, chapter_id, summary, created_at)`.
    - Injected as `<story_summary>` block di prompt.
    - **Same `complete()` primitive** sebagai `glossary_suggestion.py`.
    - Cadence config: `[memory] summary_cadence = 0` (default off).

11. **Character profile extension (migration v13)** (`storage/schema.sql` + `services/characters.py`)
    - New fields: `description`, `voice_style`, `aliases_json`, `pronouns`, `first_intro_chapter_id`, `updated_at`.
    - Update `<characters>` block di prompt untuk include voice_style + description.
    - Backward compat: existing rows render existing prompt unchanged.
    - New `_characters.html` section di project page.

12. **Glossary term priority** (`glossary.terms` add `priority` boolean)
    - `priority = true` → emit dengan tag `#important` di prompt block.
    - UI: checkbox di `_glossary_terms.html` edit row.

### Phase C — Sophisticated Features (2-3 sprints)

**Effort per item: M-L**

13. **Fuzzy TM** (`storage/translation_memory.py` extend + `services/translation.py:495-509`)
    - Normalized-prefix index (lowercase, strip punctuation, first 50 chars).
    - Lookup tier: exact → normalized → fuzzy (token overlap ratio > 0.85).
    - Pure Python, no embeddings, no extra deps.
    - Cap ke 1 fuzzy candidate + warn ke user ("Low confidence: applied 0.87 similarity match").

14. **Two-tier glossary scope (Global + Project)** (`~/.weaver/global_glossary.toml`)
    - Global glossary di-load saat project init.
    - Per-project terms override global.
    - UI: separate tab di glossary page untuk "Global" vs "Project" entries.
    - **Ini bukan multi-user** — global glossary adalah user-level (single-user Weaver install), bukan shared.

15. **Auto-substitute on term change** (`storage/translation_memory.py` + new CLI)
    - `weaver memory rewrite --source X --target Y` → walks all `translations.text` di project, replaces X → Y, with confirmation prompt.
    - Backs up to `translations.text.bak` sebelum write.
    - Documents limitation: gendered pronouns & inflections may break (text replacement, not linguistic).

16. **LLM-based consistency validation** (`services/consistency_llm.py` + new QA check type)
    - New QA check: `cross_chapter_name_drift` — uses `complete()` to detect name spelling drift across chapters.
    - On-demand endpoint: `POST /ui/.../qa/llm-consistency` (explicit click, Gate B1 compliant).
    - Cost visible di response.

### Phase D — Differentiation & Polish (3+ sprints)

**Effort per item: L**

17. **Genre glossary packs** (`weaver/glossary_packs/`)
    - Shipped TOML: `cultivation-xianxia.toml`, `modern-romance.toml`, `scifi.toml`.
    - `weaver glossary pack install <name>` → copies ke project.
    - Community contribution via PR ke Weaver repo.

18. **Term Conventions (scoped rules)** (`[translation_profile.conventions]` array)
    - Array of plain-English rules: `[{rule: "Always transliterate character names", scope: {type: "character"}, action: "transliterate"}]`.
    - Injected as `<conventions>` block di prompt.

19. **AI quality judging (paired comparison)** (`translation_quality_votes` table)
    - Track `(prompt, candidate_a, candidate_b, accepted, edited_to)` di new table (migration v14).
    - Hook di `_segment.html`: "Which is better?" buttons setelah regenerate.
    - Builds fine-tune dataset over time.

20. **Audit trail / per-attempt provenance UI** (extend `segment_history`)
    - Surface `raw_response`, `provider`, `model`, `input_tokens`, `output_tokens` di segment history view.
    - Already ada di `translations` table; hanya expose.

---

## 5. Concrete Implementation Anchors (File:Line)

Setiap rekomendasi di Phase A-C punya anchor spesifik di codebase Weaver. Di bawah ini quick-reference.

### 5.1 Quick Wins

| # | Item | Primary files | Lines (anchor) |
|---|---|---|---|
| 1 | TMX I/O | `src/weaver/services/translation_memory.py` `src/weaver/storage/translation_memory.py` `src/weaver/cli/main.py` | add `export_tmx()`, `import_tmx()`; new CLI subcommands |
| 2 | Translation Profile | `src/weaver/core/config.py` `src/weaver/providers/templates/balanced_system.txt` `src/weaver/providers/templates/balanced_user.jinja2` | extend `[translation_profile]` parse; emit `<profile>` block |
| 3 | In-reader term highlight | `src/weaver/api/templates/partials/_segment.html` `src/weaver/api/static/app.css` `src/weaver/api/routers/glossary.py` | CSS bold; JS click handler; existing upsert route |
| 4 | Continuous entity extraction | `src/weaver/services/translation.py:540-570` `src/weaver/services/entity_extraction.py` (new) | post-success hook; new service mirrors `glossary_suggestion.py` |
| 5 | Reverse-lookup | `src/weaver/services/workspace_context.py` `src/weaver/api/routers/translate.py` | new `find_source_term()`; new POST endpoint |
| 6 | Pre-translation gate | `src/weaver/services/batch_translate.py` `src/weaver/cli/main.py` | add `--require-glossary-reviewed` flag; check pending candidates |
| 7 | Per-segment regenerate | `src/weaver/api/templates/partials/_segment.html` `src/weaver/services/workspace_translate.py` | new button + new POST route |
| 8 | `legal_sources` field | `src/weaver/core/config.py` `src/weaver/api/templates/project.html` | parse + display |

### 5.2 Story Context

| # | Item | Primary files | Notes |
|---|---|---|---|
| 9 | Cross-chapter window | `src/weaver/services/story_context.py` (new) `src/weaver/providers/templates/balanced_user.jinja2` `src/weaver/services/translation.py:83-150` | new service + new prompt block; bypass on TM hit |
| 10 | Project summary | `src/weaver/services/story_summarizer.py` (new) `src/weaver/storage/schema.sql` (new table) `src/weaver/services/translation.py:540-570` | migration v13; new service uses `complete()` primitive |
| 11 | Character profile extension | `src/weaver/storage/schema.sql` `src/weaver/services/characters.py` `src/weaver/api/templates/partials/_characters.html` | migration v13; backward-compat |
| 12 | Glossary priority | `src/weaver/storage/glossary.py` `src/weaver/api/templates/partials/_glossary_terms.html` | add `priority` boolean |

### 5.3 Sophisticated Features

| # | Item | Primary files | Notes |
|---|---|---|---|
| 13 | Fuzzy TM | `src/weaver/storage/translation_memory.py` `src/weaver/services/translation.py:495-509` | normalized-prefix index; tiered lookup |
| 14 | Two-tier glossary | `src/weaver/core/global_config.py` `src/weaver/services/glossary.py` `src/weaver/api/templates/partials/_glossary_terms.html` | global file + per-project override |
| 15 | Auto-substitute on term change | `src/weaver/services/translation_memory.py` `src/weaver/cli/main.py` | new CLI; with backup |
| 16 | LLM consistency validation | `src/weaver/services/consistency_llm.py` (new) `src/weaver/qa/consistency_checks.py` `src/weaver/api/routers/ui_qa.py` | new QA check type + new endpoint |

---

## 6. Differentiation Opportunities (vs OpenNovel & OmniTranslate)

Ini yang **tidak ada** di platform manapun dan **Weaver sudah punya atau bisa bangun dengan effort rendah**:

### 6.1 Per-Task Model Routing (SUDAH ADA)

ADR 018 — `[routing.<task>]` allows different connection/model untuk `translate`, `glossary_suggest`, `candidate`. **Tidak ada di OpenNovel/OmniTranslate.** Lead dengan ini di marketing Weaver.

Example:

```toml
[routing.translate]
connection = "deepseek-prod"
model = "deepseek-chat"

[routing.glossary_suggest]
connection = "claude-prod"
model = "claude-3-5-sonnet-20241022"

[routing.candidate]
connection = "gpt-prod"
model = "gpt-4o-mini"
```

**Use case:** Claude lebih bagus untuk creative translation, GPT lebih bagus untuk structured JSON (glossary extraction), DeepSeek lebih murah untuk bulk. OpenNovel/OmniTranslate: satu model per call.

### 6.2 Per-Attempt Provenance & Audit Trail (SUDAH ADA)

`translations` table append-only dengan `raw_response`, `input_tokens`, `output_tokens`, `provider`, `model`, `created_at`. **OpenNovel/OmniTranslate: tidak ada audit trail.**

**Use case:** debugging "kenapa chapter 50 hallucinate?" → buka segment history → lihat raw response + token usage. Bandingkan dengan attempt #2.

### 6.3 Append-Only Translation History (SUDAH ADA)

Setiap attempt = new row dengan `attempt` counter. **OpenNovel: overwrites.** Weaver: track evolution of translation over time.

**Use case:** user regenerate segment 5x → bisa compare semua versi. Plus, manual edit = source of truth (`protect_manual=True`).

### 6.4 Review Status Independent of Translation Status (SUDAH ADA)

`segments.review_status` (`not_reviewed|needs_review|needs_revision|approved|rejected`) **independen** dari `segments.status` (`pending|in_progress|translated|failed|manual|stale`). **OpenNovel: implicit review (no formal status).**

**Use case:** translator workflow = translate → review → approve. Auditor workflow = read → flag needs_revision. Dua workflow di tool yang sama.

### 6.5 Manual Edit as Source of Truth (SUDAH ADA)

`protect_manual=True` blocks provider overwrites. **OpenNovel/OmniTranslate: provider always wins.** Weaver: human wins.

**Use case:** kalau user spent 30 min editing segment by hand, AI tidak boleh overwrite di batch translate berikutnya.

### 6.6 Per-Project Thresholds (SUDAH ADA)

`[qa]` table di `project.toml` allows per-project QA thresholds. **OpenNovel/OmniTranslate: global thresholds only.**

**Use case:** wuxia project allow longer segments (descriptive), light novel project stricter length ratio.

### 6.7 Segment-Level Fallback with Cold-Mark (SUDAH ADA)

30s cold-mark saat engine failed. **OpenNovel: tidak ada fallback.** **OmniTranslate: simple fallback, no cold-mark.** Weaver: try-next + 30s cooldown per engine.

**Use case:** kalau deepseek down, otomatis fall back ke claude untuk next 30s tanpa loop retry.

### 6.8 Honorific Policy Per-Project (SUDAH ADA)

`[translation] honorifics = preserve|localize|hybrid`. **OpenNovel: global setting only.** Weaver: per-project.

**Use case:** preserve honorifics untuk wuxia, localize untuk light novel. Switch project = switch policy otomatis.

### 6.9 Existing Glossary AI Suggestion (SUDAH ADA)

`complete()`-based ephemeral suggestion (ADR 014), strict JSON, never persisted. **OpenNovel: suggestions persisted to glossary, harder to undo.** Weaver: ephemeral, always validated, one click.

### 6.10 Per-Scope QA (SUDAH ADA)

QA report at novel / volume / chapter / segment scope. **OpenNovel/OmniTranslate: chapter-level only.** Weaver: rollup novel → drilldown volume → drilldown chapter → drilldown segment.

**Use case:** "novel punya 3 critical issues" → "all in volume 2" → "all in chapter 7" → "specific segment failed".

---

## 7. Yang HARUS TIDAK Dilakukan (sesuai Hard Rules)

Sesuai ADR 018 D9 dan CLAUDE.md §3.4/§3.5:

- ❌ **No circuit breaker** — fallback sederhana (try-next + 30s cold-mark) sudah cukup.
- ❌ **No health-score formula** — health = last Test-probe result. Simple.
- ❌ **No presets** — user define connection + routing secara eksplisit.
- ❌ **No cost/observability dashboard** — token usage ditampilkan per-segment, bukan aggregated dashboard.
- ❌ **No `routing_decisions` ledger** — `translations` table sudah ada; tidak perlu ledger terpisah.
- ❌ **No rotation window** — manual switch via UI.
- ❌ **No native non-OpenAI families** — protocols = `openai_chat` + `fake` only.
- ❌ **No telemetry** — no phone-home.
- ❌ **No multi-user SaaS** — single-user per install.
- ❌ **No cloud sync** — local-first.
- ❌ **No external queue/worker daemon** — in-process JobRegistry.
- ❌ **No auto AI feature on render** — Gate B1: explicit POST only.

**PENTING:** setiap rekomendasi di Phase A-D di Section 4 harus lulus aturan di atas. Misalnya:
- Recommendation #4 (continuous extraction): default `off`, opt-in via config.
- Recommendation #9 (cross-chapter context): bypass on TM hit, no provider call when no overlap.
- Recommendation #10 (project summary): cadence config, off by default.
- Recommendation #16 (LLM consistency): on-demand endpoint, explicit click.

---

## 8. Prioritization Summary

### MUST (Phase A — 1-2 sprints)
Effort: rendah, impact: langsung terasa.

1. Translation Profile (`[translation_profile]`)
2. In-reader term highlight + click-to-edit
3. Continuous entity extraction (opt-in)
4. TMX Import/Export
5. Per-segment regenerate action
6. `legal_sources` field
7. Pre-translation glossary gate
8. Reverse-lookup

### SHOULD (Phase B — 1-2 sprints)
Effort: medium, impact: high (long-novel consistency).

9. Cross-chapter rolling window (NEW ADR)
10. Project summary (LLM-summarized, opt-in)
11. Character profile extension (migration v13)
12. Glossary term priority

### COULD (Phase C — 2-3 sprints)
Effort: medium-high, impact: medium.

13. Fuzzy TM
14. Two-tier glossary scope
15. Auto-substitute on term change
16. LLM-based consistency validation

### WON'T (out of scope, atau differentiation opportunities)
- Multi-user / collaboration (out of scope per CLAUDE.md)
- Circuit breaker / health score (rejected per ADR 018 D9)
- Cost dashboard (rejected per ADR 018 D9)
- Native non-OpenAI families (rejected per ADR 018 D9)

### DIFFERENTIATION (Phase D)
- Genre glossary packs
- Term Conventions (scoped rules)
- AI quality judging
- Audit trail UI

---

## 9. Expected Outcome

Dengan roadmap di atas, Weaver akan:

1. **Menjaga konsistensi** nama, istilah, dan konteks cerita lintas chapter (Phase B).
2. **Memperkaya profile** karakter dan translation style (Phase A + B).
3. **Mempercepat editing** dengan in-reader UX dan continuous extraction (Phase A).
4. **Mendukung interop** dengan industri lokalisasi via TMX (Phase A).
5. **Menjaga simplicity** Weaver — tidak jadi SaaS, tidak jadi Telemetry-heavy, tidak jadi Multi-user. Local-first, single-user, OpenAI-protocol only.

Yang paling penting: **Weaver tetap Weaver**. Hard rules dihormati. Differentiation (per-task routing, provenance, manual-as-truth) tetap menjadi selling point. Phase B (cross-chapter context) adalah **game-changer** untuk long-novel use case, tapi butuh ADR baru dan diskusi owner.

---

## 10. Next Steps

1. **Diskusi owner**: prioritas mana yang paling penting. Rekomendasi saya: mulai dengan Phase A #1 (Translation Profile) dan #2 (In-reader highlight) — effort rendah, impact langsung terasa, tidak butuh ADR baru.
2. **ADR baru** untuk Phase B #9 (Cross-chapter context) — diskusi risk + cost.
3. **Update opennovel-reference.md** dengan findings dari research (Section 2 di proposal ini).
4. **Sprint planning** untuk Phase A items.

---

**Lampiran:** Research report lengkap tentang opennovel.co, novellist.co, dan OmniTranslate ada di catatan research. Detail file:line anchor di Section 5.
