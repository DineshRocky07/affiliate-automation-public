"""Daily shirt scheduler: posts up to MAX_POSTS_PER_DAY shirts, paced by POST_INTERVAL_SECONDS."""
import time
from datetime import datetime

import schedule

from app.config import get_settings
from app.shirts_publisher import publish_shirts


def job():
    s = get_settings()
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Shirt run started "
          f"(target: {s.max_posts_per_day}, dry_run={s.dry_run})...")
    res = publish_shirts(settings=s)
    print("Result:", res)


def start_100_daily_scheduler():
    from app.console import enable_utf8
    enable_utf8()

    s = get_settings()
    print("100-Shirts Daily Publisher daemon started.")
    print(f"Schedule: daily at 09:00. Target {s.max_posts_per_day} posts, "
          f"{s.post_interval_seconds}s apart, dry_run={s.dry_run}.")
    print("Press Ctrl+C to stop.")
    schedule.every().day.at("09:00").do(job)
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    start_100_daily_scheduler()
