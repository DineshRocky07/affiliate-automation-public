"""Auto-discovers low-price deals (Men under 299, Women under 299) from Amazon."""
import re
import urllib.request
from typing import List

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def discover_category_asins(query: str, limit: int = 50) -> List[str]:
    """Finds active low price ASINs for any search term (e.g. 'mens t shirts under 299')."""
    encoded_query = query.strip().replace(" ", "+")
    url = f"https://www.amazon.in/s?k={encoded_query}&s=price-asc-rank"
    req = urllib.request.Request(url, headers=HEADERS)

    discovered = []
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            # Extract unique Amazon ASIN IDs
            raw_asins = re.findall(r'data-asin="([A-Z0-9]{10})"', html)
            seen = set()
            for asin in raw_asins:
                if asin and asin not in seen:
                    seen.add(asin)
                    discovered.append(asin)
                if len(discovered) >= limit:
                    break
    except Exception as e:
        print(f"Discovery error for '{query}': {e}")

    return discovered
