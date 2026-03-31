import os
import requests
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
except Exception as e:
    print("数据库连接失败:", e)
    supabase = None

# ===================== 【终极修复】正确接口 =====================
def get_articles():
    # 直接拼接，不绕弯
    url = WECHAT2RSS_URL.rstrip("/") + f"/api/entries?key={WECHAT2RSS_KEY}"
    print("🔗 最终请求地址:", url)  # 你会看到真实请求路径

    try:
        res = requests.get(url, timeout=15)
        print("✅ 接口状态码:", res.status_code)
        print("📄 返回内容:", res.text[:500])
        return res.json() if res.status_code == 200 else []
    except Exception as e:
        print("❌ 错误:", e)
        return []

# ===================== 获取阅读点赞 =====================
def get_article_data(article_url):
    try:
        resp = requests.get(
            "https://www.dajiala.com/api/article/data",
            params={"url": article_url},
            headers={"Authorization": JIZHILIAO_API_KEY},
            timeout=10
        )
        data = resp.json()
        return data.get("read", 0), data.get("like", 0), data.get("comment", 0)
    except:
        return 0, 0, 0

# ===================== 存入数据库 =====================
def save_to_db(article):
    if not supabase:
        return

    title = article.get("title", "")
    url = article.get("url", "")
    publish_time = article.get("created_at", "")
    account_name = article.get("account_name", "unknown")

    if not title or not url:
        return

    read, like, comment = get_article_data(url)

    try:
        supabase.table("wechat_articles").upsert({
            "title": title,
            "url": url,
            "publish_time": publish_time,
            "account_id": account_name,
            "read_count": read,
            "like_count": like,
            "comment_count": comment
        }, on_conflict="url").execute()
        print(f"✅ 已保存: {title}")
    except Exception as e:
        print("❌ 保存失败:", e)

# ===================== 主程序 =====================
if __name__ == "__main__":
    print("🚀 开始抓取公众号文章...")
    articles = get_articles()

    if not articles:
        print("📭 无文章")
    else:
        print(f"📝 文章数量: {len(articles)}")
        for art in articles:
            save_to_db(art)

    print("🏁 任务完成")
