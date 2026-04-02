import os
import requests
import feedparser
from supabase import create_client
import time
from datetime import datetime, date

# ===================== 环境变量 =====================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
WECHAT2RSS_URL = os.getenv("WECHAT2RSS_URL")
WECHAT2RSS_KEY = os.getenv("WECHAT2RSS_KEY")
DAJIALA_API_KEY = os.getenv("JIZHILIAO_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_TO = os.getenv("EMAIL_TO")

# ===================== 数据库 =====================
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
print("✅ 数据库连接成功")

# ===================== 获取公众号 =====================
def get_accounts():
    url = f"{WECHAT2RSS_URL}/list?page=1&size=100&k={WECHAT2RSS_KEY}"
    res = requests.get(url, timeout=15)
    return res.json().get("data", [])

# ===================== 抓文章 =====================
def fetch_articles(feed_url, account_name, limit=5):
    articles = []
    feed = feedparser.parse(feed_url)

    for i, entry in enumerate(feed.entries):
        if i >= limit:
            break

        articles.append({
            "title": entry.title,
            "link": entry.link,
            "published": getattr(entry, "published", ""),
            "account": account_name
        })

    return articles

# ===================== 极致了数据 =====================
def fetch_stats(url):
    try:
        api_url = "https://www.dajiala.com/fbmain/monitor/v3/read_zan_pro"
        body = {"url": url, "key": DAJIALA_API_KEY, "verifycode": ""}

        res = requests.post(api_url, json=body, timeout=10).json()
        data = res.get("data", {})

        return {
            "read": data.get("read", 0),
            "like": data.get("zan", 0),
            "comment": max(data.get("comment_count", 0), 0),
            "share": data.get("share_num", 0)
        }
    except:
        return {"read":0,"like":0,"comment":0,"share":0}

# ===================== 计算指标 =====================
def compute(stats):
    read = stats["read"]
    like = stats["like"]
    comment = stats["comment"]
    share = stats["share"]

    hot = read*0.5 + like*0.3 + share*0.1 + comment*0.1
    interact = (like+comment+share)/max(read,1)
    abnormal = (read+like+comment+share)/max(read,1)

    return round(hot,2), round(interact,2), round(abnormal,2)

# ===================== 去重 =====================
def is_exist(url):
    res = supabase.table("wechat_articles").select("id").eq("url", url).execute()
    return len(res.data) > 0

# ===================== 生成排行榜 =====================
def generate_ranks():
    today = date.today()

    # 取今天所有文章（关键：不是只看新数据）
    res = supabase.table("wechat_articles").select("*").gte("created_at", str(today)).execute()

    articles = res.data
    if not articles:
        print("⚠️ 今日无文章")
        return

    # 排序
    hot_top = sorted(articles, key=lambda x: x["hot_score"], reverse=True)[:5]
    interact_top = sorted(articles, key=lambda x: x["interact_score"], reverse=True)[:5]
    abnormal_top = sorted(articles, key=lambda x: x["abnormal_score"], reverse=True)[:5]

    # 清空今天旧榜
    supabase.table("hot_ranks").delete().gte("created_at", str(today)).execute()

    # 写入榜单
    for art in hot_top:
        supabase.table("hot_ranks").insert({
            "article_id": art["id"],
            "rank_type": "hot",
            "rank_value": art["hot_score"],
            "created_at": today
        }).execute()

    for art in interact_top:
        supabase.table("hot_ranks").insert({
            "article_id": art["id"],
            "rank_type": "interact",
            "rank_value": art["interact_score"],
            "created_at": today
        }).execute()

    for art in abnormal_top:
        supabase.table("hot_ranks").insert({
            "article_id": art["id"],
            "rank_type": "abnormal",
            "rank_value": art["abnormal_score"],
            "created_at": today
        }).execute()

    print("📊 排行榜生成完成")

# ===================== 发邮件 =====================
def send_daily_report():
    if not RESEND_API_KEY or not EMAIL_TO:
        print("⚠️ 邮件未配置")
        return

    today = date.today().isoformat() 

    res = supabase.table("hot_ranks").select("*").eq("created_at", str(today)).execute()
    ranks = res.data

    if not ranks:
        print("⚠️ 没有排行榜数据，邮件不发")
        return

    html = f"<h2>公众号日报 {today}</h2>"

    def render(rank_type, title):
        items = [r for r in ranks if r["rank_type"] == rank_type]
        html_block = f"<h3>{title}</h3>"
        for r in items:
            art = supabase.table("wechat_articles").select("title,url").eq("id", r["article_id"]).execute().data[0]
            html_block += f"<p><a href='{art['url']}'>{art['title']}</a> - {r['rank_value']}</p>"
        return html_block

    html += render("hot", "🔥 热度榜")
    html += render("interact", "💬 互动榜")
    html += render("abnormal", "🚨 异常榜（爆文）")

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "from": "onboarding@resend.dev",
        "to": EMAIL_TO,
        "subject": f"公众号日报 {today}",
        "html": html
    }

    r = requests.post("https://api.resend.com/emails", headers=headers, json=body)

    print("📧 邮件状态:", r.status_code)
    print(r.text)

# ===================== 主程序 =====================
if __name__ == "__main__":
    print("🚀 开始运行")

    accounts = get_accounts()

    for acc in accounts:
        feed_url = acc.get("link")
        name = acc.get("name")

        print(f"🔹 抓取公众号: {name}")

        articles = fetch_articles(feed_url, name, limit=5)

        for art in articles:
            if is_exist(art["link"]):
                continue

            stats = fetch_stats(art["link"])
            hot, interact, abnormal = compute(stats)

            supabase.table("wechat_articles").insert({
                "title": art["title"],
                "url": art["link"],
                "account_id": art["account"],
                "publish_time": art["published"],
                "read_count": stats["read"],
                "like_count": stats["like"],
                "comment_count": stats["comment"],
                "share_count": stats["share"],
                "hot_score": hot,
                "interact_score": interact,
                "abnormal_score": abnormal
            }).execute()

            print(f"✅ 插入: {art['title']}")

            time.sleep(1)

    # 👉 核心：生成排行榜
    generate_ranks()

    # 👉 核心：发送邮件
    send_daily_report()

    print("🎉 完成")
