# import os
# import requests
# from supabase import create_client

# # ===================== 环境变量 =====================
# SUPABASE_URL = os.getenv("SUPABASE_URL")
# SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
# JIZHILIAO_API_KEY = os.getenv("JIZHILIAO_API_KEY")
# WECHAT2RSS_URL = os.getenv("WECHAT2RSS_URL")
# WECHAT2RSS_KEY = os.getenv("WECHAT2RSS_KEY")

# # ===================== 连接数据库 =====================
# try:
#     supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
# except Exception as e:
#     print("数据库连接失败:", e)
#     supabase = None

# # ===================== 【最终正确接口】 =====================
# def get_articles():
#     url = f"{WECHAT2RSS_URL}/list?page=1&size=100&k={WECHAT2RSS_KEY}"
#     print("🔗 请求地址:", url)

#     try:
#         res = requests.get(url, timeout=15)
#         print("✅ 状态码:", res.status_code)
#         if res.status_code == 200:
#             data = res.json()
#             return data.get("list", [])
#         return []
#     except:
#         return []

# # ===================== 获取阅读量 =====================
# def get_article_data(article_url):
#     try:
#         resp = requests.get(
#             "https://www.dajiala.com/api/article/data",
#             params={"url": article_url},
#             headers={"Authorization": JIZHILIAO_API_KEY},
#             timeout=10
#         )
#         data = resp.json()
#         return data.get("read",0), data.get("like",0), data.get("comment",0)
#     except:
#         return 0,0,0

# # ===================== 保存数据库 =====================
# def save_to_db(article):
#     if not supabase:
#         return

#     title = article.get("title", "")
#     url = article.get("url", "")
#     publish_time = article.get("created_at", "")
#     account_name = article.get("account_name", "unknown")

#     if not title or not url:
#         return

#     read, like, comment = get_article_data(url)

#     try:
#         supabase.table("wechat_articles").upsert({
#             "title": title,
#             "url": url,
#             "publish_time": publish_time,
#             "account_id": account_name,
#             "read_count": read,
#             "like_count": like,
#             "comment_count": comment
#         }, on_conflict="url").execute()
#         print(f"✅ 已保存: {title}")
#     except:
#         pass

# # ===================== 主程序 =====================
# if __name__ == "__main__":
#     print("🚀 开始抓取...")
#     articles = get_articles()

#     if not articles:
#         print("📭 无文章")
#     else:
#         print(f"📝 文章数量: {len(articles)}")
#         for art in articles:
#             save_to_db(art)

#     print("🏁 完成")
import os
import requests
import feedparser
from supabase import create_client

# ===================== 环境变量 =====================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
JIZHILIAO_API_KEY = os.getenv("JIZHILIAO_API_KEY")
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
        print("📦 返回原始 JSON:", data)

        accounts = data.get("data", [])
        if not accounts:
            print("📭 公众号列表为空，请确认 RSS_TOKEN 正确且后台有账号")
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
            articles.append({
                "title": entry.title,
                "url": entry.link,
                "publish_time": entry.get("published", ""),
                "account_name": account_name
            })
    except Exception as e:
        print(f"❌ 解析 RSS feed 失败 ({feed_url}):", e)
    return articles

# ===================== 获取阅读量/点赞/评论 =====================
import requests

import requests
from bs4 import BeautifulSoup

def get_article_data(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        res = requests.get(url, headers=headers, timeout=10)
        print("✅ 返回状态码:", res.status_code)

        if res.status_code != 200:
            print("❌ 请求失败")
            return None

        html = res.text

        # 解析 HTML
        soup = BeautifulSoup(html, "html.parser")

        # 标题
        title = soup.find("h1")
        title = title.text.strip() if title else "无标题"

        # 正文
        content = soup.find("div", id="js_content")
        content = content.get_text(strip=True) if content else ""

        # 作者
        author = soup.find("a", id="js_name")
        author = author.text.strip() if author else ""

        return {
            "title": title,
            "content": content[:5000],  # 防止过长
            "author": author,
            "url": url
        }

    except Exception as e:
        print("❌ 获取文章数据失败:", e)
        return None

# ===================== 保存文章到 Supabase =====================
def save_to_db(article):
    url = article["link"]

    data = get_article_data(url)
    if not data:
        print("❌ 获取文章失败")
        return

    content = data.get("content", "")
    author = data.get("author", "")

    try:
        res = supabase.table("articles").insert({
            "title": article["title"],
            "url": url,
            "account": article["account"],
            "publish_time": article["published"],
            "content": content,
            "author": author
        }).execute()

        print("✅ 插入成功:", article["title"])

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
        print(f"🔹 抓取公众号: {account_name}, feed: {feed_url}")
        articles = fetch_articles_from_feed(feed_url, account_name)
        all_articles.extend(articles)

    print(f"📝 获取到文章总数: {len(all_articles)}")

    for art in all_articles:
        print("🔹 标题:", art["title"])
        print("🔹 URL:", art["url"])
        print("🔹 公众号:", art["account_name"])
        print("🔹 发布时间:", art["publish_time"])
        save_to_db(art)

    print("🏁 完成")
