"""Creates real product dress cards with photo, price badges, and brand tags."""
import io
import logging
import os
import urllib.request

from PIL import Image, ImageDraw

from app.image_utils import fit_image, load_font, strip_emoji

log = logging.getLogger(__name__)


def download_or_create_dress_card(
    image_url: str,
    brand: str,
    title: str,
    price: float,
    mrp: float,
    discount_pct: int,
    output_path: str = "data/product_card.jpg"
) -> str:
    """Creates a modern full-bleed product image card with floating discount and price pills."""
    card_w, card_h = 700, 900
    bg = Image.new("RGB", (card_w, card_h), color="#f8fafc")

    try:
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            product_img = Image.open(io.BytesIO(resp.read()))
        # Full-bleed product image fills the card cleanly
        bg.paste(fit_image(product_img, card_w, card_h), (0, 0))
    except Exception as exc:
        log.warning("Could not download product image (%s): %s", image_url, exc)
        fallback = ImageDraw.Draw(bg)
        fallback.rectangle([0, 0, card_w, card_h], fill="#0f172a")
        fallback.text((150, 420), "AJIO EXCLUSIVE STYLE", fill="#ffffff", font=load_font(28))

    draw = ImageDraw.Draw(bg)
    badge_font = load_font(24)
    brand_font = load_font(20)
    price_font = load_font(32)
    small_font = load_font(18)

    # 1. Top-Left Floating Badge: Discount Pill
    draw.rounded_rectangle([25, 25, 210, 78], radius=10, fill="#dc2626")
    draw.text((40, 36), f"{discount_pct}% OFF", fill="#ffffff", font=badge_font)

    # 2. Top-Left Badge 2: Brand Tag Pill
    if brand:
        brand_clean = strip_emoji(brand)[:18].upper()
        draw.rounded_rectangle([25, 90, 235, 134], radius=8, fill="#0f172a")
        draw.text((38, 98), brand_clean, fill="#38bdf8", font=brand_font)

    # 3. Bottom-Right Floating Price Tag Pill
    draw.rounded_rectangle([card_w - 265, card_h - 95, card_w - 25, card_h - 25], radius=12, fill="#0f172a")
    draw.text((card_w - 250, card_h - 85), f"Rs {price:,.0f}", fill="#22c55e", font=price_font)
    draw.text((card_w - 125, card_h - 78), f"Rs {mrp:,.0f}", fill="#94a3b8", font=small_font)
    draw.line([card_w - 127, card_h - 66, card_w - 40, card_h - 66], fill="#ef4444", width=2)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    bg.save(output_path, "JPEG", quality=95)
    return output_path
