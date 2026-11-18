"""
Curated Top-Brand AJIO Deal Fetcher (Runs on your PC)
===================================================
100% Free - No ScraperAPI / Apify required.
Uses your PC's real Indian residential IP (cannot be blocked by Akamai).

Filters:
1. Price <= 500
2. Rating >= 3.7 (or 4.0 preferred)
3. Top Brands only (Puma, Levi's, DNMX, Netplay, Avaasa, USPA, Flying Machine, etc.)
4. Discount >= 50%
"""

import logging
import os
import re
import time
from typing import Any, Dict, List, Set
import requests

from app.config import get_settings
from app.google_sheet_source import _open_worksheet

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# 🏷️ TOP BRANDS LIST (Trusted by Indian shoppers)
TOP_BRANDS = [
    "PUMA", "LEVI'S", "LEVIS", "U.S. POLO ASSN.", "USPA", "FLYING MACHINE", 
    "DNMX", "NETPLAY", "AVAASA", "TEAMSPIRIT", "GAP", "CAMPUS", 
    "RED TAPE", "ROADSTER", "HIGHLANDER", "MAX", "JOHN PLAYERS",
    "PETER ENGLAND", "VAN HEUSEN", "ALLEN SOLLY", "ARROW", "WRANGLER",
    "SPYKAR", "MUFTI", "LEE", "CRAZYMONK"
]

MAX_PRICE = 500
MIN_DISCOUNT_PCT = 50
MIN_RATING = 3.7

SOURCES = [
    {
        "label": "Offers 50%+ Off",
        "url": "https://www.ajio.com/api/curated/min50percentoff-curated-437897?fields=SITE&format=json&curated=true&curatedid=min50percentoff-curated-437897&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    },
    {
        "label": "Men - Shirts & Tops",
        "url": "https://www.ajio.com/api/category/830216001?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    },
    {
        "label": "Men - T-Shirts",
        "url": "https://www.ajio.com/api/category/830216010?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    },
    {
        "label": "Women - Kurtas & Dresses",
        "url": "https://www.ajio.com/api/category/830303011?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    },
    {
        "label": "Women - Western Tops",
        "url": "https://www.ajio.com/api/category/830303002?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    },
    {
        "label": "Kids Wear",
        "url": "https://www.ajio.com/api/category/830401?fields=SITE&format=json&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    },
    {
        "label": "Top Brands Sale",
        "url": "https://www.ajio.com/api/curated/brand-sale-curated?fields=SITE&format=json&curated=true&curatedid=brand-sale-curated&platform=Msite&store=ajio&gridColumns=2&advfilter=true"
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.ajio.com/",
    "Origin": "https://www.ajio.com"
}


def build_page_url(base: str, page: int) -> str:
    sep = "&" if "?" in base else "?"
    url = re.sub(r"([?&])currentPage=\d+", "", base)
    url = re.sub(r"([?&])pageSize=\d+", "", url)
    return f"{url}{sep}currentPage={page}&pageSize=45&sort=newn"


def is_brand_match(brand_name: str) -> bool:
    b_upper = brand_name.upper()
    return any(tb in b_upper for tb in TOP_BRANDS)


def fetch_category_deals(category_url: str, label: str, max_pages: int = 3) -> List[Dict[str, Any]]:
    session = requests.Session()
    session.headers.update(HEADERS)
    deals: List[Dict[str, Any]] = []

    for page in range(max_pages):
        page_url = build_page_url(category_url, page)
        try:
            r = session.get(page_url, timeout=12)
            if r.status_code != 200:
                log.warning("[%s] Page %d returned HTTP %d", label, page + 1, r.status_code)
                break

            data = r.json()
            products = data.get("products", [])
            if not products:
                break

            for p in products:
                price = float(p.get("price", {}).get("value") or 0)
                mrp = float(p.get("wasPriceData", {}).get("value") or 0)
                rating = float(p.get("averageRating") or p.get("rating") or 0)
                brand = (p.get("fnlColorVariantData", {}).get("brandName") or p.get("brandName") or "").strip()
                title = (p.get("name") or "").strip()
                rel_url = p.get("url") or ""

                if not rel_url or price <= 0:
                    continue

                # 1. Price check (Under 500)
                if price > MAX_PRICE:
                    continue

                # 2. Discount check (>= 50% OFF)
                discount = int(round(((mrp - price) / mrp) * 100)) if mrp > price else 0
                if discount < MIN_DISCOUNT_PCT:
                    continue

                # 3. Rating check (if rated, must be >= 3.7)
                if 0 < rating < MIN_RATING:
                    continue

                # 4. Brand match
                if brand and not is_brand_match(brand):
                    # Also check if title contains brand name
                    if not any(b in title.upper() for b in TOP_BRANDS):
                        continue

                # Full secure URL
                full_url = f"https://www.ajio.com{rel_url}"

                # Image
                images = p.get("images", [])
                img = ""
                if images and images[0].get("url"):
                    u = images[0]["url"]
                    img = u if u.startswith("http") else f"https://assets.ajio.com{u}"

                deals.append({
                    "title": title,
                    "url": full_url,
                    "price": str(int(price)),
                    "mrp": str(int(mrp)),
                    "image_url": img,
                    "platform": "ajio",
                    "brand": brand,
                    "rating": rating,
                    "discount": discount
                })

            time.sleep(1.2)
        except Exception as e:
            log.error("[%s] Error on page %d: %s", label, page + 1, e)
            break

    return deals


def sync_curated_deals_to_sheet(target_new_deals: int = 50) -> int:
    settings = get_settings()
    wks = _open_worksheet(settings.google_sheet_id, settings.google_worksheet, settings.google_credentials_file)
    existing_rows = wks.get_all_values()

    seen_urls: Set[str] = set()
    if len(existing_rows) > 1:
        for r in existing_rows[1:]:
            if len(r) > 1 and r[1]:
                seen_urls.add(r[1].strip().rstrip("?"))

    log.info("Found %d existing deals in Google Sheet.", len(seen_urls))

    added_count = 0
    for src in SOURCES:
        if added_count >= target_new_deals:
            log.info("Reached target of %d fresh curated deals. Stopping.", target_new_deals)
            break

        log.info("Scanning category: %s", src["label"])
        deals = fetch_category_deals(src["url"], src["label"])
        
        for d in deals:
            clean_url = d["url"].strip().rstrip("?")
            if clean_url in seen_urls:
                continue

            wks.append_row([
                d["title"],
                clean_url,
                d["price"],
                d["mrp"],
                d["image_url"],
                d["platform"]
            ])
            seen_urls.add(clean_url)
            added_count += 1
            log.info("Added: [%s] %s | Rs %s (%s%% OFF) | %s*", 
                     d.get("brand") or "Brand", d["title"][:40], d["price"], d["discount"], d.get("rating", 0))

            if added_count >= target_new_deals:
                break

    log.info("=== FINISHED! Added %d new curated top-brand deals to Google Sheet ===", added_count)
    return added_count


if __name__ == "__main__":
    sync_curated_deals_to_sheet(target_new_deals=30)
