import os
import requests
import feedparser
from supabase import create_client
import time
from datetime import datetime, timezone
import time as time_module

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

# ===================== 时间工具 =====================
def now_utc():
    return datetime.now(timezone.utc).isoformat()

def today_utc():
    return datetime.now(timezone.utc).date().isoformat()

def today_start_utc():
    return datetime.now(timezone.utc).date().isoformat() + "T00:00:00Z"

# ===================== 时间格式化 =====================
def format_publish_time(published):
    if not published:
        return None

    if isinstance(published, time_module.struct_time):
        return datetime(*published[:6]).isoformat(timespec='seconds')

    if isinstance(published, str):
        return published

    return str(published)

# ===================== 时间衰减 =====================
def time_decay(publish_time):
    if not publish_time:
        return 1

    try:
        pub = datetime.fromisoformat(publish_time.replace("Z", "+00:00"))
        hours = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
        return max(hours, 1)
    except:
        return 1

# ===================== 爆文算法 =====================
def compute_advanced(stats, publish_time):
    read = stats["read"]
    like = stats["like"]
    comment = stats["comment"]
    share = stats["share"]

    decay = time_decay(publish_time)
    growth = read / decay  # 核心爆发力

    # 简单归一化（防大号碾压）
    norm = read / 10000

    hot = (
        growth * 0.6 +
        (like + comment + share) * 0.3 +
        norm * 0.1
    )

    interact = (like + comment + share) / max(read, 1)
    abnormal = growth / max(read, 1)

    return round(hot, 2), round(interact, 2), round(abnormal, 2)

# ===================== 获取公众号 =====================
def get_accounts():
    url = f"{WECHAT2RSS_URL}/list?page=1&size=100&k={WECHAT2RSS_KEY}"
    res = requests.get(url, timeout=15)
    res.raise_for_status()
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
            "published": getattr(entry, "published", None),
            "account": account_name
        })

    return articles

# ===================== 数据抓取 =====================
def fetch_stats(url):
    try:
        api_url = "https://www.dajiala.com/fbmain/monitor/v3/read_zan_pro"
        body = {"url": url, "key": DAJIALA_API_KEY, "verifycode": ""}

        res = requests.post(api_url, json=body, timeout=10)
        res.raise_for_status()

        data = res.json().get("data", {})

        return {
            "read": data.get("read", 0),
            "like": data.get("zan", 0),
            "comment": max(data.get("comment_count", 0), 0),
            "share": data.get("share_num", 0)
        }

    except Exception as e:
        print("❌ fetch_stats error:", e)
        return {"read":0,"like":0,"comment":0,"share":0}

# ===================== 去重 =====================
def is_exist(url):
    res = supabase.table("wechat_articles") \
        .select("id", count="exact") \
        .eq("url", url) \
        .execute()
    return res.count > 0

# ===================== 榜单锁 =====================
def has_generated_today():
    today = today_utc()

    res = supabase.table("hot_ranks") \
        .select("id", count="exact") \
        .eq("created_at", today) \
        .execute()

    return res.count > 0

# ===================== 生成排行榜 =====================
def generate_ranks():
    today = today_utc()
    today_start = today_start_utc()

    res = supabase.table("wechat_articles") \
        .select("*") \
        .gte("created_at", today_start) \
        .execute()

    articles = res.data
    if not articles:
        print("⚠️ 今日无文章")
        return

    print(f"📊 今日文章数: {len(articles)}")

    hot_top = sorted(articles, key=lambda x: x["hot_score"], reverse=True)[:5]
    interact_top = sorted(articles, key=lambda x: x["interact_score"], reverse=True)[:5]
    abnormal_top = sorted(articles, key=lambda x: x["abnormal_score"], reverse=True)[:5]

    def insert_rank(art, rank_type, value):
        supabase.table("hot_ranks").insert({
            "article_id": art["id"],
            "rank_type": rank_type,
            "rank_value": value,
            "created_at": today
        }).execute()

    for art in hot_top:
        insert_rank(art, "hot", art["hot_score"])

    for art in interact_top:
        insert_rank(art, "interact", art["interact_score"])

    for art in abnormal_top:
        insert_rank(art, "abnormal", art["abnormal_score"])

    print("📊 排行榜生成完成")

# ===================== 发邮件 =====================
def send_daily_report():
    if not RESEND_API_KEY or not EMAIL_TO:
        print("⚠️ 邮件未配置")
        return

    today = today_utc()

    res = supabase.table("hot_ranks") \
        .select("*") \
        .eq("created_at", today) \
        .execute()

    ranks = res.data
    if not ranks:
        print("⚠️ 没有排行榜数据")
        return

    article_ids = [r["article_id"] for r in ranks]

    arts_res = supabase.table("wechat_articles") \
        .select("id,title,url") \
        .in_("id", article_ids) \
        .execute()

    art_map = {a["id"]: a for a in arts_res.data}

    html = f"<h2>公众号日报 {today}</h2>"

    def render(rank_type, title):
        items = [r for r in ranks if r["rank_type"] == rank_type]
        block = f"<h3>{title}</h3>"

        for r in items:
            art = art_map.get(r["article_id"])
            if art:
                block += f"<p><a href='{art['url']}'>{art['title']}</a> - {r['rank_value']}</p>"

        return block

    html += render("hot", "🔥 热度榜")
    html += render("interact", "💬 互动榜")
    html += render("abnormal", "🚨 异常榜")

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
            print("📰 抓到:", art["title"])

            if is_exist(art["link"]):
                print("⚠️ 已存在:", art["title"])
                continue

            stats = fetch_stats(art["link"])

            hot, interact, abnormal = compute_advanced(
                stats,
                format_publish_time(art.get("published"))
            )

            try:
                supabase.table("wechat_articles").insert({
                    "title": art["title"],
                    "url": art["link"],
                    "account_name": art["account"],
                    "publish_time": format_publish_time(art.get("published")),
                    "read_count": stats["read"],
                    "like_count": stats["like"],
                    "comment_count": stats["comment"],
                    "share_count": stats["share"],
                    "hot_score": hot,
                    "interact_score": interact,
                    "abnormal_score": abnormal,
                    "created_at": now_utc()
                }).execute()

                print(f"✅ 插入: {art['title']}")

            except Exception as e:
                print("❌ 插入失败:", e)

            time.sleep(1)

    # ✅ 榜单锁
    if not has_generated_today():
        generate_ranks()
        send_daily_report()
    else:
        print("⚠️ 今日榜单已生成，跳过")

    print("🎉 完成")
