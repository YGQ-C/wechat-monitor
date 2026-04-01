import os
import requests
import feedparser
from supabase import create_client
import time
from datetime import datetime

# ===================== 环境变量 =====================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
WECHAT2RSS_URL = os.getenv("WECHAT2RSS_URL")
WECHAT2RSS_KEY = os.getenv("WECHAT2RSS_KEY")
DAJIALA_API_KEY = os.getenv("JIZHILIAO_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")  # 邮件发送，可选
EMAIL_TO = os.getenv("EMAIL_TO")             # 收件人邮箱，可逗号分隔

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

# ===================== 从 RSS feed 获取文章（测试阶段限制5篇） =====================
def fetch_articles_from_feed(feed_url, account_name, limit=5):
    articles = []
    try:
        feed = feedparser.parse(feed_url)
        for i, entry in enumerate(feed.entries):
            if i >= limit:
                break
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
        api_url = "https://www.dajiala.com/fbmain/monitor/v3/read_zan_pro"
        headers = {"Content-Type": "application/json"}
        body = {"url": article_url, "key": DAJIALA_API_KEY, "verifycode": ""}

        res = requests.post(api_url, headers=headers, json=body, timeout=10)

        if res.status_code != 200:
            print("❌ 极致了 API 请求失败:", res.status_code)
            return {"read_count": 0, "like_count": 0, "comment_count": 0, "share_count": 0}

        data = res.json()
        if data.get("code") != 0:
            print("⚠️ API 返回错误:", data)
            return {"read_count": 0, "like_count": 0, "comment_count": 0, "share_count": 0}

        stats = data.get("data", {})
        return {
            "read_count": stats.get("read", 0),
            "like_count": stats.get("zan", 0),
            "comment_count": max(stats.get("comment_count", 0), 0),
            "share_count": stats.get("share_num", 0)
        }

    except Exception as e:
        print("❌ 调用极致了 API 出错:", e)
        return {"read_count": 0, "like_count": 0, "comment_count": 0, "share_count": 0}

# ===================== 去重检查 =====================
def is_exist(url):
    try:
        res = supabase.table("wechat_articles").select("id").eq("url", url).execute()
        return len(res.data) > 0
    except Exception as e:
        print("❌ 去重查询失败:", e)
        return False

# ===================== 计算热度/互动/异常指数 =====================
def compute_scores(stats):
    read = stats.get("read_count", 0)
    like = stats.get("like_count", 0)
    comment = stats.get("comment_count", 0)
    share = stats.get("share_count", 0)

    hot_score = read*0.5 + like*0.3 + share*0.1 + comment*0.1
    interact_score = (like + comment + share) / max(read, 1)
    abnormal_score = (read + like + comment + share) / max(read, 1)

    return round(hot_score,2), round(interact_score,2), round(abnormal_score,2)

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
    hot_score, interact_score, abnormal_score = compute_scores(stats)

    try:
        supabase.table("wechat_articles").insert({
            "title": article.get("title", ""),
            "url": url,
            "account_id": article.get("account", ""),
            "publish_time": article.get("published", ""),
            "read_count": stats["read_count"],
            "like_count": stats["like_count"],
            "comment_count": stats["comment_count"],
            "share_count": stats["share_count"],
            "hot_score": hot_score,
            "interact_score": interact_score,
            "abnormal_score": abnormal_score
        }).execute()

        print(f"✅ 插入成功: {article.get('title')} | hot:{hot_score} interact:{interact_score} abnormal:{abnormal_score}")
    except Exception as e:
        print("❌ 保存数据库失败:", e)

# ===================== 发送日报 =====================
def send_daily_report():
    if not RESEND_API_KEY or not EMAIL_TO:
        print("⚠️ 邮件未配置，跳过发送日报")
        return

    recipients = [email.strip() for email in EMAIL_TO.split(",")]
    today = datetime.utcnow().date()

    try:
        res = supabase.table("hot_ranks").select("article_id, rank_type, rank_value").eq("created_at", today).execute()

        if not res.data:
            print("⚠️ 今日排行榜为空，邮件不发送")
            return

        content = f"📊 今日公众号排行榜 ({today})<br><br>"
        for r in res.data:
            art_res = supabase.table("wechat_articles").select("title, url").eq("id", r["article_id"]).execute()
            if art_res.data:
                title = art_res.data[0]["title"]
                url = art_res.data[0]["url"]
                content += f"{r['rank_type'].capitalize()}: <a href='{url}'>{title}</a> - 分数: {r['rank_value']}<br>"

        headers = {"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"}
        body = {
            "from": "no-reply@example.com",
            "to": recipients,
            "subject": f"公众号日报 {today}",
            "html": content
        }

        response = requests.post("https://api.resend.com/emails", headers=headers, json=body)
        if response.status_code in [200, 202]:
            print("✅ 日报已发送成功！")
        else:
            print("❌ 邮件发送失败")
            print("状态码:", response.status_code)
            print("返回内容:", response.text)

    except Exception as e:
        print("❌ 发送日报异常:", e)

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

        articles = fetch_articles_from_feed(feed_url, account_name, limit=5)
        all_articles.extend(articles)

    print(f"📝 获取到文章总数: {len(all_articles)}")

    for art in all_articles:
        print(f"🔹 标题: {art.get('title')}")
        print(f"🔹 URL: {art.get('link')}")
        print(f"🔹 公众号
