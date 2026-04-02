import os
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def is_exist(url):
    res = supabase.table("wechat_articles") \
        .select("id", count="exact") \
        .eq("url", url) \
        .execute()
    return res.count > 0


def insert_article(data):
    return supabase.table("wechat_articles").insert(data).execute()
