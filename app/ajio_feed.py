"""Fetch AJIO product rows from a real feed URL (JSON or CSV).

The AJIO ACE/Trackier dashboard is the only source of the feed URL. Trackier
authenticates with the ``X-Api-Key`` header (also passed as ``apiKey`` query
param). Nothing here invents products: if the feed is missing or invalid, the
existing CSV inventory is used unchanged.
"""
import csv
import io
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

HEADER = ["product_id", "title", "brand", "category", "price", "mrp", "image_url", "url", "price_verified"]

URL_KEYS = ("url", "product_url", "productUrl", "deeplink", "deep_link", "link", "landing_url", "landingUrl")
TITLE_KEYS = ("title", "name", "product_name", "productName", "product_title", "productTitle")
ID_KEYS = ("product_id", "productId", "id", "sku", "product_code", "productCode")
PRICE_KEYS = ("price", "selling_price", "sellingPrice", "sale_price", "salePrice", "discounted_price")
MRP_KEYS = ("mrp", "list_price", "listPrice", "original_price", "originalPrice", "strike_price")
IMAGE_KEYS = ("image_url", "imageUrl", "image", "thumbnail", "thumb", "image_link", "imageLink")
BRAND_KEYS = ("brand", "brand_name", "brandName")
CATEGORY_KEYS = ("category", "category_name", "categoryName")
LIST_KEYS = ("data", "products", "items", "offers", "result", "results", "list")


def _first(item: Dict[str, Any], keys) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _parse_money(value: str) -> Optional[float]:
    cleaned = re.sub(r"[^0-9.]", "", value or "")
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return number if number > 0 else None


def _ajio_id_from_url(url: str) -> Optional[str]:
    match = re.search(r"/p/([A-Za-z0-9_\-]+)", url)
    return match.group(1) if match else None


def normalize_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    url = _first(item, URL_KEYS)
    title = _first(item, TITLE_KEYS)
    if not url or not title:
        return None
    if "ajio.com" not in urlparse(url).netloc.lower():
        return None

    price = _parse_money(_first(item, PRICE_KEYS))
    mrp = _parse_money(_first(item, MRP_KEYS)) or price
    if not price or not mrp or mrp < price:
        return None

    product_id = _first(item, ID_KEYS) or _ajio_id_from_url(url) or ""
    if not product_id:
        return None

    return {
        "product_id": product_id if product_id.startswith("AJIO-") else f"AJIO-{product_id}",
        "title": title,
        "brand": _first(item, BRAND_KEYS) or "AJIO",
        "category": _first(item, CATEGORY_KEYS) or "Shirt",
        "price": price,
        "mrp": mrp,
        "image_url": _first(item, IMAGE_KEYS),
        "url": url,
        "price_verified": True,
    }


def _extract_items(body: Any) -> List[Dict[str, Any]]:
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if isinstance(body, dict):
        for key in LIST_KEYS:
            value = body.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
            if isinstance(value, dict):
                nested = _extract_items(value)
                if nested:
                    return nested
    return []


def parse_feed(text: str, content_type: str = "", url: str = "") -> Tuple[List[Dict[str, Any]], List[str]]:
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    is_csv = "csv" in (content_type or "").lower() or url.lower().split("?")[0].endswith(".csv")

    try:
        if is_csv:
            items = list(csv.DictReader(io.StringIO(text)))
        else:
            import json
            items = _extract_items(json.loads(text))
    except Exception as exc:
        return [], [f"Could not parse feed: {type(exc).__name__}"]

    if not items:
        return [], ["Feed returned no product items (check the endpoint or response shape)"]

    for index, item in enumerate(items, start=1):
        row = normalize_item(item)
        if row is None:
            errors.append(f"item {index}: skipped (missing/invalid ajio url, title, price or id)")
            continue
        rows.append(row)

    return rows, errors


def fetch_feed_rows(
    feed_url: str,
    api_key: str = "",
    timeout: int = 30,
    session: Optional[Any] = None,
    limit: int = 0,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    if not feed_url:
        return [], ["AJIO_FEED_URL is not configured"]

    session = session or requests
    headers = {"Accept": "application/json, text/csv, */*"}
    if api_key:
        headers["X-Api-Key"] = api_key
        headers["X-API-Key"] = api_key
    params = {"apiKey": api_key} if api_key else {}
    if limit:
        params.update({"limit": limit, "page_size": limit})

    try:
        response = session.get(feed_url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
    except Exception as exc:
        return [], [f"Feed request failed: {type(exc).__name__}"]

    return parse_feed(response.text, response.headers.get("Content-Type", ""), feed_url)


def merge_into_inventory(rows: List[Dict[str, Any]], csv_path: str) -> int:
    """Append new rows to the shirt inventory, deduplicated by product_id."""
    existing: List[Dict[str, Any]] = []
    seen = set()

    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pid = (row.get("product_id") or "").strip()
                if pid and pid not in seen:
                    seen.add(pid)
                    existing.append(row)

    added = 0
    for row in rows:
        pid = row["product_id"]
        if pid in seen:
            continue
        seen.add(pid)
        existing.append(row)
        added += 1

    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER, extrasaction="ignore")
        writer.writeheader()
        for row in existing:
            writer.writerow({key: row.get(key, "") for key in HEADER})

    return added
