[![View All Projects](https://img.shields.io/badge/View_All_Projects-omdika.github.io-blue?style=flat-square&logo=github)](https://omdika.github.io/)

# News Crawler and QA Agent

Proyek ini terdiri dari dua komponen utama:
1. **Crawler**: Mengumpulkan artikel berita dari situs Detik.com menggunakan Playwright.
2. **QA Agent Otomatis**: Memverifikasi kualitas artikel dengan menghasilkan test cases, mengeksekusi verifikasi menggunakan AI (Groq) dan search engine (Tavily), serta menyimpan hasil ke database.

## Fitur

### Crawler
- Mengakses indeks berita Detik.com
- Mengumpulkan judul, URL, tanggal, dan konten artikel
- Menyimpan data ke database PostgreSQL
- Menghindari duplikasi berdasarkan URL

### QA Agent
- Membaca artikel dengan status 'pending' dari database
- Menghasilkan 3-5 test cases relevan untuk verifikasi kualitas
- Mengeksekusi test cases menggunakan:
  - Search engine (Tavily) untuk verifikasi fakta
  - Perbandingan judul-isi menggunakan AI
- Menyimpan hasil test dan update status artikel ('done', 'warning', 'flagged', atau 'error')

## Persyaratan Sistem

- Python 3.8+
- PostgreSQL database (misalnya Supabase)
- API keys untuk Groq, Tavily

## Setup

1. **Clone repository**:
   ```bash
   git clone <repository-url>
   cd crawler
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Setup environment variables**:
   - Copy `example.env` ke `.env`
   - Isi nilai-nilai yang diperlukan:
     - `DATABASE_URL`: Connection string PostgreSQL (format: `postgresql://user:password@host:port/database`)
     - `GROQ_API_KEY`: API key dari Groq
     - `TAVILY_API_KEY`: API key dari Tavily

4. **Setup database**:
   - Buat database PostgreSQL
   - Jalankan script SQL berikut untuk membuat tabel:

   ```sql
   CREATE TABLE articles (
       id SERIAL PRIMARY KEY,
       title TEXT NOT NULL,
       url TEXT UNIQUE NOT NULL,
       content TEXT,
       date TEXT,
       crawled_at TIMESTAMP DEFAULT NOW(),
       qa_status TEXT DEFAULT 'pending',  -- 'pending', 'done', 'warning', 'flagged', 'error'
       qa_result JSONB,
       qa_at TIMESTAMP
   );

   CREATE TABLE test_cases (
       id SERIAL PRIMARY KEY,
       article_id INTEGER REFERENCES articles(id),
       nama TEXT NOT NULL,
       aksi TEXT NOT NULL,
       ekspektasi TEXT NOT NULL,
       status TEXT DEFAULT 'pending'  -- 'pass', 'fail'
   );

   CREATE TABLE test_results (
       id SERIAL PRIMARY KEY,
       test_case_id INTEGER REFERENCES test_cases(id),
       output TEXT,
       evidence TEXT,
       verdict TEXT NOT NULL,  -- 'pass', 'fail'
       created_at TIMESTAMP DEFAULT NOW()
   );
   ```

## Cara Menjalankan

1. **Jalankan Crawler**:
   ```bash
   python crawler.py
   ```
   Ini akan mengumpulkan artikel terbaru dari Detik.com dan menyimpannya ke database.

2. **Jalankan QA Agent**:
   ```bash
   python auto_qa_agent.py
   ```
   Ini akan memproses artikel dengan status 'pending', menjalankan QA, dan update status.

## Struktur File

- `crawler.py`: Script untuk crawling artikel
- `auto_qa_agent.py`: Script untuk QA agent otomatis
- `qa_agent.py`: (Jika ada, mungkin versi manual)
- `requirements.txt`: Dependencies Python
- `example.env`: Template untuk environment variables
- `README.md`: Dokumentasi ini

## Catatan

- Pastikan API keys valid dan memiliki quota yang cukup
- Crawler menggunakan browser Chrome via Playwright (headless=False untuk debugging)
- QA Agent menunggu beberapa detik antar request untuk menghindari rate limit
- Status artikel: 'done' (semua pass), 'warning' (beberapa fail), 'flagged' (banyak fail), 'error' (kesalahan proses)

## Lisensi

[Tambahkan lisensi jika diperlukan]
