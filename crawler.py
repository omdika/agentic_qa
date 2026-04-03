from playwright.sync_api import sync_playwright
import psycopg2
import time
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def save_article(conn, title, url, content, date):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO articles (title, url, content, date)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (url) DO NOTHING  -- skip kalau sudah ada
    """, (title, url, content, date))
    conn.commit()
    cur.close()

def get_article_data(page, url):
    page.goto(url, timeout=60000, wait_until="domcontentloaded")
    page.wait_for_selector("div.detail__body-text", timeout=15000)

    try:
        date = page.locator("div.detail__date").inner_text()
    except:
        date = "Tanggal tidak ditemukan"

    paragraphs = page.locator("div.detail__body-text p").all()
    text = "\n".join([p.inner_text() for p in paragraphs if p.inner_text().strip()])

    return date, text

def crawl_detik():
    conn = get_db_connection()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome")
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        page.goto("https://news.detik.com/indeks", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_selector("article.list-content__item", timeout=30000)

        articles = page.locator("article.list-content__item")
        urls = []

        for i in range(articles.count()):
            article = articles.nth(i)
            title = article.locator("h3.media__title a").inner_text()
            url = article.locator("h3.media__title a").get_attribute("href")
            urls.append((title, url))

        print(f"Ditemukan {len(urls)} artikel\n")

        saved = 0
        skipped = 0

        for title, url in urls:
            try:
                date, text = get_article_data(page, url)
                
                cur = conn.cursor()
                cur.execute("SELECT id FROM articles WHERE url = %s", (url,))
                exists = cur.fetchone()
                cur.close()

                if exists:
                    print(f"⏭️  Skip (sudah ada): {title[:50]}")
                    skipped += 1
                else:
                    save_article(conn, title, url, text, date)
                    print(f"✅ Disimpan: {title[:50]}")
                    saved += 1

            except Exception as e:
                print(f"❌ Error: {title[:50]} → {e}")

            time.sleep(1)

        browser.close()
    
    conn.close()
    print(f"\n Selesai: {saved} disimpan, {skipped} di-skip")

crawl_detik()
# ```

# ---

## 3. Dapat `DATABASE_URL` dari Supabase

# Di Supabase → **Settings** → **Database** → **Connection string** → pilih **URI** → copy, formatnya:
# ```
# postgresql://postgres:[password]@db.xxx.supabase.co:5432/postgres

#AIzaSyCvIQpQfkAsRxE6XzSEb8RqL2RNcn7ipq8 emini api key


