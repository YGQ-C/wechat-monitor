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


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def format_publish_time(published):
    if not published:
        return None
    return str(published)


def get_accounts():
    url = f"{WECHAT2RSS_URL}/list?page=1&size=100&k={WECHAT2RSS_KEY}"
    res = requests.get(url)
    return res.json().get("data", [])


def fetch_stats(url):
    try:
        api_url = "https://www.dajiala.com/fbmain/monitor/v3/read_zan_pro"
        body = {"url": url, "key": DAJIALA_API_KEY}

        res = requests.post(api_url, json=body, timeout=10)
        data = res.json().get("data", {})

        return {
            "read": data.get("read", 0),
            "like": data.get("zan", 0),
            "comment": data.get("comment_count", 0),
            "share": data.get("share_num", 0)
        }

    except:
        return {"read":0,"like":0,"comment":0,"share":0}


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
                    "account_id": art["account"],  # ✅ 修复这里
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

            time.sleep(1)

    print("🎉 完成")
