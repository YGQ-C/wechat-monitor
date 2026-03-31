import os
import requests
from datetime import datetime
from supabase import create_client

# 配置
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
JIZHILIAO_KEY = os.getenv("JIZHILIAO_API_KEY")
WECHAT2RSS_URL = os.getenv("WECHAT2RSS_URL")
WECHAT2RSS_KEY = os.getenv("WECHAT2RSS_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_wechat_articles():
    try:
        url = f"{WECHAT2RSS_URL}/api/articles?key={WECHAT2RSS_KEY}"
        res = requests.get(url, timeout=15)
        return res.json()
    except:
        return []

def get_article_read_count(link):
    try:
        resp = requests.get(
            "https://www.dajiala.com/api/article/data",
            params={"url": link},
            headers={"Authorization": JIZHILIAO_KEY},
            timeout=10
        )
        data = resp.json()
        return data.get("read", 0), data.get("like", 0), data.get("comment", 0)
    except:
        return 0, 0, 0

def save_article(title, link, publish_time, read, like, comment):
    supabase.table("wechat_articles").upsert({
        "title": title,
        "url": link,
        "publish_time": publish_time,
        "read_count": read,
        "like_count": like,
        "comment_count": comment
    }, on_conflict="url").execute()

def run():
    articles = get_wechat_articles()
    if not articles:
        print("无文章")
        return

    for item in articles:
        title = item.get("title", "")
        link = item.get("url", "")
        publish_time = item.get("publish_time", "")
        read, like, comment = get_article_read_count(link)
        save_article(title, link, publish_time, read, like, comment)
        print(f"已保存: {title}")

    print("全部完成！")

if __name__ == "__main__":
    run()
