"""Daily fashion deal publisher: reads the inventory CSV and posts eligible deals.

AJIO rows are routed through the AJIO ACE provider, everything else through
Cuelinks. Every caption is checked by the deterministic guardrails first.
"""
import csv
import html
import logging
import os
import time
from typing import Any, Dict

from app.config import get_settings
from app.content_checker import ContentRejected, enforce_caption_safety
from app.db import Database
from app.dress_card_creator import download_or_create_dress_card
from app.link_service import resolve_affiliate_link
from app.models import Product
from app.telegram_publisher import TelegramPublisher

log = logging.getLogger(__name__)


def publish_fashion_deals(category_filter: str = "all", max_posts: int = 50) -> Dict[str, Any]:
    """Publishes separate fashion deals for Men and Women."""
    s = get_settings()
    db = Database(s.db_path)
    db.init()

    publisher = TelegramPublisher(s.telegram_bot_token, s.telegram_chat_id, dry_run=s.dry_run)
    csv_path = "data/fashion_deals_inventory.csv"

    if not os.path.exists(csv_path):
        return {"status": "error", "message": f"Inventory {csv_path} not found."}

    posted_count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if posted_count >= max_posts:
                break

            cat = row.get("category", "").strip().lower()
            if category_filter != "all" and cat != category_filter.lower():
                continue

            brand = row["brand"].strip()
            title = row["title"].strip()
            price = float(row["price"])
            mrp = float(row["mrp"])
            image_url = row["image_url"].strip()
            product_url = row["url"].strip()

            deal_id = f"FASHION-{cat.upper()}-{brand}-{title[:15].replace(' ', '_')}"

            if db.is_product_posted(deal_id):
                continue

            link = resolve_affiliate_link(deal_id, product_url, s, subid=f"viod_{cat}")
            if not link.is_eligible:
                log.warning("Skipping %s: %s", title, link.reason)
                continue

            discount_pct = int(round((1.0 - (price / mrp)) * 100))
            product = Product(
                product_id=deal_id,
                title=title,
                url=product_url,
                price=price,
                mrp=mrp,
                category=cat,
                image_url=image_url,
                source=link.provider,
                price_verified=True,
            )

            card_path = f"data/card_{cat}_{posted_count + 1}.jpg"
            download_or_create_dress_card(
                image_url=image_url,
                brand=brand,
                title=title,
                price=price,
                mrp=mrp,
                discount_pct=discount_pct,
                output_path=card_path,
            )

            gender_tag = "MEN'S FASHION DEAL" if cat == "men" else "WOMEN'S FASHION DEAL"
            caption = (
                f"<b>{gender_tag}</b>\n\n"
                f"<b>{html.escape(brand.upper())}</b> - <b>{html.escape(title)}</b>\n\n"
                f"<b>Deal Price:</b> Rs {price:,.0f} <s>Rs {mrp:,.0f}</s> <b>({discount_pct}% OFF)</b>\n"
                f"Check latest price and available sizes on the store.\n\n"
                f"<a href=\"{link.tracking_url}\"><b>Tap here to see all sizes and colours</b></a>\n\n"
                f"<i>Affiliate link - I may earn a commission on qualifying purchases.</i>"
            )

            try:
                enforce_caption_safety(title, caption, product)
                publisher.send_deal(caption=caption, image_path=card_path, tracking_url=link.tracking_url)
                if not s.dry_run:
                    db.record_post(
                        product_id=deal_id,
                        provider=link.provider,
                        affiliate_url=link.tracking_url,
                        headline=title,
                        caption=caption,
                    )
                posted_count += 1
                log.info("Posted %s deal: %s @ Rs. %s", cat, title, price)
                time.sleep(3)
            except ContentRejected as exc:
                log.warning("Caption rejected for %s: %s", deal_id, exc)
            except Exception as e:
                log.error("Failed to post deal %s: %s", deal_id, e)

    return {
        "status": "success",
        "category": category_filter,
        "deals_posted": posted_count,
        "dry_run": s.dry_run,
    }
