# OpenNovel-Style Translation Workflow

## Status

Proposed Insight

## Motivation

Mayoritas AI translator mampu menghasilkan terjemahan yang baik pada level chapter, namun gagal menjaga konsistensi pada novel panjang yang memiliki ratusan hingga ribuan chapter.

Masalah yang sering muncul:

- Nama karakter berubah antar chapter.
- Nama lokasi tidak konsisten.
- Istilah dunia (world-building terms) diterjemahkan berbeda-beda.
- AI lupa konteks cerita sebelumnya.
- Gelar karakter berubah.
- Dialog kehilangan gaya yang sudah terbentuk.

OpenNovel dan platform penerjemahan novel profesional umumnya mengatasi masalah ini menggunakan kombinasi:

- Persistent Memory
- Glossary
- Translation Memory
- Story Context
- Entity Extraction

Insight ini dapat diadaptasi ke Weaver sebagai fondasi fitur **Novel Translation Workspace**.

---

# Core Principle

```text
Consistency First
Creativity Second
```

Untuk novel, konsistensi lebih penting daripada variasi terjemahan.

---

# Architecture

```text
Novel Project
│
├── Source Novel
│
├── Translation Profile
│
├── Persistent Memory
│
├── Glossary
│
├── Translation Memory
│
├── Story Context
│
├── Character Profiles
│
└── Translation Engine
```

---

# Component 1 — Persistent Name Memory

## Purpose

Menjaga konsistensi nama karakter, lokasi, organisasi, item, dan skill.

## Example

Source:

```text
李晨
```

Stored Memory:

```json
{
  "character": {
    "李晨": "Li Chen"
  }
}
```

Rule:

```text
If memory exists:
Always use stored translation.
```

AI tidak diperbolehkan membuat variasi baru.

### Incorrect

```text
Li Chen
Lee Chen
Lichen
```

### Correct

```text
Li Chen
Li Chen
Li Chen
```

---

# Component 2 — Glossary

## Purpose

Menjaga konsistensi istilah dunia.

## Example

```text
灵石
筑基
金丹
元婴
```

Glossary:

| Source | Translation              |
| ------ | ------------------------ |
| 灵石   | Spirit Stone             |
| 筑基   | Foundation Establishment |
| 金丹   | Golden Core              |
| 元婴   | Nascent Soul             |

Rule:

```text
Glossary overrides model preference.
```

Jika istilah ada di glossary maka AI wajib menggunakan istilah tersebut.

---

# Component 3 — Translation Memory

## Purpose

Mengurangi variasi terjemahan pada kalimat yang berulang.

## Example

Source:

```text
Senior Brother, please wait.
```

Stored Translation:

```text
Kakak Senior, tunggu sebentar.
```

Saat kalimat serupa muncul kembali:

```text
Similarity > 90%
```

Weaver dapat menggunakan hasil sebelumnya sebagai referensi atau langsung melakukan reuse.

Benefits:

- Konsistensi dialog.
- Mengurangi biaya token.
- Mengurangi editing manual.

---

# Component 4 — Story Context Memory

## Purpose

Menjaga pemahaman konteks lintas chapter.

## Example

Stored Context:

```json
{
  "current_arc": "Demon War",
  "main_characters": ["Li Chen", "Su Yue"],
  "recent_events": ["Li Chen lost his sword", "Su Yue became sect leader"]
}
```

Saat chapter baru diterjemahkan:

```text
Context Summary
+
Current Chapter
=
Translation Prompt
```

Benefits:

- Mengurangi kesalahan referensi karakter.
- Menjaga alur cerita.
- Mengurangi hallucination.

---

# Component 5 — Character Profile Memory

## Purpose

Menyimpan atribut karakter penting.

## Example

```json
{
  "Li Chen": {
    "gender": "male",
    "title": "Young Master"
  },
  "Su Yue": {
    "gender": "female",
    "title": "Sect Leader"
  }
}
```

Benefits:

- Pronoun lebih akurat.
- Gelar tetap konsisten.
- Mengurangi kesalahan identitas karakter.

---

# Component 6 — Translation Profile

## Purpose

Menentukan gaya terjemahan pada level proyek.

## Example

### Light Novel

```json
{
  "tone": "casual",
  "dialog_style": "natural"
}
```

### Wuxia / Xianxia

```json
{
  "tone": "formal",
  "retain_honorifics": true
}
```

### Western Fantasy

```json
{
  "tone": "literary",
  "descriptive": true
}
```

Benefits:

- Konsistensi gaya antar chapter.
- Tidak perlu mengulang instruksi setiap kali translate.

---

# Component 7 — Automatic Entity Extraction

## Purpose

Mendeteksi istilah baru secara otomatis.

## Example

Chapter introduces:

```text
Crimson Tower
```

Entity belum ada di memory.

Weaver menghasilkan:

```json
{
  "type": "organization",
  "name": "Crimson Tower"
}
```

User Review:

```text
New Entity Found

[Accept]
[Reject]
```

Jika diterima:

```text
Memory Updated
```

Benefits:

- Memory berkembang secara otomatis.
- Mengurangi input manual.

---

# Translation Pipeline

```text
Open Chapter
        │
        ▼
Load Translation Profile
        │
        ▼
Load Persistent Memory
        │
        ▼
Load Glossary
        │
        ▼
Load Translation Memory
        │
        ▼
Load Story Context
        │
        ▼
Build Translation Prompt
        │
        ▼
Translate
        │
        ▼
Consistency Validation
        │
        ▼
Entity Extraction
        │
        ▼
Memory Update
        │
        ▼
Save Result
```

---

# Future Enhancements

## Consistency Checker

Memeriksa:

- Nama karakter berubah.
- Istilah glossary berubah.
- Gelar berubah.
- Pronoun tidak sesuai.

## Cross-Chapter Validation

Melakukan validasi terhadap chapter sebelumnya untuk mendeteksi inkonsistensi.

## Shared Glossary

Memungkinkan beberapa novel menggunakan glossary yang sama.

## Import / Export

Support:

- JSON
- CSV
- TMX (Translation Memory eXchange)

---

# Suggested Weaver Roadmap

## Phase 1

- Translation Profile
- Glossary
- Persistent Name Memory

## Phase 2

- Translation Memory
- Entity Extraction

## Phase 3

- Story Context Memory
- Character Profile Memory

## Phase 4

- Consistency Checker
- Cross-Chapter Validation

## Phase 5

- Shared Glossary
- Import / Export
- Advanced Localization Workspace

---

# Expected Outcome

Dengan pendekatan ini, Weaver berkembang dari sekadar AI translator menjadi platform yang mampu menangani proyek novel panjang secara konsisten dan terstruktur.

Fokus utama bukan menghasilkan terjemahan paling kreatif, tetapi menjaga kualitas, terminologi, karakter, dan konteks cerita secara konsisten dari chapter pertama hingga chapter terakhir.
