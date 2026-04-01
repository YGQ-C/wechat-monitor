import os
import requests
import feedparser
from supabase import create_client
from bs4 import BeautifulSoup
import time
from urllib.parse import quote

# ===================== 环境变量 =====================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
WECHAT2RSS_URL = os.getenv("WECHAT2RSS_URL")
WECHAT2RSS_KEY = os.getenv("WECHAT2RSS_KEY")
DAJIALA_API_KEY = os.getenv("JIZHILIAO_API_KEY")  # 注意你的环境变量名字

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
            if art["link"]:
                articles.append(art)
    except Exception as e:
        print(f"❌ 解析 RSS 失败 ({feed_url}):", e)
    return articles

# ===================== 调用极致了 API 获取文章数据 =====================
def fetch_article_stats(article_url):
    try:
        encoded_url = quote(article_url, safe='')
        api_url = f"https://www.dajiala.com/api/article?url={encoded_url}&key={DAJIALA_API_KEY}"
        res = requests.get(api_url, timeout=10)
        
        print("🔹 调用 API URL:", api_url)
        print("🔹 API 返回内容:", res.text[:200])  # 只打印前 200 字

        if res.status_code != 200:
            print("❌ 极致了 API 请求失败:", res.status_code)
            return {"read_count": 0, "like_count": 0, "comment_count": 0, "share_count": 0}

        if not res.text.strip():
            print("⚠️ 极致了 API 返回空数据:", article_url)
            return {"read_count": 0, "like_count": 0, "comment_count": 0, "share_count": 0}

        # 尝试解析 JSON
        try:
            data = res.json()
        except Exception as e:
            print("⚠️ 极致了 API 返回非 JSON 数据:", e, "URL:", article_url)
            return {"read_count": 0, "like_count": 0, "comment_count": 0, "share_count": 0}

        return {
            "read_count": data.get("read", 0),
            "like_count": data.get("zan", 0),
            "comment_count": max(data.get("comment_count", 0), 0),
            "share_count": data.get("share_num", 0)
        }
    except Exception as e:
        print("❌ 调用极致了 API 出错:", e)
        return {"read_count": 0, "like_count": 0, "comment_count": 0, "share_count": 0}

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

    if is_exist(url):
        print("⚠️ 已存在，跳过:", url)
        return

    stats = fetch_article_stats(url)

    try:
        supabase.table("wechat_articles").insert({
            "title": article.get("title", ""),
            "url": url,
            "account_id": article.get("account", ""),  # 可以改为实际 account_id 对应表
            "publish_time": article.get("published", ""),
            "read_count": stats["read_count"],
            "like_count": stats["like_count"],
            "comment_count": stats["comment_count"],
            "share_count": stats["share_count"]
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
        time.sleep(0.5)  # 避免短时间 API 调用过多

    print("🏁 完成")
