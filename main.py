import os
import requests
import time
from datetime import datetime, timezone
from db import supabase, is_exist, insert_article
from fetcher import fetch_articles
from analyzer import compute_score

WECHAT2RSS_URL = os.getenv("WECHAT2RSS_URL")
WECHAT2RSS_KEY = os.getenv("WECHAT2RSS_KEY")
DAJIALA_API_KEY = os.getenv("JIZHILIAO_API_KEY")


# ===================== 时间 =====================
def now_utc():
    return datetime.now(timezone.utc).isoformat()


def format_publish_time(published):
    if not published:
        return None
    return str(published)


# ===================== 获取公众号 =====================
def get_accounts():
    url = f"{WECHAT2RSS_URL}/list?page=1&size=100&k={WECHAT2RSS_KEY}"
    res = requests.get(url)
    return res.json().get("data", [])


# ===================== 抓阅读量 =====================
def fetch_stats(url):
    try:
        api_url = "https://www.dajiala.com/fbmain/monitor/v3/read_zan_pro"
        body = {"url": url, "key": DAJIALA_API_KEY}

        res = requests.post(api_url, json=body, timeout=20)
        data = res.json().get("data", {})

        return {
            "read": data.get("read", 0),
            "like": data.get("zan", 0),
            "comment": data.get("comment_count", 0),
            "share": data.get("share_num", 0)
        }

    except:
        return {"read": 0, "like": 0, "comment": 0, "share": 0}


# ===================== 生成排行榜 =====================
def generate_ranks():
    print("📊 开始生成排行榜")

    today = datetime.now().date().isoformat()

    # 取所有文章（简单稳定版本）
    res = supabase.table("wechat_articles") \
        .select("*") \
        .execute()

    articles = res.data

    if not articles:
        print("⚠️ 没有文章数据")
        return

    # 排序
    hot_top = sorted(articles, key=lambda x: x["hot_score"], reverse=True)[:10]
    interact_top = sorted(articles, key=lambda x: x["interact_score"], reverse=True)[:10]
    abnormal_top = sorted(articles, key=lambda x: x["abnormal_score"], reverse=True)[:10]

    # 清空当天数据
    supabase.table("hot_ranks") \
        .delete() \
        .eq("created_at", today) \
        .execute()

    def insert_rank(art, rank_type, value):
        supabase.table("hot_ranks").insert({
            "article_id": art["id"],
            "rank_type": rank_type,
            "rank_value": value,
            "created_at": today
        }).execute()

    # 写入三类榜单
    for art in hot_top:
        insert_rank(art, "hot", art["hot_score"])

    for art in interact_top:
        insert_rank(art, "interact", art["interact_score"])

    for art in abnormal_top:
        insert_rank(art, "abnormal", art["abnormal_score"])

    print("✅ 排行榜生成完成")


# ===================== 发邮件 =====================
def send_email():
    RESEND_API_KEY = os.getenv("RESEND_API_KEY")
    EMAIL_TO = os.getenv("EMAIL_TO")

    if not RESEND_API_KEY or not EMAIL_TO:
        print("⚠️ 邮件未配置")
        return

    today = datetime.now().date().isoformat()

    res = supabase.table("hot_ranks") \
        .select("*") \
        .eq("created_at", today) \
        .execute()

    ranks = res.data

    if not ranks:
        print("⚠️ 没有排行榜数据")
        return

    article_ids = [r["article_id"] for r in ranks]

    arts = supabase.table("wechat_articles") \
        .select("id,title,url") \
        .in_("id", article_ids) \
        .execute()

    art_map = {a["id"]: a for a in arts.data}

    html = f"<h2>公众号排行榜 {today}</h2>"

    def render(rank_type, title):
        items = [r for r in ranks if r["rank_type"] == rank_type]
        items = sorted(items, key=lambda x: x["rank_value"], reverse=True)

        block = f"<h3>{title}</h3>"

        for i, r in enumerate(items):
            art = art_map.get(r["article_id"])
            if art:
                block += f"<p>第{i+1}名：<a href='{art['url']}'>{art['title']}</a>（{r['rank_value']}）</p>"

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
        "subject": f"公众号排行榜 {today}",
        "html": html
    }

    r = requests.post("https://api.resend.com/emails", headers=headers, json=body)

    print("📧 邮件状态:", r.status_code)


# ===================== 主程序 =====================
if __name__ == "__main__":
    print("🚀 开始运行")

    accounts = get_accounts()

    for acc in accounts:
        print("🔹 抓取公众号:", acc.get("name"))

        articles = fetch_articles(acc.get("link"), acc.get("name"))

        for art in articles:
            print("📰 抓到:", art["title"])

            if is_exist(art["link"]):
                print("⚠️ 已存在:", art["title"])
                continue

            stats = fetch_stats(art["link"])

            hot, interact, abnormal = compute_score(
                stats,
                format_publish_time(art.get("published"))
            )

            try:
                insert_article({
                    "title": art["title"],
                    "url": art["link"],
                    "account_id": art["account"],
                    "publish_time": format_publish_time(art.get("published")),
                    "read_count": stats["read"],
                    "like_count": stats["like"],
                    "comment_count": stats["comment"],
                    "share_count": stats["share"],
                    "hot_score": hot,
                    "interact_score": interact,
                    "abnormal_score": abnormal,
                    "created_at": now_utc()
                })

                print("✅ 插入:", art["title"])

            except Exception as e:
                print("❌ 插入失败:", e)

            time.sleep(2)

    # ✅ 关键两步（你之前缺的）
    generate_ranks()
    send_email()

    print("🎉 完成")
