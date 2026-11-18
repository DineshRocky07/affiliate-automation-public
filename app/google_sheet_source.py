"""Read product rows from a Google Sheet published as CSV (mobile inbox).

This is the human's ~10%: they add AJIO product links from their phone.
No OAuth is needed. In Google Sheets use:
    File > Share > Publish to web > Comma-separated values (.csv)
and paste that URL into ``GOOGLE_SHEET_CSV_URL``.

Rows are normalized to the same shape as ``data/shirts.csv``. Duplicates are
removed by product_id and Flipkart is always rejected. Prices are optional:
without them the post says "Check the latest price".
"""
import csv
import io
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from app.ajio_feed import _ajio_id_from_url, _parse_money

log = logging.getLogger(__name__)

BLOCKED_HOSTS = ("flipkart.com",)
ENABLED_PLATFORMS = ("ajio",)

URL_KEYS = ("url", "link", "product_url", "product_link", "productlink", "ajio_url", "deal_url")
TITLE_KEYS = ("title", "name", "product", "product_name", "product_title", "deal_title")
BRAND_KEYS = ("brand", "brand_name")
CATEGORY_KEYS = ("category", "category_name", "product_category")
PRICE_KEYS = (
    "price", "selling_price", "sale_price", "deal_price", "discounted_price",
    "offer_price", "current_price", "final_price",
)
MRP_KEYS = ("mrp", "list_price", "original_price", "strike_price", "market_price", "regular_price")
IMAGE_KEYS = (
    "image_url", "image", "image_link", "imagelink", "photo", "photo_url",
    "product_image", "thumbnail", "thumbnail_url", "img",
)
ID_KEYS = ("product_id", "id", "sku", "product_code", "productcode")
PLATFORM_KEYS = ("platform", "provider", "store", "merchant")
RATING_KEYS = ("rating", "ratings", "stars", "avg_rating", "average_rating")
RATING_COUNT_KEYS = ("rating_count", "ratings_count", "reviews", "review_count", "num_reviews")
IMAGE_FORMULA_RE = re.compile(r"""IMAGE\(\s*["']([^"']+)["']""", re.IGNORECASE)


def _header_key(name: Any) -> str:
    """Normalize a header so 'Image URL', 'image_url' and 'image-url' all match."""
    text = re.sub(r"[\s\-/]+", "_", str(name).strip().lower())
    text = re.sub(r"[^a-z0-9_]+", "", text)
    return text.strip("_")


def _normalized(row: Dict[str, Any]) -> Dict[str, str]:
    return {
        _header_key(key): str(value).strip() if value is not None else ""
        for key, value in row.items()
        if key is not None
    }


def _get(row: Dict[str, str], keys) -> str:
    for key in keys:
        value = row.get(_header_key(key))
        if value:
            return value
    return ""


def _extract_image_url(value: str) -> str:
    """Support plain URLs and Google Sheets =IMAGE("...") formulas."""
    text = (value or "").strip()
    match = IMAGE_FORMULA_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip().strip('"\'')


def normalize_sheet_row(row: Dict[str, Any], default_platform: str = "ajio") -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Turn one sheet row into an inventory row, or return a rejection reason."""
    data = _normalized(row)
    url = _get(data, URL_KEYS)
    title = _get(data, TITLE_KEYS)
    platform = (_get(data, PLATFORM_KEYS) or default_platform).strip().lower()

    if not url or not title:
        return None, "missing url or title"
    if not url.lower().startswith(("http://", "https://")):
        return None, "url must start with http(s)"
    # Strip empty trailing '?' or '&' left when copying URLs from a browser bar
    if url.endswith(("?", "&")) and not urlparse(url).query:
        url = url.rstrip("?&")

    host = urlparse(url).netloc.lower()
    if any(blocked in host for blocked in BLOCKED_HOSTS):
        return None, "Flipkart is disabled by policy"
    if platform not in ENABLED_PLATFORMS:
        return None, f"provider '{platform}' is not enabled yet (only AJIO)"
    if "ajio.com" not in host:
        return None, "not an ajio.com URL"

    product_id = _get(data, ID_KEYS) or _ajio_id_from_url(url) or ""
    if not product_id:
        return None, "could not determine product_id"
    product_id = product_id if product_id.startswith("AJIO-") else f"AJIO-{product_id}"

    price = _parse_money(_get(data, PRICE_KEYS))
    mrp = _parse_money(_get(data, MRP_KEYS))
    price_verified = bool(price and mrp and mrp >= price)
    if not price_verified:
        price, mrp = price or 0.0, mrp or 0.0

    image_url = _extract_image_url(_get(data, IMAGE_KEYS))
    if image_url and not image_url.lower().startswith(("http://", "https://")):
        log.warning("%s: ignoring image_url that is not an http(s) URL", product_id)
        image_url = ""

    rating_val = None
    try:
        raw_r = _get(data, RATING_KEYS)
        if raw_r:
            rating_val = float(raw_r)
    except ValueError:
        pass

    rating_count_val = None
    try:
        raw_rc = _get(data, RATING_COUNT_KEYS)
        if raw_rc:
            rating_count_val = int(raw_rc.replace(",", ""))
    except ValueError:
        pass

    return {
        "product_id": product_id,
        "title": title,
        "brand": _get(data, BRAND_KEYS) or "AJIO",
        "category": _get(data, CATEGORY_KEYS) or "Shirt",
        "price": price,
        "mrp": mrp,
        "image_url": image_url,
        "url": url,
        "price_verified": price_verified,
        "rating": rating_val,
        "rating_count": rating_count_val,
    }, None


def parse_records(items: List[Dict[str, Any]], default_platform: str = "ajio") -> Tuple[List[Dict[str, Any]], List[str]]:
    """Normalize already-parsed sheet records (CSV rows or API dicts)."""
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    seen = set()

    if not items:
        return [], ["Sheet has no data rows"]

    for index, item in enumerate(items, start=2):
        row, reason = normalize_sheet_row(item, default_platform=default_platform)
        if row is None:
            errors.append(f"row {index}: {reason}")
            continue
        if row["product_id"] in seen:
            errors.append(f"row {index}: duplicate {row['product_id']} skipped")
            continue
        seen.add(row["product_id"])
        rows.append(row)

    return rows, errors


def parse_sheet(text: str, default_platform: str = "ajio") -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse a published Google Sheet CSV export."""
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
        items = list(reader)
    except Exception as exc:
        return [], [f"Could not parse sheet: {type(exc).__name__}"]
    return parse_records(items, default_platform=default_platform)


def fetch_sheet_rows(
    csv_url: str,
    timeout: int = 30,
    session: Optional[Any] = None,
    default_platform: str = "ajio",
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Download and parse the published Google Sheet CSV."""
    if not csv_url:
        return [], ["GOOGLE_SHEET_CSV_URL is not configured"]

    session = session or requests
    try:
        response = session.get(csv_url, timeout=timeout)
        response.raise_for_status()
    except Exception as exc:
        return [], [f"Sheet request failed: {type(exc).__name__}"]

    return parse_sheet(response.text, default_platform=default_platform)


SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


def _open_worksheet(sheet_id: str, worksheet: str, credentials_file: str, client_factory=None):
    if client_factory is not None:
        client = client_factory(credentials_file)
    else:
        import gspread
        from google.oauth2.service_account import Credentials

        credentials = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
        client = gspread.authorize(credentials)
    return client.open_by_key(sheet_id).worksheet(worksheet)


def fetch_sheet_rows_api(
    sheet_id: str,
    worksheet: str,
    credentials_file: str,
    client_factory=None,
    default_platform: str = "ajio",
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Read rows with a Google service account (no publishing needed)."""
    if not sheet_id or not credentials_file:
        return [], ["GOOGLE_SHEET_ID or GOOGLE_CREDENTIALS_FILE is not configured"]
    if not os.path.exists(credentials_file):
        return [], [f"Credentials file not found: {credentials_file}"]

    try:
        ws = _open_worksheet(sheet_id, worksheet, credentials_file, client_factory=client_factory)
        records = ws.get_all_records()
    except Exception as exc:
        return [], [f"Google Sheet API failed: {type(exc).__name__}: {str(exc)[:120]}"]

    return parse_records(records, default_platform=default_platform)


def clear_processed_rows_api(
    sheet_id: str,
    worksheet: str,
    credentials_file: str,
    product_ids: List[str],
    client_factory=None,
) -> int:
    """Delete rows whose product_id/url was posted this run."""
    if not product_ids:
        return 0

    ws = _open_worksheet(sheet_id, worksheet, credentials_file, client_factory=client_factory)
    values = ws.get_all_values()
    if not values:
        return 0

    header = [_header_key(cell) for cell in values[0]]
    url_col = next((i for i, name in enumerate(header) if name in URL_KEYS), None)
    id_col = next((i for i, name in enumerate(header) if name in ID_KEYS), None)
    if url_col is None and id_col is None:
        raise ValueError("Sheet needs a 'url' or 'product_id' column to clear rows")

    wanted = set(product_ids)
    targets = []
    for row_number, row in enumerate(values[1:], start=2):
        pid = ""
        if id_col is not None and id_col < len(row):
            pid = str(row[id_col]).strip()
        if not pid and url_col is not None and url_col < len(row):
            pid = _ajio_id_from_url(str(row[url_col])) or ""
        if pid and not pid.startswith("AJIO-"):
            pid = f"AJIO-{pid}"
        if pid in wanted:
            targets.append(row_number)

    for row_number in sorted(targets, reverse=True):
        ws.delete_rows(row_number)
    return len(targets)


def _column_value(header_name: str, row: Dict[str, Any], raw_price: str, raw_mrp: str, platform: str) -> str:
    key = _header_key(header_name)
    if key in TITLE_KEYS:
        return str(row["title"])
    if key in URL_KEYS:
        return str(row["url"])
    if key in PRICE_KEYS:
        return str(raw_price).strip() if str(raw_price).strip() else ""
    if key in MRP_KEYS:
        return str(raw_mrp).strip() if str(raw_mrp).strip() else ""
    if key in IMAGE_KEYS:
        return str(row.get("image_url") or "")
    if key in BRAND_KEYS:
        return str(row.get("brand") or "AJIO")
    if key in CATEGORY_KEYS:
        return str(row.get("category") or "Shirt")
    if key in ID_KEYS:
        return str(row["product_id"])
    if key in PLATFORM_KEYS:
        return platform
    return ""


def append_sheet_row(
    settings: Any,
    title: str,
    url: str,
    price: str = "",
    mrp: str = "",
    image_url: str = "",
    platform: str = "ajio",
    client_factory=None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Validate and append one AJIO deal row into the Google Sheet inbox."""
    sheet_id = getattr(settings, "google_sheet_id", "")
    credentials_file = getattr(settings, "google_credentials_file", "")
    worksheet = getattr(settings, "google_worksheet", "deals") or "deals"
    if not sheet_id or not credentials_file:
        return None, "GOOGLE_SHEET_ID or GOOGLE_CREDENTIALS_FILE is not configured"
    if client_factory is None and not os.path.exists(credentials_file):
        return None, f"Credentials file not found: {credentials_file}"

    candidate = {
        "title": title,
        "url": url,
        "price": price,
        "mrp": mrp,
        "image_url": image_url,
        "platform": platform,
    }
    normalized, reason = normalize_sheet_row(candidate, default_platform=platform)
    if normalized is None:
        return None, reason

    try:
        ws = _open_worksheet(sheet_id, worksheet, credentials_file, client_factory=client_factory)
        values = ws.get_all_values()
        if values and values[0]:
            header = [str(col).strip() for col in values[0]]
        else:
            header = ["title", "url", "price", "mrp", "image_url", "platform"]
            ws.append_row(header, value_input_option="USER_ENTERED")

        new_row = [
            _column_value(col, normalized, price, mrp, platform)
            for col in header
        ]
        ws.append_row(new_row, value_input_option="USER_ENTERED")
        return normalized, None
    except Exception as exc:
        return None, f"Google Sheet API failed: {type(exc).__name__}: {str(exc)[:120]}"


def load_sheet_rows(
    settings: Any,
    session: Optional[Any] = None,
    client_factory=None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Use the service account when its file exists, else the published CSV URL."""
    sheet_id = getattr(settings, "google_sheet_id", "")
    credentials_file = getattr(settings, "google_credentials_file", "")
    csv_url = getattr(settings, "google_sheet_csv_url", "")

    if sheet_id and credentials_file and os.path.exists(credentials_file):
        return fetch_sheet_rows_api(
            sheet_id,
            getattr(settings, "google_worksheet", "deals") or "deals",
            credentials_file,
            client_factory=client_factory,
        )
    if csv_url:
        return fetch_sheet_rows(csv_url, session=session)
    if sheet_id and credentials_file:
        return [], [f"Credentials file not found: {credentials_file} (set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SHEET_CSV_URL)"]
    return fetch_sheet_rows("", session=session)


def clear_processed_rows(
    settings: Any,
    product_ids: List[str],
    session: Optional[Any] = None,
    client_factory=None,
) -> int:
    """Remove posted rows from the sheet (service account) or call the webhook."""
    if not product_ids:
        return 0

    if getattr(settings, "google_sheet_id", "") and getattr(settings, "google_credentials_file", ""):
        try:
            return clear_processed_rows_api(
                settings.google_sheet_id,
                getattr(settings, "google_worksheet", "deals") or "deals",
                settings.google_credentials_file,
                product_ids,
                client_factory=client_factory,
            )
        except Exception as exc:
            log.warning("Could not clear processed rows: %s", type(exc).__name__)
            return 0

    webhook = getattr(settings, "sheet_clear_webhook_url", "")
    if webhook:
        ok = notify_sheet_clear(webhook, product_ids, getattr(settings, "sheet_clear_secret", ""), session=session)
        return len(product_ids) if ok else 0
    return 0


def notify_sheet_clear(
    webhook_url: str,
    product_ids: List[str],
    secret: str = "",
    timeout: int = 15,
    session: Optional[Any] = None,
) -> bool:
    """Optionally ask a Google Apps Script webhook to remove processed rows."""
    if not webhook_url or not product_ids:
        return False

    session = session or requests
    payload = {"action": "clear", "secret": secret, "product_ids": product_ids}
    try:
        response = session.post(webhook_url, json=payload, timeout=timeout)
        response.raise_for_status()
        return True
    except Exception as exc:
        log.warning("Sheet clear webhook failed: %s", type(exc).__name__)
        return False
