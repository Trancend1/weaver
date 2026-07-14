# Audit Teknis End-to-End — Weaver v0.7.3 (pre-implementation)

**Tanggal:** 2026-07-13 · **Baseline:** `main` @ tag `v0.7.2` + PR #56; branch audit `docs/v073-execution-plan` (commit `73b9193`)
**Metode:** verifikasi anchor kode langsung + pengukuran nyata (probe SQLite terhadap skema asli, run fake-provider 10k segmen, bench/gate repo) + cross-check terhadap audit post-release 2026-07-05 ([handoff](docs/superpowers/handoffs/2026-07-05-v072-audit-and-blocker-fixes.md)) dan [execution plan v0.7.3](docs/superpowers/specs/2026-07-05-v073-performance-execution-plan.md). Temuan F1–F8/A1–A8 dari audit itu **tidak di-derive ulang** — di sini diverifikasi masih berlaku di kode saat ini, lalu diperluas dengan temuan baru dan angka terukur.

> **Koreksi konteks prompt audit (stale):** suite saat ini **1615 test terkoleksi** (bukan 258); `google-generativeai` sudah **dihapus** dari stack di v0.7.2 (ADR 018 — hanya `openai_chat` + `fake`); provider natives gemini/ollama sudah tidak ada.

---

## 1. Executive Summary

Weaver v0.7.2 secara struktural sehat: ruff clean, pyright 0 error, 1615 test, boundary layering disiplin, tidak ada pola berbahaya (`eval`/`exec`/`shell=True`/pickle = 0 hit di `src/weaver`). Transaction shape H3 (provider call di luar transaksi WAL) terverifikasi benar di kode.

**Bottleneck #1 yang terukur** adalah pasangan F2+F3 di jalur translate:

| Pengukuran (mesin owner, 2026-07-13) | Hasil |
| --- | --- |
| Query rolling-window per ukuran tabel `translations` | 0.98 ms @1k → 5.0 @5k → 19.4 @20k → **48.1 ms @50k baris** (linear per call ⇒ **O(n²) per run**) |
| Varian CTE ter-scope chapter @50k baris | **0.177 ms** (−99.6%, ~272×) |
| Commit `synchronous=FULL` (default sekarang) vs `NORMAL` | **1.325 ms vs 0.031 ms** per commit (43×); ≥2 commit/segmen |
| Run fake-provider 10k segmen (end-to-end, fresh) | 72.9 s total; per-segmen **tumbuh 1.96×** dalam satu run (first-100 6.89 ms → last-100 13.50 ms) — kriteria exit v0.7.3 "<20% delta" **saat ini gagal 96%** |

**Untuk run live**, latensi provider (detik/segmen) tetap mendominasi — satu-satunya tuas throughput adalah bounded concurrency (M4/ADR 020). Angka di atas menentukan **skalabilitas** (novel besar/multi-volume) dan kelincahan cockpit, bukan wall-clock live.

**Temuan baru di luar ledger F/A (tidak ada di audit 2026-07-05):**

| # | Temuan | Severity |
| --- | --- | --- |
| N1 | **Bench harness rusak sejak v0.7.2**: `weaver init` kini menulis `[provider] type = ""`, sehingga `_rewrite_project_for_fake` (replace `type = "deepseek"`) no-op → budget translate/export/validate di `bench/run_performance_budgets.py` tidak bisa jalan sama sekali. Premis M1/M5 "existing budgets green" belum bisa dibuktikan sampai ini diperbaiki. | **High** (memblokir gate v0.7.3) |
| N2 | **Dead config key** `[translation] max_retries = 2` ditulis `weaver init` (`services/project.py:350`) tapi **tidak pernah dibaca** di mana pun — menyesatkan user (retry sebenarnya = default silent SDK OpenAI). Pelanggaran anti-slop §4.3. | Medium |
| N3 | **`/projects/epub-preview` melewati cap upload**: `tmp.write(await file.read())` tanpa cek `MAX_UPLOAD_BYTES` (`api/routers/projects.py:95-100`); jalur create/import punya cap 256 MiB (`services/source_intake.py:20,49`) tapi dicek **setelah** full buffering in-memory. | Medium |
| N4 | **Tidak ada guard rasio dekompresi (zip bomb)** di seluruh `src/weaver` (grep `bomb|uncompressed|ratio` = 0 relevan). EPUB ≤256 MiB terkompresi bisa mengembang berkali lipat di memori via ebooklib. | Medium |
| N5 | **Satu chapter XHTML malformed menggagalkan seluruh import**: `read_epub` menangkap `ParseError` di level buku (`readers/epub.py:134-150`), tidak ada degradasi per-chapter. | Medium |
| N6 | **Inline markup hilang saat export EPUB**: `_replace_text` membuang semua child element (`renderers/epub.py:234-237`) — `<em>/<strong>/<br/>` dalam paragraf terjemahan menjadi teks polos. | Low–Medium |
| N7 | **Estimator token 1 tok ≈ 4 char undercount CJK ~3×** (`services/translation.py:198-200`, `DRY_RUN_TOKENS_PER_CHAR=0.25`): budget window 600 "token" riilnya meloloskan ~1.5–2k token JP; estimasi dry-run ~3× terlalu rendah. | Medium |
| N8 | Furigana (`<rt>`) **dibuang** saat import (`readers/epub.py:1429-1448`) — benar untuk teks dasar, tapi ruby dengan bacaan non-standar (nuansa penulis) hilang dari konteks penerjemah. | Low |

Tidak ada temuan **Critical**. Prioritas eksekusi yang direncanakan v0.7.3 (M1→M5) **terkonfirmasi tepat sasaran oleh pengukuran ini**; tambahkan N1 (bench fix) sebagai prasyarat M1, dan N2–N5 masuk keranjang M2/M3.

---

## 2. Area 1: EPUB Import & Export Pipeline

**Arsitektur (verifikasi kode):** import = `readers/epub.read_epub()` → `DocumentIR` (ebooklib, full-load); inspeksi paralel read-only = `parse_epub_structure()` → `ParsedEpub` + snapshot 6 tabel (`epub_snapshots*`, atomik sejak Q2C). Export EPUB-sourced = `renderers/epub.render_translated_epub` (reopen source → replace text in-place via xpath tersimpan → `atomic_write_epub`); TXT/HTML-sourced = `renderers/epub_synthesis.synthesize_epub` (build fresh). `services/export_book.py` kanonik untuk UI/API; `services/export.py` legacy CLI.

**Temuan:**

1. **[Medium] N5 — corrupt/invalid EPUB gagal total, bukan per-chapter.** Bukti: `read_epub` (`readers/epub.py:121-150`) membungkus seluruh loop chapter dalam satu `try`; `_read_chapter` (`:1373`) memanggil `ElementTree.fromstring` per item — satu `ParseError` menggagalkan buku. XHTML dengan named entity non-XML (mis. `&nbsp;` tanpa DTD) adalah pemicu umum di EPUB liar. Root cause: tidak ada isolasi kegagalan per spine item. Dampak: user tidak bisa mengimpor buku yang 99% valid. Rekomendasi: tangkap `ParseError` per chapter → catat sebagai validation issue (pola `readers/epub_validation.py` sudah ada), lanjutkan chapter lain; fail hanya jika 0 chapter terbaca. Export punya masalah simetris (`renderers/epub.py:87-93` raise per file).
2. **[Medium] N3+N4 — jalur upload & bomb** (bukti di §Executive). Cap 256 MiB ada tapi (a) dicek setelah `await file.read()` full in-memory (`api/routers/projects.py:181,424`; item deferred yang sudah tercatat di plan), (b) `/epub-preview` tidak dicek sama sekali, (c) tidak ada ceiling ukuran ter-dekompresi. Rekomendasi minimal: terapkan `MAX_UPLOAD_BYTES` di preview + tolak arsip yang `sum(file_size)` (`_archive_info` sudah membaca `infolist`!) melebihi ceiling, sebelum `ebooklib.read_epub`.
3. **[Low–Medium] N6 — fidelity inline markup di export** (bukti di §Executive). Struktur blok, CSS, image, metadata, spine order **terjaga** (buku dibuka ulang dan hanya text node yang diganti); NCX dijamin ada (`_ensure_navigation_items`), TOC dibangun ulang bila `uid=None` (`_ensure_toc_entries`) — dua guard kompat reader yang benar. Yang hilang hanya inline children dalam blok yang diterjemahkan.
4. **[Low] Kompatibilitas reader (Kindle/Kobo/Apple/Calibre/dst):** struktur output memelihara package asli + NCX, secara teori aman untuk EPUB2/3 reader. **Data tidak cukup untuk disimpulkan** tanpa `epubcheck` + uji perangkat nyata — tidak ada validasi epubcheck di repo/CI. Rekomendasi: jalankan epubcheck manual pada artefak export sebagai bagian gate M5 (tanpa menambah dependency runtime).
5. **[Info] Streaming vs full-load:** ebooklib memuat seluruh arsip; untuk skala LN (puluhan MB) ini bukan masalah terukur. Re-open `ZipFile` berulang pada jalur inspeksi (`readers/epub.py:185-1229`) sudah tercatat sebagai deferred low-leverage di plan — setuju, jangan dikerjakan tanpa bukti baru.
6. **[Info] Resume:** import bersifat one-shot atomik (snapshot Q2C); resume translasi lewat status segmen + `reset_in_progress_segments` — teruji (suite + kode H3). Eksekusi duplikat dicegah TM exact-match.

## 3. Area 2: Preprocessing & Text Normalization

1. **[OK] Normalisasi** (`core/segment.py:9-20`): NFKC + collapse whitespace, dipakai konsisten untuk hashing & prompt. ID deterministik blake2b ter-scope volume (`scope_id_to_volume` — guard tabrakan antar volume identik, terdokumentasi). Stale detection = SHA-256 atas teks ternormalisasi. Solid.
2. **[Low] N8 — ruby/furigana:** `<rt>/<rp>` di-skip (`readers/epub.py:1429-1448`) sehingga base text bersih — benar. Tapi bacaan furigana dibuang total; pada kasus penulis memakai ruby untuk makna ganda (baca X tulis Y), penerjemah/LLM kehilangan sinyal. Rekomendasi (butuh keputusan produk, bukan quick fix): pertahankan reading sebagai anotasi opsional di `BlockIR`/prompt.
3. **[OK] Segmentasi** = level blok (`TEXT_BLOCK_TAGS`, paragraf/heading), bukan kalimat — cocok untuk konteks translasi LN; tidak merusak struktur EPUB karena xpath per blok disimpan di `markup_context` dan export menggantikan text node pada elemen yang sama.
4. **[OK] Tokenisasi Jepang:** fugashi/MeCab **opsional** hanya untuk ekstraksi proper-noun glossary (`services/glossary.py:230-246`) dengan fallback bersih saat tidak terpasang. Tidak di hot path translate.
5. **[Info] Deteksi nama karakter/dialog:** exact-match `jp_name` substring (`_filter_characters`, `services/translation.py:156-167`); tidak ada alias/variant matching (kanji vs kana) — gap kualitas kecil, jangan dibangun tanpa bukti kebutuhan (§4.3 gate 1).

## 4. Area 3: Translation Pipeline & Provider Orchestration

1. **[High→direncanakan M4] F1 — strictly sequential** terverifikasi (`services/translation.py:338-382`; sama di `workspace_translate`/`batch_translate`). Segmen N+1 menunggu commit N. Untuk run live inilah satu-satunya tuas wall-clock (plan §Honest impact framing — setuju). ADR 020 (Proposed, default `max_concurrent=1`) adalah jawaban yang tepat; H3 sudah membuka jalannya (provider call tanpa transaksi terbuka — diverifikasi `translation.py:517-655`).
2. **[Medium] F6 — round-trip tersembunyi**: hingga 3 network call per segmen — primer + JSON-parse-repair (`providers/openai_chat.py:95-122`) + enforcement repair (`translation.py:586-621`) — **plus** retry silent SDK (klien dibangun tanpa `max_retries`, `openai_chat.py:194-203`). Biaya repair terhitung di summary (`spent_input/spent_output`) tapi **baris DB hanya menyimpan token attempt final** (`record_translation(..., final.input_tokens)`, `:633`) → rekonsiliasi row vs summary pecah (= A5, terkonfirmasi baris demi baris). M3.2/M3.3 menutup ini.
3. **[Medium] N2 — `[translation] max_retries` dead key** (bukti §Executive): hapus dari template init **atau** wire ke `OpenAI(max_retries=...)` di M3.3 — jangan biarkan dua-duanya.
4. **[Medium] A1 — dead primary abort** meski fallback chain sehat: healthcheck primer gagal → `ProviderUnavailable` mematikan run (`translation.py:280-289`) padahal loop per-segmen (`:559-577`) mampu carry via fallback. M2.2 tepat.
5. **[OK] Fallback & cold-mark:** try-next per segmen + cold 30 s; saat semua cold, tetap dicoba (`warm or candidates`) — tidak ada blind-fail. Fallback yang gagal dibangun di-skip tanpa mematikan run (`:303-312`). Sesuai D9 (tanpa circuit breaker).
6. **[OK] Cancellation/resume/duplikat:** cooperative cancel per segmen; `finally` mengembalikan status pre-run bila exception tak terduga (`:661-674`); TM exact-match mencegah retranslasi; `use_translation_memory=False` untuk retranslate eksplisit. Timeout provider configurable per koneksi.
7. **[Info] Batching/chunking:** satu segmen = satu request by design (kualitas + atomicity); tidak ada micro-batching. Dengan M4, window bounded 1–4 sudah cukup — jangan tambah kompleksitas batching prompt tanpa eval kualitas.

## 5. Area 4: AI Context, Memory & Token Efficiency

**Anatomi prompt per segmen** (`providers/templates/balanced_user.jinja2` + `balanced_system.txt`, di-`@cache` — F8): system ±150 token tetap; `<glossary>` ≤20 term **ter-filter substring terhadap segmen** (bukan seluruh glossary — efisien); `<characters>` ≤20 ter-filter; `<context>` ≤5 pasangan (source+translation) dengan budget estimasi 600 token; `<source>`. Tidak ada konteks redundan yang tidak perlu — desainnya sudah hemat.

1. **[Medium] N7 — estimator token salah kelas karakter** (bukti §Executive). `_estimate_tokens = chars//4` dan `DRY_RUN_TOKENS_PER_CHAR = 0.25` adalah heuristik Inggris; JP ≈ 1–1.5 char/token. Konsekuensi terukur secara aritmetika: budget window "600" riil ~1.5–2k token; estimasi dry-run underestimate ~3× (mis. novel 300k char JP: estimasi 75k vs riil ±200–300k input token). Rekomendasi: heuristik dua-kelas (CJK = 1 char/token, lainnya /4) — deterministik, tanpa dependency baru; recalibrate `MAX_CONTEXT_TOKENS`.
2. **[Info — kuantifikasi redundansi]** Rolling window mengirim ulang tiap pasangan terjemahan ≤5× selama satu chapter (window 5) — overhead konteks ≈ 5×(src+tgt) per segmen, bounded by design dan dibayar untuk konsistensi. Alternatif penghematan (kirim translation-only di window, hemat ~40–50% token konteks) adalah **trade-off kualitas** — jangan diambil tanpa eval; "data tidak cukup untuk disimpulkan" efek kualitasnya.
3. **[OK] Invalidasi:** window di-query ulang dari DB per segmen dengan guard `t.source_hash = s.source_hash` (tidak pernah memakai terjemahan stale sebagai konteks — benar); TM key = `source_hash` (NFKC-stable). Cache prompt template `@cache` (F8). Tidak ada chapter memory lintas run selain TM — by design, bukan gap.
4. **[Perf — lihat Area 6]** Mekanisme *pengambilan* window-lah yang mahal (F2), bukan isinya.

## 6. Area 5: Glossary & Character Consistency Engine

1. **[Medium→M1.5] F7 — casefold di dalam loop per-term**: `_filter_glossary` (`services/translation.py:140-153`) dan `check_glossary_mismatch` (`qa/checks.py:185-220`) melakukan `normalized_source.casefold()` (dan `translation_text.casefold()`) **per term per segmen**. Hoist = O(1) per segmen. Dampak kecil vs F2 tapi gratis.
2. **[Medium→M1.5] Index hilang `glossary_candidates(project_id, source)`** — terkonfirmasi di `storage/schema.sql:80-89` (tidak ada index project). `record_uncertain_glossary_candidate` (`storage/glossary.py:203-245`) menjalankan 2 query per uncertain term per segmen di dalam transaksi commit — linear scan tabel candidates. `glossary_terms` aman (UNIQUE(project_id, source) = index).
3. **[OK] Lookup semantics:** exact substring, case-folding opsional per term; konflik ditolak pre-run (`raise_on_glossary_conflicts`); prioritas deterministik (urutan listing, cap 20 early-exit). Tidak ada fuzzy/regex — sesuai fence non-goal (fuzzy TM ditolak plan). O(terms×len) per segmen dengan cap-20 cukup untuk glossary ratusan–ribuan term; Aho-Corasick baru relevan bila ada bukti glossary >5–10k term — **data tidak cukup** untuk merekomendasikannya sekarang.
4. **[OK] Konsistensi lintas chapter:** enforcement loop ADR 019 (E1–E4) membuat glossary/karakter **binding** — deteksi + 1 bounded repair, hasil terlihat di QA. Gap yang tersisa = provenance tidak dipersist (A4, M3) dan deteksi ter-gate `enforce_repair` (A4a — terkonfirmasi `translation.py:586` kontra docstring `:709-712`).
5. **[Low] Alias/relationship mapping:** tidak ada (exact `jp_name` saja). Biarkan sampai ada bukti kebutuhan.

## 7. Area 6: Persistence Layer — Database & Cache

Semua angka diukur pada skema v12 asli (`initialize_database` + query produksi), mesin owner, 2026-07-13. Probe: `probe_scaling.py`/`probe_scoped.py` (scratchpad sesi ini).

1. **[High→M1.2] F2 — rolling-window CTE O(n²) per run — TERUKUR.** `list_previous_translated_segments` (`storage/translations.py:172-191`): CTE `GROUP BY segment_id` mengagregasi **seluruh** tabel `translations` per panggilan, dipanggil per segmen provider-bound.
   - Per query: 0.977 ms @1k → 5.03 @5k → 19.35 @20k → **48.15 ms @50k baris** (linear sempurna terhadap ukuran tabel).
   - End-to-end run fresh 10k segmen: per-segmen **6.89 ms (first-100) → 13.50 ms (last-100), growth 1.96×**.
   - Varian ter-scope chapter (filter di dalam CTE): **0.177 ms @50k** — flat, −99.6%.
   - `list_export_segment_states` (`:211-253`) memakai bentuk CTE yang sama → export ikut menskala buruk pada DB besar.
2. **[High→M1.1] F3 — `synchronous=FULL` implisit — TERUKUR.** `_open_database` (`storage/db.py:147-157`) hanya set WAL+busy_timeout+FK; default FULL. Commit kecil: **1.325 ms (FULL) vs 0.031 ms (NORMAL)** = 43×. Jalur translate = 2 commit/segmen (marker `in_progress` + hasil) → ≈26 s fsync murni per 10k segmen yang bisa jadi ≈0.6 s. Risiko NORMAL under WAL = kehilangan txn terakhir saat OS crash (bukan korupsi) — `reset_in_progress_segments` memang crash net untuk window itu. `connect_readonly_database` (`:81-104`) tanpa pragma sama sekali (busy_timeout 0 → SQLITE_BUSY saat checkpoint; M1.1 benar).
3. **[Medium→M1.3/M1.4] F4/F5 — N+1 & discovery tak ter-cache** terkonfirmasi pada anchor (`core/connection_registry.py:90-93`; `services/connections.py:191-224`; `discover_projects` dipanggil 2× per render providers-hub dan tiap 3 s oleh poll queue — `queue_hub.html:12` — sambil membuka **setiap** project DB; cache 5 s `workspace_index` kalah start). Catatan tambahan: `connect_database` menjalankan `apply_migrations` pada **setiap** open — poll queue membayar cek migrasi per project per 3 s.
4. **[Medium→M1.5] `executemany`**: `sync_document_segments` insert per-baris (`storage/segments.py:79-88`) — kontras dengan probe audit ini yang memakai `executemany` untuk 50k baris tanpa masalah.
5. **[OK] Skema & query lain:** PK `translations(segment_id, attempt)` melayani lookup attempt; `idx_segments_chapter(chapter_id, block_order)` melayani window scan; TM `UNIQUE(project_id, source_hash)` = exact lookup terindeks (F8); `raw_response` off by default menjaga ukuran DB; FK ON; migrasi forward-only + idempoten (disiplin T4 teruji di suite). Tidak ada ORM. Orphan data: tidak ditemukan jalur penulisan orphan; `job_events`/`export_history` append-only dengan index.
6. **[Low] Duplikasi cache vs DB:** satu-satunya cache derived = `connection_models.json` (TTL 6 h, workspace-level, deviasi sadar dari ADR 018 §6.1 — terdokumentasi). Klaim doc "glossary LRU cache" di `docs/SECURITY_AND_PERFORMANCE.md:183` **fiktif** (tidak pernah diimplementasi) — bersihkan saat M1 (sudah dicatat plan).

## 8. Area 7: Runtime Performance — CPU, Memory, I/O

1. **CPU:** hotspot terukur = F2 (dominan, lihat Area 6) lalu fsync F3; sisanya (casefold loop, PRAGMA `table_info` per render segmen-editor `services/workspace_context.py:171`) kecil tapi gratis diperbaiki (M1.5). Regex mahal: tidak ditemukan (pola-pola kecil, `XPATH_STEP_PATTERN` sederhana).
2. **Memory:** full-load EPUB (ebooklib) + `block_by_id` seluruh dokumen per run — pada fixture 10k blok tidak menunjukkan tekanan (run 72.9 s stabil). Upload full-buffer ≤256 MiB (N3 untuk preview); DOCX build in-memory (`renderers/docx.py:202`, deferred — setuju low-leverage). **Klaim leak/retained-object: data tidak cukup untuk disimpulkan** — belum ada tracemalloc/py-spy pada server long-running; tidak ada indikasi dari suite. Rekomendasi M5: satu sesi py-spy pada `weaver serve` selama run batch sebagai evidence.
3. **I/O:** 2 fsync commit/segmen @FULL (terukur); WAL checkpoint implisit; atomic write untuk EPUB/TOML/exports (`renderers/_atomic.py`, `_escape` TOML — lihat A2/A7 di Area 9). Temp file preview dibersihkan di `finally` (`projects.py:106-108`). Tidak ada async file I/O — tidak dibutuhkan (§3.5).

## 9. Area 8: UI Responsiveness

1. **[Medium→M1.4] Poll queue 3 s = build termahal** (F5): tiap tick membuka semua project DB + parse semua project.toml. Providers-hub render = 2× discovery + N+1 TOML (F4). Ini satu-satunya sumber "berat" berulang di UI; perbaikannya sudah di M1. Poll lain: `job_detail.html` 1 s + `_snapshot.html` 1 s — murah (baca tabel `jobs`), SSE progress di-throttle 1/dtk (F8).
2. **[OK] Tidak ada freeze:** job translate/export berjalan di thread background SQLite-backed (ADR 010); render path bebas provider/QA/hashing (Gate B1 — diverifikasi review keamanan 2026-06-16 dan konsisten dengan kode yang dibaca audit ini). Loading/empty/error states konsisten di partials.
3. **[Info] Virtual list:** tidak ada — listing segmen dipaginasi server-side; pada chapter LN (ratusan blok) cukup. Jangan tambah virtualisasi tanpa bukti jank.

## 10. Area 9: Reliability & Security

**Reliability (kegagalan sistem):**

1. **[OK — verifikasi kode]** Transaction shape H3: marker `in_progress` (txn pendek) → provider call **tanpa** txn → hasil+memory+kandidat+status **satu commit atomik**; exception path mengembalikan status semula; `reset_in_progress_segments` = crash net (`translation.py:517-674`). Tidak ada jendela korupsi data; kill keras hanya meninggalkan `in_progress` yang direklamasi run berikutnya (trade-off terdokumentasi di handoff PR #56).
2. **[Medium→M2.1] A2/A7 — corrupt `connections.toml`/`secrets.toml` musnah diam-diam** pada write berikutnya (read tolerant → write unconditional rewrite), plus 3 kopi `_escape` yang tidak meng-escape C0 control chars (`core/connection_registry.py:199-200`, `core/secret_store.py:155-156`, `services/config_writer.py:379-380`). Ini satu-satunya jalur *silent data loss* yang ditemukan. Backup-before-rewrite (M2.1) tepat.
3. **[Medium→M2.2] A1 dead-primary abort** (Area 3 #4). **[OK]** timeout provider per-koneksi; provider offline → `ProviderUnavailable` dengan pesan actionable; network failure per-segmen → `failed` + fallback chain; EPUB corrupt → lihat N5.

**Security (input jahat):** review menyeluruh permukaan v0.7.2 sudah ada ([2026-06-16 handoff](docs/superpowers/handoffs/2026-06-16-connection-routing-security-review.md)) — traversal `find_project` (Windows `\`) dan reflected-XSS **sudah diperbaiki + diregresi-test**; boundary token sesi/CORS same-origin/secret 0600 tanpa echo/HTMX relatif semuanya terverifikasi. Audit ini menambah:

4. **[Medium] N3 — `/projects/epub-preview` tanpa cap upload** (bukti §Executive). Terproteksi token sesi, tapi model ancaman lokal tetap relevan (EPUB dari internet).
5. **[Medium] N4 — zip bomb**: tidak ada ceiling dekompresi; user Weaver *memang* membuka EPUB tak tepercaya. Mitigasi murah tersedia (`_archive_info` sudah membaca `file_size` manifest — tinggal dijumlahkan dan dibatasi).
6. **[Low] Prompt injection via konten EPUB**: teks sumber masuk `<source>` prompt; EPUB jahat bisa berisi instruksi. Mitigasi eksisting memadai untuk model ancaman: respons dipaksa JSON-parse ketat (`providers/parser.py`), tidak ada tool-use, hasil selalu direview manusia, enforcement mendeteksi anomali (untranslated-JP/banned-phrase). Residual = manipulasi kualitas terjemahan segmen itu sendiri. Tidak perlu aksi selain kesadaran.
7. **[OK]** Tidak ada `eval`/`exec`/`os.system`/`subprocess(shell=True)`/pickle di `src/weaver` (grep 0 hit). Deserialisasi = tomllib/json saja. Path traversal upload: nama file di-store lewat `store_uploaded_source` (sandbox source_browser, ADR 0017). Image preview punya suite security sendiri (`test_image_preview_security.py`).

## 11. Area 10: Scalability pada Skala Realistis

Berdasarkan pengukuran nyata (bukan asumsi):

| Skala | Perilaku hari ini (terukur/terproyeksi dari probe) |
| --- | --- |
| 1 novel 10k segmen, fake | 72.9 s; per-segmen tumbuh 1.96× dalam run (F2+F3). Dengan M1: proyeksi flat ~3–5 ms/segmen (window 0.18 ms + commit 0.06 ms + overhead) → total ±30–50 s ⇒ **−40–60%** |
| DB multi-volume 50k+ baris translations | 48 ms/segmen hanya untuk query window (terukur @50k) — run lanjutan & export makin lambat **per volume yang ditambahkan**; dengan M1.2 flat 0.18 ms |
| Jutaan paragraf dalam satu DB | Ekstrapolasi linear probe: ~1 ms/1k baris ⇒ ~1 dtk/query @1M baris per segmen = tidak bisa dipakai tanpa M1.2; setelah M1.2, biaya per query hanya fungsi ukuran chapter (flat) |
| Puluhan–ratusan project di workspace | Poll queue 3 dtk membuka tiap project DB + jalankan `apply_migrations` per open (F5) — degradasi linear terhadap jumlah project; M1.4 menutupnya |
| Run live (provider nyata) | Latensi provider (0.5–5 dtk/segmen) mendominasi; F2/F3 tak terasa sampai DB besar. Throughput hanya naik lewat M4 (target terukur ≥2.4× @3 worker) |

**Bottleneck utama pada skala realistis = F2 (kuadratik), lalu F5 (linear × frekuensi poll), lalu F3 (konstanta besar).** Urutan M1 di plan sudah sesuai urutan dampak ini.

## 12. Area 11: Code Quality & Test Coverage

1. **Gate hijau (dijalankan audit ini, 2026-07-13):** `uv run ruff check .` clean; `uv run pyright src` **0 error**; suite penuh `pytest -q -m "not requires_cloud and not requires_ollama"` → **1614 passed, 1 skipped (POSIX file mode), 351.5 s**. Tidak ada TODO/FIXME debt (audit 2026-07-05). Layer boundaries dihormati (spot-check konsisten: routers tipis, writes via services, provider transport-only).
2. **Test:** 205 file test, **1615 terkoleksi** (unit mirror source tree + integration CLI/readers/providers). Kekuatan: corrupt-EPUB exit-code, security regression (traversal/XSS/secret-echo), migrasi idempoten, sidecar contract via HTTP nyata, e2e fallback-rescue, enforcement e2e.
3. **Gap coverage (bukan duplikasi effort dari 1615 yang ada):**
   - **[High→M5] N1 bench harness rusak** — kepercayaan "budget hijau" saat ini salah; perbaiki `_rewrite_project_for_fake` (tulis `[provider] type="fake"` eksplisit, jangan string-replace) sebelum M1 mengklaim baseline.
   - `requires_ollama` marker: **0 test** (`pyproject.toml:94`); Gemini live `requires_cloud` belum ada → sudah dijadwalkan M5, konfirmasi.
   - Tidak ada fuzz/property-based test (tidak ada hypothesis) untuk parser EPUB/JSON-response — nilai tertinggi ada di `providers/parser.py` dan `readers/epub_validation.py`; opsional, butuh keputusan dependency dev.
   - Counting-seam untuk N+1 (parse TOML/DB-open per render) belum ada — M1 acceptance sudah mensyaratkannya.
   - Skenario "simulasi" prompt audit yang belum ter-cover sebagai test nyata: zip-bomb ceiling (N4 — tulis saat guard dibuat), preview-cap (N3), single-chapter-malformed import degradation (N5 — tulis saat perilaku diubah; hari ini perilakunya fail-total dan *itu* ter-cover).
4. **Duplikasi/dead code:** 3 kopi `_escape` (M2.1 menyatukan); dead config key N2; klaim doc cache fiktif (§7.6). Selain itu bersih.
5. **SOLID/modularitas:** file >400 baris hanya `readers/epub.py` (~1470) dan `services/translation.py` (729) — keduanya kohesif; `translate_one_segment` >50 baris dengan justifikasi atomicity yang terdokumentasi. Tidak menemukan abstraksi single-caller baru.

---

## 13. Risk Assessment & Prioritized Roadmap

Roadmap v0.7.3 (M1–M5) **divalidasi oleh audit ini** — tidak ada perubahan urutan yang disarankan. Tambahan/penegasan di bawah.

### Quick Wins (<1 hari, estimasi dari data terukur)

| Aksi | Bukti/estimasi dampak |
| --- | --- |
| **Perbaiki bench harness (N1)** — prasyarat semua klaim baseline | Membuka kembali budget translate/export; tanpa ini M1/M5 tidak punya baseline sah |
| `PRAGMA synchronous=NORMAL` + pragma readonly (M1.1) | **−97% biaya commit** (1.325→0.031 ms terukur); ≈−26 s/10k segmen; readonly busy_timeout menghilangkan SQLITE_BUSY sporadis |
| CTE ter-scope chapter (M1.2, kedua call site) | **−99.6% per query @50k** (48.1→0.18 ms terukur); growth run 1.96× → target <1.2× |
| Hoist casefold, `executemany`, index `glossary_candidates`, cache `table_info` (M1.5) | Terverifikasi ada; dampak individual kecil — "data tidak cukup" untuk % per item, tapi arah pasti positif dan zero-risk |
| Hapus atau wire `[translation] max_retries` (N2) | Koreksi kejujuran konfigurasi; 0 biaya |
| Terapkan `MAX_UPLOAD_BYTES` di `/epub-preview` (N3) | 3 baris; menutup bypass |

### Mid-term (1–2 minggu)

| Aksi | Catatan |
| --- | --- |
| M1.3/M1.4 (F4/F5): single-parse registry + discovery di bawah cache 5 s + ≤1 DB open/project/poll | Estimasi: providers-hub dari O(2N discovery + N+1 parse) → O(1) parse per file; % wall-clock **tidak cukup data** sampai counting-seam ada (M1 acceptance) |
| M2.1–M2.4 (A1/A2/A3/A7/A8) | Menutup satu-satunya silent-data-loss + dead-primary + brand history + inspect |
| M3.1–M3.3 (A4/A5 + F6): deteksi ungated, migration v14 provenance (v13 dipakai M1.5 untuk index glossary_candidates), `max_retries` eksplisit + hitung repair round-trips | Membuat biaya tersembunyi terlihat (gate §4.3 #6); prasyarat keputusan default `enforce_repair` |
| Estimator token CJK-aware (N7) | Deterministik, tanpa dependency; recalibrate `MAX_CONTEXT_TOKENS` setelahnya |
| Zip-bomb ceiling via manifest `file_size` (N4) + test | Murah karena `_archive_info` sudah ada |
| Import degradasi per-chapter (N5) + test | Ubah kontrak error → butuh keputusan produk kecil (chapter rusak = validation issue, bukan fail-total) |

### Long-term Refactor

| Aksi | Catatan |
| --- | --- |
| M4 bounded concurrency (ADR 020 harus Accepted dulu) | Satu-satunya tuas throughput live; target terukur ≥2.4× @3 worker; enabler FakeProvider latency knob dulu (M4.1) |
| Preservasi inline markup pada export (N6) | Butuh desain: terjemahan flat vs markup — kemungkinan placeholder-marker di prompt; **jangan** dikerjakan tanpa eval kualitas |
| Validasi epubcheck + matriks reader di gate rilis | Dev-tooling saja, bukan dependency runtime |
| Anotasi furigana opsional di IR/prompt (N8), alias karakter | Fitur kualitas — lewat gate §4.3 (real pain dibuktikan dulu) |

### Estimasi peningkatan performa (hanya yang terukur/terproyeksi dari data nyata)

- **Jalur fake/lokal 10k segmen:** 72.9 s → proyeksi ±30–50 s setelah M1.1+M1.2 (**−40–60%**; komposisi: −26 s fsync terukur + eliminasi growth window terukur). Angka pasti dikunci oleh bench M5.
- **Query konteks pada DB 50k baris:** −99.6% (terukur langsung, 48.1→0.18 ms).
- **Growth intra-run:** 1.96× → <1.2× (kriteria exit; probe flat-cost sudah tersedia dari audit ini untuk dipakai ulang di `bench/`).
- **Run live:** M1 ≈ netral terhadap wall-clock (latensi provider dominan); M4 = **2.4–3×** (target ADR 020, harus dibuktikan bench + spot-check live).
- **Cockpit render/poll:** arah pasti positif; **tidak cukup data untuk %** sampai counting-seam M1 terpasang.

---

*Probe audit (dapat direproduksi): `probe_scaling.py`, `probe_scoped.py`, `probe_flatcost.py` — scratchpad sesi 2026-07-13; skema v12 asli via `initialize_database`; fixture `bench/generate_synthetic_fixture` (200 chapter / 10k blok). Suite penuh dijalankan pada sesi yang sama.*
