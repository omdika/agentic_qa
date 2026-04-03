# qa_agent.py

from dotenv import load_dotenv
import psycopg2
import google.generativeai as genai
import json
import os
import time
from groq import Groq
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)


# genai.configure(api_key=GEMINI_API_KEY)
# model = genai.GenerativeModel("gemini-2.0-flash")

# ============================================================
# DB FUNCTIONS
# ============================================================

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def get_pending_articles(conn, limit=10):
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

def mark_done(conn, article_id, qa_result):
    cur = conn.cursor()
    cur.execute("""
        UPDATE articles
        SET qa_status = 'done',
            qa_result = %s,
            qa_at = NOW()
        WHERE id = %s
    """, (json.dumps(qa_result), article_id))
    conn.commit()
    cur.close()

def mark_error(conn, article_id, error_msg):
    cur = conn.cursor()
    cur.execute("""
        UPDATE articles
        SET qa_status = 'error',
            qa_error = %s
        WHERE id = %s
    """, (error_msg, article_id))
    conn.commit()
    cur.close()

# ============================================================
# AI FUNCTION
# ============================================================

# def qa_analyze(title, content):
#     prompt = f"""
# Kamu adalah QA Engineer untuk media berita Indonesia.
# Analisis artikel berikut secara objektif.

# JUDUL: {title}
# ISI:
# {content[:3000]}

# Berikan penilaian dalam format JSON berikut.
# Respond HANYA dengan JSON, tanpa penjelasan, tanpa markdown.

# {{
#   "judul_relevan": true/false,
#   "alasan_judul": "penjelasan singkat",
#   "clickbait_score": 1-10,
#   "completeness_score": 1-10,
#   "ada_narasumber": true/false,
#   "sentimen": "netral/positif/negatif",
#   "ada_5w1h": true/false,
#   "flag": true/false,
#   "flag_reason": "kosong jika tidak di-flag"
# }}
# """
#     response = model.generate_content(prompt)
#     text = response.text.strip()

#     # bersihkan kalau ada backtick dari gemini
#     text = text.replace("```json", "").replace("```", "").strip()

#     return json.loads(text)

# # ============================================================
# # MAIN
# # ============================================================

def qa_analyze(title, content):
    prompt = f"""
Kamu adalah QA Engineer untuk media berita Indonesia.
Analisis artikel berikut secara objektif.

JUDUL: {title}
ISI:
{content[:3000]}

Berikan penilaian dalam format JSON berikut.
Respond HANYA dengan JSON, tanpa penjelasan, tanpa markdown.

{{
  "judul_relevan": true,
  "alasan_judul": "penjelasan singkat",
  "clickbait_score": 1,
  "completeness_score": 1,
  "ada_narasumber": true,
  "sentimen": "netral/positif/negatif",
  "ada_5w1h": true,
  "flag": false,
  "flag_reason": ""
}}
"""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    
    text = response.choices[0].message.content.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)

def run_qa_agent():
    conn = get_db_connection()
    articles = get_pending_articles(conn, limit=10)

    if not articles:
        print("✅ Tidak ada artikel pending.")
        conn.close()
        return

    print(f"🔍 Memproses {len(articles)} artikel...\n")

    for id, title, url, content in articles:
        print(f"{'='*60}")
        print(f"JUDUL : {title[:70]}")
        print(f"URL   : {url}")

        try:
            result = qa_analyze(title, content)
            mark_done(conn, id, result)

            print(f"STATUS     : ✅ Done")
            print(f"Clickbait  : {result['clickbait_score']}/10")
            print(f"Lengkap    : {result['completeness_score']}/10")
            print(f"Sentimen   : {result['sentimen']}")
            print(f"Narasumber : {'Ada' if result['ada_narasumber'] else 'Tidak ada'}")
            print(f"5W1H       : {'Ada' if result['ada_5w1h'] else 'Tidak lengkap'}")

            if result['flag']:
                print(f"⚠️  FLAG: {result['flag_reason']}")

        except Exception as e:
            mark_error(conn, id, str(e))
            print(f"❌ Error: {e}")

        print()
        time.sleep(15)  # hindari rate limit

    conn.close()
    print("🏁 QA Agent selesai.")

run_qa_agent()
