import os
import requests
import feedparser
from supabase import create_client
from bs4 import BeautifulSoup

# ===================== 环境变量 =====================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
WECHAT2RSS_URL = os.getenv("WECHAT2RSS_URL")
WECHAT2RSS_KEY = os.getenv("WECHAT2RSS_KEY")

# ===================== 连接数据库 =====================
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    print("✅ 数据库连接成功")
except Exception as e:
    print("❌ 数据库连接失败:", e)
    supabase = None

# ===================== 获取公众号列表 =====================
def get_accounts():
    url = f"{WECHAT2RSS_URL}/list?page=1&size=100&k={WECHAT2RSS_KEY}"
    print("🔗 请求公众号列表:", url)

    try:
        res = requests.get(url, timeout=15)
        print("✅ 状态码:", res.status_code)
        data = res.json()

        accounts = data.get("data", [])
        if not accounts:
            print("📭 公众号列表为空")
        return accounts

    except Exception as e:
        print("❌ 获取公众号列表失败:", e)
        return []

# ===================== 从 RSS feed 获取文章 =====================
def fetch_articles_from_feed(feed_url, account_name):
    articles = []

    try:
        feed = feedparser.parse(feed_url)

        for entry in feed.entries:
            art = {
                "title": getattr(entry, "title", ""),
                "link": getattr(entry, "link", ""),
                "published": getattr(entry, "published", ""),
                "account": account_name
            }

            if art["link"]:  # 防止空链接
                articles.append(art)

    except Exception as e:
        print(f"❌ 解析 RSS 失败 ({feed_url}):", e)

    return articles

# ===================== 获取文章详情 =====================
def get_article_data(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        res = requests.get(url, headers=headers, timeout=10)
        print("✅ 返回状态码:", res.status_code)

        if res.status_code != 200:
            return None

        soup = BeautifulSoup(res.text, "html.parser")

        title = soup.find("h1")
        title = title.text.strip() if title else ""

        content = soup.find("div", id="js_content")
        content = content.get_text(strip=True) if content else ""

        author = soup.find("a", id="js_name")
        author = author.text.strip() if author else ""

        return {
            "title": title,
            "content": content[:5000],
            "author": author
        }

    except Exception as e:
        print("❌ 获取文章数据失败:", e)
        return None

# ===================== 去重检查 =====================
def is_exist(url):
    try:
        res = supabase.table("wechat_articles") \
            .select("id") \
            .eq("url", url) \
            .execute()

        return len(res.data) > 0

    except Exception as e:
        print("❌ 去重查询失败:", e)
        return False

# ===================== 保存文章 =====================
def save_to_db(article):
    if not supabase:
        print("❌ 数据库未连接")
        return

    url = article.get("link")

    if not url:
        print("⚠️ 空 URL，跳过")
        return

    # ✅ 去重
    if is_exist(url):
        print("⚠️ 已存在，跳过:", url)
        return

    try:
        supabase.table("wechat_articles").insert({
            "title": article.get("title", ""),
            "url": url,
            "account_id": article.get("account", ""),  # ✅ 改这里
            "publish_time": article.get("published", "")
        }).execute()

        print("✅ 插入成功:", article.get("title"))

    except Exception as e:
        print("❌ 保存数据库失败:", e)
# ===================== 主程序 =====================
if __name__ == "__main__":
    print("🚀 开始抓取公众号文章...")

    accounts = get_accounts()
    all_articles = []

    for acc in accounts:
        feed_url = acc.get("link")
        account_name = acc.get("name", "unknown")

        if not feed_url:
            continue

        print(f"🔹 抓取公众号: {account_name}")

        articles = fetch_articles_from_feed(feed_url, account_name)
        all_articles.extend(articles)

    print(f"📝 获取到文章总数: {len(all_articles)}")

    for art in all_articles:
        print("🔹 标题:", art.get("title"))
        print("🔹 URL:", art.get("link"))
        print("🔹 公众号:", art.get("account"))
        print("🔹 发布时间:", art.get("published"))

        save_to_db(art)

    print("🏁 完成")
