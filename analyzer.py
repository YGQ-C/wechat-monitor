from datetime import datetime, timezone

def time_decay(publish_time):
    if not publish_time:
        return 1

    try:
        pub = datetime.fromisoformat(publish_time.replace("Z", "+00:00"))
        hours = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
        return max(hours, 1)
    except:
        return 1


def compute_score(stats, publish_time):
    read = stats["read"]
    like = stats["like"]
    comment = stats["comment"]
    share = stats["share"]

    decay = time_decay(publish_time)
    growth = read / decay

    norm = read / 10000

    hot = growth * 0.6 + (like + comment + share) * 0.3 + norm * 0.1
    interact = (like + comment + share) / max(read, 1)
    abnormal = growth / max(read, 1)

    return round(hot, 2), round(interact, 2), round(abnormal, 2)
