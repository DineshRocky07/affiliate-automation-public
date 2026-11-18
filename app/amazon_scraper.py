"""Extracts clean real product titles, prices, and high-res images directly from Amazon."""
import html
import logging
import re
import urllib.request
from typing import Optional, Dict

log = logging.getLogger(__name__)


def fetch_amazon_product_details(url_or_asin: str) -> Optional[Dict[str, str]]:
    """Extracts exact product details and real photo from Amazon India."""
    asin_match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url_or_asin)
    asin = asin_match.group(1) if asin_match else url_or_asin.strip()

    target_url = f"https://www.amazon.in/dp/{asin}"
    req = urllib.request.Request(target_url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            page_html = resp.read().decode("utf-8", errors="ignore")

            # 1. Product Title
            title_m = re.search(r'<span id="productTitle"[^>]*>(.*?)</span>', page_html, re.DOTALL)
            title = html.unescape(title_m.group(1).strip()) if title_m else "Exclusive Amazon Deal"

            # 2. Live Price
            price_m = re.search(r'class="a-price-whole">([0-9,]+)', page_html)
            price = price_m.group(1).replace(",", "") if price_m else None

            # 3. High-res product photo from Amazon image CDN
            imgs = re.findall(r'https://m\.media-amazon\.com/images/I/[A-Za-z0-9\-_%]+\.jpg', page_html)
            # Find the best quality product image
            product_img = None
            for candidate in imgs:
                if len(candidate) > 40:
                    product_img = candidate
                    break

            return {
                "asin": asin,
                "title": title,
                "price": price,
                "image_url": product_img,
                "original_url": target_url
            }
    except Exception as e:
        log.error("Failed to fetch Amazon details for %s: %s", asin, e)
        return None
