"""Attractive deal banner generator using Pillow (no fabricated claims)."""
import os
import re

from PIL import Image, ImageDraw

from app.image_utils import load_font, strip_emoji


def create_deal_banner(title: str, discount_text: str = "", subtitle: str = "AJIO EXCLUSIVE", output_path: str = "data/deal_banner.jpg") -> str:
    """Creates a clean dark-mode banner for Telegram."""
    width, height = 800, 460
    img = Image.new("RGB", (width, height), color="#090d16")
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width - 1, height - 1], outline="#1e293b", width=3)

    badge_font = load_font(22)
    title_font = load_font(34)
    small_font = load_font(20)
    cta_font = load_font(22)

    if discount_text:
        draw.rounded_rectangle([45, 45, 275, 95], radius=12, fill="#dc2626")
        draw.text((65, 58), strip_emoji(discount_text).upper(), fill="#ffffff", font=badge_font)

    draw.rounded_rectangle([300, 45, 500, 95], radius=12, fill="#1e293b")
    draw.text((320, 58), subtitle, fill="#38bdf8", font=badge_font)

    clean_title = strip_emoji(re.sub(r"[^\w\s\-,!&%']", "", title)).strip()
    words = clean_title.split()
    lines = []
    current = []
    for word in words:
        current.append(word)
        if len(" ".join(current)) > 30:
            lines.append(" ".join(current))
            current = []
    if current:
        lines.append(" ".join(current))

    y_text = 150
    for line in lines[:2]:
        draw.text((45, y_text), line, fill="#f8fafc", font=title_font)
        y_text += 50

    draw.text((45, 285), "Official store link  |  Check current price before buying", fill="#94a3b8", font=small_font)
    draw.text((45, 320), "Affiliate link - commission at no extra cost to you", fill="#94a3b8", font=small_font)

    draw.rounded_rectangle([45, 365, 380, 420], radius=10, fill="#16a34a")
    draw.text((75, 380), "TAP LINK BELOW TO BUY", fill="#ffffff", font=cta_font)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "JPEG", quality=92)
    return output_path
