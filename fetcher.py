import feedparser

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
