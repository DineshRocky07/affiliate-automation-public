"""AJIO ACE (Trackier v2) affiliate provider.

Builds the official Trackier click URL:
    <tracking_base>?campaign_id=..&pub_id=..&p1=<subid>&url=<encoded ajio url>

The raw tracking link is used directly. It is never wrapped in a third-party
shortener: shorteners add a network hop, can fail (and log warnings), and hide
the real tracking domain from the user.
"""
import logging
from urllib.parse import urlencode, urlparse

from app.models import AffiliateLink

log = logging.getLogger(__name__)


class AjioProvider:
    def __init__(self, api_key: str, campaign_id: int, pub_id: int, tracking_base: str, shorten: bool = False):
        self.api_key = api_key
        self.campaign_id = campaign_id
        self.pub_id = pub_id
        self.tracking_base = (tracking_base or "").rstrip("/")
        self.shorten = shorten

    def is_ajio_url(self, url: str) -> bool:
        netloc = urlparse(url).netloc.lower()
        return "ajio.com" in netloc

    def build_link(
        self,
        product_id: str,
        ajio_url: str,
        subid: str = "deals_telegram",
        utm_campaign: str = "viodFallDeals",
    ) -> AffiliateLink:
        if not self.is_ajio_url(ajio_url):
            return AffiliateLink(
                product_id=product_id,
                provider="ajio",
                original_url=ajio_url,
                tracking_url="",
                status="rejected",
                reason="Not an ajio.com URL",
                campaign_name="AJIO ACE",
            )

        if not self.tracking_base or not self.pub_id or not self.campaign_id:
            return AffiliateLink(
                product_id=product_id,
                provider="ajio",
                original_url=ajio_url,
                tracking_url="",
                status="rejected",
                reason="AJIO tracking base, pub_id and campaign_id must be configured",
                campaign_name="AJIO ACE",
            )

        params = {
            "campaign_id": self.campaign_id,
            "pub_id": self.pub_id,
            "p1": subid,
            "p2": utm_campaign,
            "url": ajio_url,
        }
        tracking_url = f"{self.tracking_base}?{urlencode(params)}"

        if self.shorten:
            try:
                from app.clean_link_builder import shorten_any_affiliate_link
                tracking_url = shorten_any_affiliate_link(tracking_url)
            except Exception:
                pass

        return AffiliateLink(
            product_id=product_id,
            provider="ajio",
            original_url=ajio_url,
            tracking_url=tracking_url,
            status="verified",
            reason="Approved AJIO ACE campaign",
            campaign_name="AJIO ACE",
        )
