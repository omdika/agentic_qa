from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient
import psycopg2
import json
import os
import time

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

groq_client = Groq(api_key=GROQ_API_KEY)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

# ============================================================
# DB FUNCTIONS
# ============================================================

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def get_pending_articles(conn, limit=5):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, url, content
        FROM articles
        WHERE qa_status = 'pending'
        ORDER BY crawled_at DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    return rows

def save_test_cases(conn, article_id, test_cases):
    cur = conn.cursor()
    ids = []
    for tc in test_cases:
        cur.execute("""
            INSERT INTO test_cases (article_id, nama, aksi, ekspektasi)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (article_id, tc['nama'], tc['aksi'], tc['ekspektasi']))
        ids.append(cur.fetchone()[0])
    conn.commit()
    cur.close()
    return ids

def save_test_result(conn, test_case_id, output, evidence, verdict):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO test_results (test_case_id, output, evidence, verdict)
        VALUES (%s, %s, %s, %s)
    """, (test_case_id, output, evidence, verdict))
    cur.execute("""
        UPDATE test_cases SET status = %s WHERE id = %s
    """, (verdict, test_case_id))
    conn.commit()
    cur.close()

def update_article_status(conn, article_id, status, summary):
    cur = conn.cursor()
    cur.execute("""
        UPDATE articles
        SET qa_status = %s,
            qa_result = %s,
            qa_at = NOW()
        WHERE id = %s
    """, (status, json.dumps(summary), article_id))
    conn.commit()
    cur.close()

# ============================================================
# STEP 1: GENERATE TEST CASES
# ============================================================

def generate_test_cases(title, content):
    prompt = f"""
Kamu adalah QA Engineer senior untuk media berita Indonesia.
Baca artikel berikut dan buat test cases yang relevan untuk memverifikasi kualitasnya.

JUDUL: {title}
ISI:
{content[:2000]}

Buat 3-5 test cases yang paling penting. Fokus pada:
- Klaim angka/statistik yang perlu diverifikasi
- Nama tokoh atau lembaga yang disebut
- Kesesuaian judul dengan isi
- Klaim faktual yang bisa dicek lewat search

Respond HANYA dengan JSON array, tanpa penjelasan, tanpa markdown:
[
  {{
    "nama": "nama test case singkat",
    "aksi": "search: query yang akan dicari" atau "compare: apa yang dibandingkan",
    "ekspektasi": "hasil yang diharapkan jika artikel benar"
  }}
]
"""
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    text = response.choices[0].message.content.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)

# ============================================================
# STEP 2: EKSEKUSI TEST CASES
# ============================================================

def eksekusi_test_case(tc, title, content):
    aksi = tc['aksi']
    ekspektasi = tc['ekspektasi']

    # Aksi: search → pakai Tavily
    if aksi.startswith("search:"):
        query = aksi.replace("search:", "").strip()
        try:
            hasil = tavily_client.search(query, max_results=3)
            evidence = "\n".join([
                f"- {r['title']}: {r['content'][:200]}"
                for r in hasil['results']
            ])
        except Exception as e:
            evidence = f"Search gagal: {e}"

    # Aksi: compare → pakai LLM
    elif aksi.startswith("compare:"):
        evidence = f"Judul: {title}\nIsi: {content[:500]}"
    
    else:
        evidence = "Aksi tidak dikenali"

    # Minta LLM verdict: pass atau fail
    verdict_prompt = f"""
Kamu adalah QA Engineer. Evaluasi test case berikut:

TEST CASE: {tc['nama']}
EKSPEKTASI: {ekspektasi}
EVIDENCE YANG DITEMUKAN:
{evidence}

Apakah artikel PASS atau FAIL test case ini?
Respond HANYA dengan JSON, tanpa markdown:
{{
  "verdict": "pass" atau "fail",
  "alasan": "penjelasan singkat 1 kalimat"
}}
"""
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": verdict_prompt}],
        temperature=0.1
    )
    text = response.choices[0].message.content.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    result = json.loads(text)

    return {
        "output": result['alasan'],
        "evidence": evidence[:500],
        "verdict": result['verdict']
    }

# ============================================================
# STEP 3: AGGREGATE VERDICT
# ============================================================

def aggregate_verdict(results):
    total = len(results)
    failed = sum(1 for r in results if r['verdict'] == 'fail')
    passed = total - failed

    if failed == 0:
        status = 'done'
    elif failed >= total / 2:
        status = 'flagged'
    else:
        status = 'warning'

    return {
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "status": status
    }

# ============================================================
# MAIN
# ============================================================

def run_qa_agent():
    conn = get_db_connection()
    articles = get_pending_articles(conn, limit=5)

    if not articles:
        print("✅ Tidak ada artikel pending.")
        conn.close()
        return

    print(f"🔍 Memproses {len(articles)} artikel...\n")

    for article_id, title, url, content in articles:
        print(f"{'='*60}")
        print(f"JUDUL : {title[:70]}")
        print(f"URL   : {url}\n")

        try:
            # Step 1: generate test cases
            print("📋 Generating test cases...")
            test_cases = generate_test_cases(title, content)
            tc_ids = save_test_cases(conn, article_id, test_cases)
            print(f"   → {len(test_cases)} test cases dibuat\n")

            # Step 2: eksekusi tiap test case
            results = []
            for i, (tc, tc_id) in enumerate(zip(test_cases, tc_ids)):
                print(f"🧪 [{i+1}/{len(test_cases)}] {tc['nama']}")
                result = eksekusi_test_case(tc, title, content)
                save_test_result(conn, tc_id, result['output'], result['evidence'], result['verdict'])
                results.append(result)

                icon = "✅" if result['verdict'] == 'pass' else "❌"
                print(f"   {icon} {result['verdict'].upper()} — {result['output']}")
                time.sleep(2)  # hindari rate limit

            # Step 3: aggregate
            summary = aggregate_verdict(results)
            update_article_status(conn, article_id, summary['status'], summary)

            print(f"\n📊 Hasil: {summary['passed']}/{summary['total_tests']} pass → STATUS: {summary['status'].upper()}")

        except Exception as e:
            print(f"❌ Error: {e}")
            update_article_status(conn, article_id, 'error', {"error": str(e)})

        print()
        time.sleep(3)

    conn.close()
    print("🏁 QA Agent selesai.")

run_qa_agent()


# ## Contoh Output yang Dihasilkan
# ```
# ============================================================
# JUDUL : Inflasi Indonesia Naik 5% di Maret 2026
# URL   : https://news.detik.com/...

# 📋 Generating test cases...
#    → 4 test cases dibuat

# 🧪 [1/4] Verifikasi angka inflasi
#    ❌ FAIL — BPS mencatat inflasi 4.2%, bukan 5%

# 🧪 [2/4] Verifikasi narasumber Airlangga
#    ✅ PASS — Pernyataan ditemukan di sumber resmi

# 🧪 [3/4] Kesesuaian judul dengan isi
#    ✅ PASS — Judul sesuai dengan konten artikel

# 🧪 [4/4] Cek konteks data
#    ✅ PASS — Data dalam konteks yang benar

# 📊 Hasil: 3/4 pass → STATUS: WARNING