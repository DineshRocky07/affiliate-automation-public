"""Publish individual dress items with direct product URLs and certified clean links."""
import csv
import logging
import os
import time
from typing import Dict, Any
from app.config import get_settings
from app.db import Database
from app.ajio_provider import AjioProvider
from app.dress_card_creator import download_or_create_dress_card
from app.telegram_publisher import TelegramPublisher

log = logging.getLogger(__name__)


def publish_individual_dresses(csv_path: str = "data/dress_catalog.csv", max_posts: int = 2) -> Dict[str, Any]:
    """Posts high-converting single dress photos with exact product links that open smoothly."""
    s = get_settings()
    db = Database(s.db_path)
    db.init()

    ajio = AjioProvider(s.ajio_api_key, s.ajio_campaign_id, s.ajio_pub_id, s.ajio_tracking_base)
    publisher = TelegramPublisher(s.telegram_bot_token, s.telegram_chat_id, dry_run=s.dry_run)

    if not os.path.exists(csv_path):
        return {"status": "error", "message": f"CSV {csv_path} not found"}

    posted = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if posted >= max_posts:
                break

            title = row["title"].strip()
            direct_url = row["url"].strip()
            price = float(row["price"])
            mrp = float(row["mrp"])
            image_url = row["image_url"].strip()
            brand = row.get("brand", "AJIO").strip()
            category = row.get("category", "Fashion").strip()

            discount_pct = int(round((1.0 - (price / mrp)) * 100))
            item_id = f"AJIO-SAFE-{brand}-{title[:15].replace(' ', '_')}"

            # 1. SQL Deduplication
            if db.is_product_posted(item_id):
                continue

            # 2. Build Antivirus-Safe Tracking Link (Bypasses Malwarebytes & Keeps Commissions)
            link = ajio.build_link(item_id, direct_url, subid=f"viod_{category.lower()}")
            if not link.is_eligible:
                continue

            affiliate_url = link.tracking_url

            # 3. Generate high-CTR dress card image
            card_path = f"data/card_{posted + 1}.jpg"
            download_or_create_dress_card(
                image_url=image_url,
                brand=brand,
                title=title,
                price=price,
                mrp=mrp,
                discount_pct=discount_pct,
                output_path=card_path
            )

            # 4. Formatted Telegram Post
            caption = (
                f"👗 <b>{brand.upper()}</b> — <b>{title}</b>\n\n"
                f"🏷️ <b>Special Price:</b> ₹{price:,.0f} <s>₹{mrp:,.0f}</s> <b>({discount_pct}% OFF)</b>\n"
                f"✨ Category: <i>{category}</i>\n"
                f"🚚 Free Returns & Cash on Delivery Available\n\n"
                f"👇 <b>Tap the button below to view and order:</b>\n"
                f"<i>ℹ️ Affiliate link — We earn a small commission on purchases.</i>"
            )

            # 5. Send with photo + Big Buy Button
            try:
                res = publisher.send_deal(
                    caption=caption,
                    image_path=card_path,
                    tracking_url=affiliate_url
                )
                msg_id = res.get("message_id") if isinstance(res, dict) else None

                # 6. Save in SQLite (live posts only)
                if not s.dry_run:
                    db.record_post(
                        product_id=item_id,
                        provider="ajio",
                        affiliate_url=affiliate_url,
                        headline=title,
                        caption=caption,
                        telegram_message_id=msg_id
                    )

                posted += 1
                log.info("Posted individual dress deal: %s with safe link %s", title, affiliate_url)
                time.sleep(2)
            except Exception as e:
                log.error("Failed to post dress: %s", e)

    return {"status": "success", "dry_run": s.dry_run, "items_posted": posted}
