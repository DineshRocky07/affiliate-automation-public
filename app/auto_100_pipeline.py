"""Automated 100-Deals Daily Pipeline: Reads product list, auto-scrapes photo & price, and publishes."""
import logging
import os
import time
from app.config import get_settings
from app.real_product_publisher import publish_real_product

log = logging.getLogger(__name__)


def auto_post_100_deals(file_path: str = "data/products_to_post.txt", max_posts: int = 100):
    """Pulls products, downloads real images, attaches clean tracking links, and posts on schedule."""
    from app.console import enable_utf8
    enable_utf8()

    if not os.path.exists(file_path):
        print(f"File {file_path} does not exist.")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    print(f"📦 Loaded {len(lines)} products from {file_path}. Target: {max_posts} posts.")

    posted_count = 0
    for item in lines:
        if posted_count >= max_posts:
            break

        try:
            res = publish_real_product(item)
            if res.get("posted"):
                posted_count += 1
                print(f"[{posted_count}/{max_posts}] ✅ Successfully posted: {res.get('asin')}")
                # Wait 5 seconds between posts so Telegram never rate-limits you
                time.sleep(5)
            else:
                print(f"⏭️ Skipped: {res.get('message')}")
        except Exception as e:
            print(f"❌ Error posting {item}: {e}")

    print(f"\n🏁 Finished publishing {posted_count} deals.")


if __name__ == "__main__":
    auto_post_100_deals()
