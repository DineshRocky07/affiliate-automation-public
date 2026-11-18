"""Cuelinks v3 REST API client with Flipkart blocker and strict eligibility check."""
import logging
from urllib.parse import urlparse
import requests
from app.models import AffiliateLink

log = logging.getLogger(__name__)

BLOCKED_CAMPAIGNS = {"flipkart"}


class CuelinksProvider:
    def __init__(self, api_key: str, api_url: str = "https://developers.cuelinks.com/pub_api/v3", auth_scheme: str = "Token"):
        self.api_key = api_key
        self.convert_url = f"{api_url.rstrip('/')}/links/convert"
        self.auth_scheme = auth_scheme

    def convert(self, product_id: str, product_url: str, subid: str = "affiliate_bot") -> AffiliateLink:
        headers = {
            "Authorization": f"{self.auth_scheme} {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "url": product_url,
            "shorten": True,
            "subid": subid
        }

        try:
            r = requests.post(self.convert_url, headers=headers, json=payload, timeout=20)
            if r.status_code != 200:
                return AffiliateLink(
                    product_id=product_id,
                    provider="cuelinks",
                    original_url=product_url,
                    tracking_url="",
                    status="rejected",
                    reason=f"API error HTTP {r.status_code}: {r.text[:100]}"
                )

            body = r.json()
            data = body.get("data", {})
            campaign_info = data.get("campaign") or {}
            campaign_name = campaign_info.get("name") if isinstance(campaign_info, dict) else None

            # 1. Hard Rule: Flipkart is blocked
            if campaign_name and campaign_name.lower() in BLOCKED_CAMPAIGNS:
                return AffiliateLink(
                    product_id=product_id,
                    provider="cuelinks",
                    original_url=product_url,
                    tracking_url="",
                    status="rejected",
                    reason=f"Campaign {campaign_name} is disabled by policy",
                    campaign_name=campaign_name
                )

            # 2. Hard Rule: affiliated must be True
            if data.get("affiliated") is not True:
                return AffiliateLink(
                    product_id=product_id,
                    provider="cuelinks",
                    original_url=product_url,
                    tracking_url="",
                    status="rejected",
                    reason="Campaign not currently approved (affiliated=False)",
                    campaign_name=campaign_name
                )

            tracking_url = data.get("short_url") or data.get("tracking_url")
            return AffiliateLink(
                product_id=product_id,
                provider="cuelinks",
                original_url=product_url,
                tracking_url=tracking_url,
                status="verified",
                reason="Eligible and verified",
                campaign_name=campaign_name
            )

        except requests.RequestException as e:
            return AffiliateLink(
                product_id=product_id,
                provider="cuelinks",
                original_url=product_url,
                tracking_url="",
                status="rejected",
                reason=f"Network error: {type(e).__name__}"
            )
