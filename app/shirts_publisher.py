"""One-shirt-one-post publisher for AJIO shirts.

Reads ``data/shirts.csv`` (real AJIO product URLs only), resolves each link
through AJIO ACE, checks the caption guardrails, then posts to Telegram with a
configurable delay between posts so we stay under Telegram's flood limits.
"""
import csv
import html
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.clean_link_builder import shorten_any_affiliate_link
from app.config import Settings, get_settings
from app.content_checker import ContentRejected, enforce_caption_safety
from app.db import Database
from app.dress_card_creator import download_or_create_dress_card
from app.link_service import resolve_affiliate_link
from app.models import Product
from app.telegram_publisher import TelegramPublisher

log = logging.getLogger(__name__)

TRUE_VALUES = {"1", "true", "yes", "on"}

ALL_TOP_BRANDS = [
    "LEVI'S", "LEVIS", "LEE COOPER", "LEE", "WRANGLER", "PEPE JEANS",
    "SPYKAR", "MUFTI", "FLYING MACHINE", "DNMX", "JACK & JONES",
    "TOMMY HILFIGER", "U.S. POLO ASSN.", "USPA", "PUMA", "NIKE",
    "ADIDAS", "REEBOK", "CAMPUS", "RED TAPE", "SPARX", "ASICS", "SKECHERS",
    "HRX", "PERFORMAX", "ROADSTER", "HIGHLANDER", "WROGN", "BEING HUMAN",
    "CRAZYMONK", "DILLINGER", "WEAR YOUR MIND", "NETPLAY", "TEAMSPIRIT",
    "MAX", "GAP", "PETER ENGLAND", "VAN HEUSEN", "ALLEN SOLLY", "ARROW",
    "LOUIS PHILIPPE", "PARK AVENUE", "JOHN PLAYERS", "MONTE CARLO", "KILLER",
    "AVAASA", "RANGRITI", "BIBA", "AURELIA", "GINI & JONY", "HOPSCOTCH",
    "TOONYPORT", "FUSION", "SIYARAM",
]


def extract_top_brand(title: str, url: str = "", brand: str = "") -> Optional[str]:
    """Identify if a product belongs to a recognizable top brand."""
    if brand and brand.upper() in ALL_TOP_BRANDS:
        return brand.upper()

    slug = ""
    if "/p/" in (url or ""):
        slug = url.split("/p/")[0].split(".com/")[-1].replace("-", " ")

    combined = f" {brand or ''} {title or ''} {slug} ".upper()
    for b in sorted(ALL_TOP_BRANDS, key=lambda x: -len(x)):
        pattern = r"(?:\b|_)" + re.escape(b) + r"(?:\b|_)"
        if re.search(pattern, combined):
            return b
    return None


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in TRUE_VALUES


def _ajio_id_from_url(url: str) -> Optional[str]:
    match = re.search(r"/p/([A-Za-z0-9_\-]+)", url)
    return match.group(1) if match else None


def load_shirts(csv_path: str, require_ajio: bool = True) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse and validate the shirt inventory. Returns (rows, errors)."""
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []

    if not os.path.exists(csv_path):
        return rows, [f"Inventory file not found: {csv_path}"]

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for line_no, raw in enumerate(reader, start=2):
            title = (raw.get("title") or "").strip()
            url = (raw.get("url") or "").strip()
            brand = (raw.get("brand") or "AJIO").strip()
            category = (raw.get("category") or "Shirt").strip()
            image_url = (raw.get("image_url") or "").strip()
            if image_url and "ajio.com" not in urlparse(image_url).netloc.lower():
                errors.append(f"line {line_no}: image_url is not on ajio.com (ignored)")
                image_url = ""

            if not title:
                errors.append(f"line {line_no}: missing title")
                continue
            if not url.lower().startswith(("http://", "https://")):
                errors.append(f"line {line_no}: url must start with http(s)")
                continue
            if require_ajio and "ajio.com" not in urlparse(url).netloc.lower():
                errors.append(f"line {line_no}: not an ajio.com URL")
                continue

            try:
                price = float(str(raw.get("price", "")).replace(",", "").strip())
                mrp = float(str(raw.get("mrp", "")).replace(",", "").strip())
            except ValueError:
                errors.append(f"line {line_no}: price/mrp must be numbers")
                continue

            if price <= 0 or mrp < price:
                errors.append(f"line {line_no}: invalid price/mrp")
                continue

            product_id = (raw.get("product_id") or "").strip() or _ajio_id_from_url(url)
            if not product_id:
                errors.append(f"line {line_no}: could not determine product_id")
                continue

            rows.append({
                "product_id": f"AJIO-{product_id}",
                "title": title,
                "brand": brand,
                "category": category,
                "price": price,
                "mrp": mrp,
                "image_url": image_url,
                "url": url,
                "price_verified": _as_bool(raw.get("price_verified"), default=True),
            })

    return rows, errors


def _generate_hashtags(product: Product, brand: Optional[str]) -> str:
    """Generate clickable Telegram hashtags for category, brand, and budget filtering."""
    tags = ["#AJIO"]
    if brand:
        safe_brand = re.sub(r"[^A-Za-z0-9]+", "", brand)
        if safe_brand:
            tags.append(f"#{safe_brand}")

    title_cat = f"{product.title} {product.category}".lower()
    if "t-shirt" in title_cat or "tshirt" in title_cat or "tee" in title_cat:
        tags.append("#TShirts")
    elif "shirt" in title_cat:
        tags.append("#Shirts")
    elif "kurta" in title_cat or "kurti" in title_cat:
        tags.append("#Kurtas")
    elif any(k in title_cat for k in ("shoe", "footwear", "sneaker", "running")):
        tags.append("#Footwear")
    elif any(k in title_cat for k in ("sandal", "slipper", "slide", "flip")):
        tags.append("#Slides")
    elif "jean" in title_cat:
        tags.append("#Jeans")
    elif "kid" in title_cat:
        tags.append("#KidsWear")

    if 0 < product.price <= 300:
        tags.append("#Under300")
    elif 0 < product.price <= 500:
        tags.append("#Under500")

    if product.discount_pct >= 70:
        tags.append("#MegaClearance")

    return " ".join(tags)


def build_shirt_caption(
    product: Product,
    tracking_url: str,
    brand: Optional[str] = None,
) -> str:
    """Build a modern, high-converting, compact Telegram caption.

    Eliminates bulky divider lines and raw URL spam for a sleek mobile view.
    """
    top_brand = brand or extract_top_brand(product.title, product.url)

    # 1. Clean Punchy Header
    if top_brand and product.discount_pct >= 70:
        header = f"🚨 <b>{product.discount_pct}% OFF: {html.escape(top_brand)}</b> 🚨\n\n"
    elif top_brand:
        header = f"🔥 <b>TOP BRAND: {html.escape(top_brand)}</b> 🔥\n\n"
    elif product.discount_pct >= 70:
        header = f"🚨 <b>MEGA DEAL ({product.discount_pct}% OFF)</b> 🚨\n\n"
    else:
        header = ""

    # 2. Title & Star Rating
    rating_line = ""
    if product.rating and product.rating > 0:
        reviews_str = f" ({product.rating_count:,} reviews)" if product.rating_count else ""
        rating_line = f"⭐ <b>Rating:</b> {product.rating:.1f}/5{reviews_str}\n"
    elif top_brand:
        rating_line = "⭐ <b>Top Brand Quality Choice</b>\n"

    body = f"<b>{html.escape(product.title)}</b>\n{rating_line}\n"

    # 3. Compact Price Line
    if product.price_verified and product.price > 0:
        price_block = (
            f"💰 <b>Deal Price:</b> Rs {product.price:,.0f} ONLY <s>(MRP: Rs {product.mrp:,.0f})</s> <b>({product.discount_pct}% OFF)</b>\n"
            "⚡ <i>Check available sizes on AJIO before stock runs out!</i>\n\n"
        )
    else:
        price_block = "Check the latest price and sizes on AJIO.\n\n"

    # 4. Clean Buy Button / Short Link (Never spills ugly long tracking codes)
    cta_label = "Tap Here to Buy on AJIO" if top_brand else "View Deal on AJIO"
    if len(tracking_url) <= 45:
        cta_block = (
            f'👉 <a href="{tracking_url}"><b>{cta_label}</b></a>\n'
            f"🔗 <b>Link:</b> {tracking_url}\n\n"
        )
    else:
        cta_block = f'👉 <a href="{tracking_url}"><b>{cta_label} (Official Store)</b></a>\n\n'

    # 5. Clickable Search Hashtags
    hashtags = _generate_hashtags(product, top_brand)
    hashtag_block = f"{hashtags}\n\n" if hashtags else ""

    # 6. Disclosure
    disclosure = "<i>Affiliate link - I may earn a commission at no extra cost to you.</i>"

    return f"{header}{body}{price_block}{cta_block}{hashtag_block}{disclosure}"


def _already_posted(db: Any, product_id: str, dry_run: bool) -> bool:
    if db.is_product_posted(product_id):
        return True
    is_seen = getattr(db, "is_seen", None)
    if not callable(is_seen):
        return False
    try:
        return bool(is_seen(product_id, include_dry_run=dry_run))
    except TypeError:
        return bool(is_seen(product_id))


def _mark_seen(db: Any, product_id: str, dry_run: bool) -> None:
    marker = getattr(db, "mark_seen", None)
    if callable(marker):
        marker(product_id, dry_run=dry_run)


def publish_rows(
    rows: List[Dict[str, Any]],
    max_posts: Optional[int] = None,
    settings: Optional[Settings] = None,
    db: Optional[Any] = None,
    publisher: Optional[Any] = None,
    card_fn=None,
    sleep_fn=time.sleep,
    errors: Optional[List[str]] = None,
    force: bool = False,
    shorten_fn: Optional[Any] = None,
) -> Dict[str, Any]:
    """Publish already-validated inventory rows (CSV, feed or Google Sheet)."""
    s = settings or get_settings()
    db = db or Database(s.db_path)
    if hasattr(db, "init"):
        db.init()
    publisher = publisher or TelegramPublisher(
        s.telegram_bot_token, s.telegram_chat_id, dry_run=s.dry_run
    )
    card_fn = card_fn or download_or_create_dress_card

    summary = {
        "status": "success",
        "dry_run": s.dry_run,
        "posted": 0,
        "pinned": 0,
        "skipped": 0,
        "rejected": 0,
        "posted_ids": [],
        "errors": list(errors or []),
    }

    if not rows:
        summary["status"] = "error"
        summary["message"] = "No valid rows"
        return summary

    limit = max_posts if max_posts is not None else s.max_posts_per_day
    unlimited = limit <= 0
    posted_this_run = set()
    pinned_count = 0

    for idx, row in enumerate(rows):
        if not unlimited and summary["posted"] >= limit:
            break

        product_id = row["product_id"]
        if product_id in posted_this_run:
            summary["skipped"] += 1
            continue
        if not force and _already_posted(db, product_id, s.dry_run):
            summary["skipped"] += 1
            continue

        link = resolve_affiliate_link(product_id, row["url"], s, subid="deals_shirts")
        if not link.is_eligible:
            summary["rejected"] += 1
            log.warning("Rejected %s: %s", row["title"], link.reason)
            continue

        price = float(row.get("price") or 0)
        mrp = float(row.get("mrp") or 0)
        price_verified = bool(row.get("price_verified")) and price > 0 and mrp >= price
        discount_pct = int(round((1.0 - (price / mrp)) * 100)) if price_verified and mrp > 0 else 0
        top_brand_name = extract_top_brand(row["title"], row["url"], row.get("brand", ""))

        final_url = link.tracking_url
        if shorten_fn is not None:
            final_url = shorten_fn(link.tracking_url)
        elif getattr(s, "shorten_affiliate_links", False):
            final_url = shorten_any_affiliate_link(link.tracking_url)

        product = Product(
            product_id=product_id,
            title=row["title"],
            url=row["url"],
            price=price,
            mrp=mrp,
            category=row.get("category") or "Shirt",
            image_url=row.get("image_url", ""),
            source=link.provider,
            price_verified=price_verified,
            rating=row.get("rating"),
            rating_count=row.get("rating_count"),
        )
        caption = build_shirt_caption(product, final_url, brand=top_brand_name)

        card_path = None
        if row.get("image_url"):
            safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", product_id)
            card_path = f"data/shirt_card_{safe_id}.jpg"
            try:
                card_fn(
                    image_url=row["image_url"],
                    brand=top_brand_name or row.get("brand") or "AJIO",
                    title=row["title"],
                    price=price,
                    mrp=mrp,
                    discount_pct=discount_pct,
                    output_path=card_path,
                )
            except Exception as exc:
                log.warning("Card generation failed for %s: %s", product_id, exc)
                card_path = None

        try:
            enforce_caption_safety(row["title"], caption, product)
            log.info(
                "Publishing %s (brand: %s, image: %s)",
                product_id,
                top_brand_name or "generic",
                os.path.basename(card_path) if card_path else "none",
            )
            deal_res = publisher.send_deal(caption=caption, image_path=card_path, tracking_url=final_url)

            # Auto-pin hero deal to Telegram channel (Top Brand with >=50% OFF, or any deal with >=75% OFF)
            is_hero_deal = (top_brand_name is not None and discount_pct >= 50) or discount_pct >= 75
            if is_hero_deal and pinned_count < 1 and hasattr(publisher, "pin_message"):
                deal_msg_id = None
                if isinstance(deal_res, dict):
                    deal_msg_id = (deal_res.get("result") or {}).get("message_id") or deal_res.get("message_id")
                if deal_msg_id:
                    try:
                        if publisher.pin_message(deal_msg_id, disable_notification=True):
                            pinned_count += 1
                            summary["pinned"] = pinned_count
                            log.info("📌 Pinned hero deal message %s: %s (%s%% OFF)", deal_msg_id, row["title"], discount_pct)
                    except Exception as pin_exc:
                        log.warning("Could not pin deal message %s: %s", deal_msg_id, pin_exc)

        except ContentRejected as exc:
            summary["rejected"] += 1
            log.warning("Caption rejected for %s: %s", product_id, exc)
            continue
        except Exception as exc:
            summary["rejected"] += 1
            summary["errors"].append(f"{product_id}: {type(exc).__name__}: {exc}")
            log.error("Failed to post %s: %s", product_id, exc)
            continue

        if not s.dry_run:
            db.record_post(
                product_id=product_id,
                provider=link.provider,
                affiliate_url=final_url,
                headline=row["title"],
                caption=caption,
            )
        _mark_seen(db, product_id, s.dry_run)
        posted_this_run.add(product_id)
        summary["posted"] += 1
        summary["posted_ids"].append(product_id)
        log.info("Posted shirt %s/%s: %s", summary["posted"], "all" if unlimited else limit, row["title"])

        if not s.dry_run and (unlimited or summary["posted"] < limit) and idx < len(rows) - 1:
            sleep_fn(s.post_interval_seconds)

    if summary["posted"] == 0 and summary["rejected"] > 0:
        summary["status"] = "error"
        summary["message"] = "Every candidate was rejected or failed - see errors"

    return summary


def publish_shirts(
    csv_path: Optional[str] = None,
    max_posts: Optional[int] = None,
    settings: Optional[Settings] = None,
    db: Optional[Any] = None,
    publisher: Optional[Any] = None,
    card_fn=None,
    sleep_fn=time.sleep,
) -> Dict[str, Any]:
    s = settings or get_settings()
    csv_path = csv_path or s.shirts_csv
    rows, errors = load_shirts(csv_path)
    if not rows:
        return {
            "status": "error",
            "message": "No valid shirt rows",
            "errors": errors,
            "posted": 0,
        }
    return publish_rows(
        rows,
        max_posts=max_posts,
        settings=s,
        db=db,
        publisher=publisher,
        card_fn=card_fn,
        sleep_fn=sleep_fn,
        errors=errors,
    )
