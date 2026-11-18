"""Auto-fetcher for live offers directly from Cuelinks & AJIO APIs.

ZERO scraping. 100% legal, official REST API.
Automatically discovers active AJIO deals with tracking links already built-in!
"""
import logging
from typing import List, Dict, Any
import requests

log = logging.getLogger(__name__)


class AutoDealFetcher:
    def __init__(self, cuelinks_api_key: str, cuelinks_base_url: str = "https://developers.cuelinks.com/pub_api/v3"):
        self.cuelinks_api_key = cuelinks_api_key
        self.offers_url = f"{cuelinks_base_url.rstrip('/')}/offers"

    def fetch_live_deals(self, merchant_filter: str = "ajio", limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch real-time active promotional deals from Cuelinks Offers API."""
        headers = {
            "Authorization": f"Token {self.cuelinks_api_key}",
            "Content-Type": "application/json"
        }

        try:
            r = requests.get(self.offers_url, headers=headers, timeout=20)
            if r.status_code != 200:
                log.error("Failed to fetch offers HTTP %s: %s", r.status_code, r.text[:200])
                return []

            body = r.json()
            all_offers = body.get("data", [])

            # Filter for active deals from the desired merchant (AJIO)
            matched = []
            for item in all_offers:
                camp = (item.get("campaign_name") or "").lower()
                title = (item.get("title") or "").lower()
                desc = (item.get("description") or "").lower()

                # Strictly ensure Flipkart is NEVER selected
                if "flipkart" in camp or "flipkart" in title:
                    continue

                if merchant_filter.lower() in camp or merchant_filter.lower() in title or merchant_filter.lower() in desc:
                    tracking = item.get("tracking_url")
                    if tracking:
                        matched.append({
                            "id": str(item.get("id")),
                            "title": item.get("title", "").strip(),
                            "description": item.get("description", "").strip(),
                            "coupon_code": item.get("coupon_code"),
                            "campaign_name": item.get("campaign_name"),
                            "tracking_url": tracking,
                            "source": "cuelinks_offers"
                        })

                if len(matched) >= limit:
                    break

            log.info("Discovered %d active live deals for merchant '%s'", len(matched), merchant_filter)
            return matched

        except requests.RequestException as e:
            log.error("Network error fetching live offers: %s", e)
            return []
