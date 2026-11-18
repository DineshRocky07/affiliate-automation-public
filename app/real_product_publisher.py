"""Publish a single real product (Amazon URL/ASIN) with an eligible affiliate link.

NOTE: the AGENTS policy prefers official APIs over scraping. This module is kept
for the existing flow, but AJIO products should use ``shirts_publisher`` instead.
"""
import html
import logging
import os
import time
import urllib.request
from typing import Any, Dict, List

from app.amazon_scraper import fetch_amazon_product_details
from app.config import get_settings
from app.content_checker import ContentRejected, enforce_caption_safety
from app.db import Database
from app.link_service import resolve_affiliate_link
from app.models import Product
from app.telegram_publisher import TelegramPublisher

log = logging.getLogger(__name__)


def publish_real_product(url_or_asin: str) -> Dict[str, Any]:
    """Fetch a real product photo/title, resolve an eligible link, and post."""
    s = get_settings()
    db = Database(s.db_path)
    db.init()

    publisher = TelegramPublisher(s.telegram_bot_token, s.telegram_chat_id, dry_run=s.dry_run)

    prod = fetch_amazon_product_details(url_or_asin)
    if not prod:
        return {"status": "error", "message": f"Could not fetch product for {url_or_asin}"}

    asin = prod["asin"]
    item_id = f"AMZN-{asin}"

    if db.is_product_posted(item_id):
        return {"status": "skipped", "message": f"Product {asin} was already posted."}

    link = resolve_affiliate_link(item_id, prod["original_url"], s, subid="viod_amazon")
    if not link.is_eligible:
        return {"status": "rejected", "message": link.reason}

    img_path = None
    if prod["image_url"]:
        img_path = f"data/real_product_{asin}.jpg"
        try:
            req = urllib.request.Request(prod["image_url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r, open(img_path, "wb") as f:
                f.write(r.read())
        except Exception as e:
            log.warning("Could not download product photo: %s", e)
            img_path = None

    price = float(prod["price"]) if prod.get("price") else 0.0
    price_line = f"Listed at Rs {price:,.0f}\n" if price else "Check the latest price on the store.\n"

    caption = (
        f"<b>{html.escape(prod['title'][:65])}</b>\n\n"
        f"{price_line}"
        f"<a href=\"{link.tracking_url}\"><b>Check sizes and order now</b></a>\n\n"
        f"<i>Affiliate link - I may earn a commission on qualifying orders.</i>"
    )

    product = Product(
        product_id=item_id,
        title=prod["title"],
        url=prod["original_url"],
        price=price,
        mrp=price,
        category="Fashion",
        image_url=prod.get("image_url") or "",
        source="amazon",
        price_verified=bool(price),
    )

    try:
        enforce_caption_safety(prod["title"], caption, product)
        res = publisher.send_deal(caption=caption, image_path=img_path, tracking_url=link.tracking_url)
    except ContentRejected as exc:
        return {"status": "rejected", "message": f"Caption rejected: {exc}"}

    msg_id = res.get("message_id") if isinstance(res, dict) else None

    db.record_post(
        product_id=item_id,
        provider=link.provider,
        affiliate_url=link.tracking_url,
        headline=prod["title"],
        caption=caption,
        telegram_message_id=msg_id,
    )

    return {
        "status": "success",
        "asin": asin,
        "title": prod["title"],
        "price": prod["price"],
        "posted": True,
    }


def publish_batch_products(asins_or_urls: List[str]) -> List[Dict[str, Any]]:
    results = []
    for u in asins_or_urls:
        results.append(publish_real_product(u))
        time.sleep(2)
    return results
