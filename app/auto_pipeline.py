"""Full automated pipeline with Auto-Image Creation and Telegram Button Integration."""
import logging
import time
import os
from typing import Dict, Any
from app.config import Settings
from app.db import Database
from app.auto_fetcher import AutoDealFetcher
from app.content_checker import ContentRejected, enforce_caption_safety
from app.image_creator import create_deal_banner
from app.models import Product
from app.telegram_publisher import TelegramPublisher

log = logging.getLogger(__name__)


def build_deal_caption(deal: Dict[str, Any]) -> str:
    title = deal["title"]
    desc = deal["description"] or "Trending styles and current offers on top brands."
    coupon = deal.get("coupon_code")
    tracking_url = deal["tracking_url"]

    coupon_line = f"\n<b>Extra Coupon:</b> <code>{coupon}</code>" if coupon else ""

    caption = (
        f"<b>{title}</b>\n\n"
        f"<i>{desc.strip()}</i>{coupon_line}\n\n"
        f"Check the latest offer and price on AJIO.\n"
        f"<a href=\"{tracking_url}\"><b>Tap here to shop on AJIO</b></a>\n\n"
        f"<i>Affiliate disclosure: I may earn a commission on eligible purchases.</i>"
    )
    return caption


def run_autonomous_deal_publisher(settings: Settings, max_posts: int = 2) -> Dict[str, Any]:
    """Disabled: strictly only Google Sheet dress cards with real photos are allowed."""
    log.info("Autonomous text-deal publisher is disabled by policy. Only real Google Sheet items are posted.")
    return {"status": "disabled", "deals_published": 0, "message": "Text banners disabled"}
