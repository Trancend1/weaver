# Ideal User Journey

## 1. First-Time Experience

Saat pertama kali membuka Weaver, pengguna masuk ke halaman:

### AI Connections

Tampilan awal:

```
No AI Connected

Connect your first AI provider.
```

Aksi yang tersedia:

```
+ Add Connection
```

---

## 2. Menambahkan AI Connection

Form dibuat sesederhana mungkin.

### Connection Information

**Connection Name**

```
OpenRouter
```

**Endpoint**

```
https://openrouter.ai/api/v1
```

**API Key**

```
********
```

### Actions

```
[Test Connection]
```

Jika berhasil:

```
✓ Connected

145 Models Available
Latency: 320 ms
```

Kemudian:

```
[Save]
```

Selesai.

### Yang Tidak Perlu Diketahui User

User tidak perlu memahami konsep teknis seperti:

* Protocol
* Adapter
* Provider Type
* Engine

Semua kompleksitas tersebut harus disembunyikan oleh sistem.

---

## 3. Setelah AI Terhubung

Halaman **Connections** menampilkan daftar koneksi yang tersedia.

### Example

#### OpenRouter

```
✓ Healthy
145 Models
```

#### Gemini

```
✓ Healthy
32 Models
```

#### Ollama

```
✓ Local
8 Models
```

### Expected User Actions

Untuk setiap connection, user hanya membutuhkan:

* Check Status
* Refresh Models
* Edit
* Disable
* Delete

Tidak lebih dari itu.

---

## 4. Saat Membuat Project Baru

### Create Project Wizard

Langkah berikutnya:

### Choose AI

Bukan:

* Choose Provider
* Choose Protocol
* Choose Model

Melainkan langsung menampilkan model yang dapat digunakan:

* DeepSeek V3
* Claude Opus
* GPT-5.5
* Gemini Pro

Karena pengguna berpikir dalam **model**, bukan dalam **provider**.

---

## 5. Saat Sedang Bekerja

Pada header project ditampilkan AI yang sedang aktif.

### Current AI

```
DeepSeek V3
via OpenRouter
```

Tersedia tombol:

```
[Switch AI]
```

Ketika diklik:

### Available AI

```
○ DeepSeek V3
○ Claude Opus
○ GPT-5.5
○ Gemini Pro
○ Qwen3 Local
```

User memilih salah satu model.

Perubahan langsung diterapkan tanpa harus membuka halaman Settings atau konfigurasi tambahan.

---

# UX Principle

### User Thinks in Models

Pengguna memilih AI berdasarkan kemampuan model yang ingin digunakan, bukan berdasarkan provider atau detail teknis infrastruktur.

### Progressive Disclosure

Detail teknis seperti provider, endpoint, protocol, adapter, dan engine hanya muncul ketika memang diperlukan.

### One-Click Switching

Mengganti AI harus menjadi aksi cepat yang dapat dilakukan langsung dari workspace tanpa mengganggu alur kerja.

### Connection as Infrastructure

Connection berfungsi sebagai lapisan infrastruktur yang dikelola sekali, lalu digunakan kembali oleh seluruh project.
