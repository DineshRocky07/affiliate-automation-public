"""Single entry point for turning a product URL into an affiliate link.

Rules:
- Flipkart is always rejected.
- AJIO URLs go through AJIO ACE (Trackier click domain + pub_id + campaign_id).
- Everything else goes through the Cuelinks static redirect (requires CUELINKS_CID).
"""
import logging
from urllib.parse import urlparse

from app.ajio_provider import AjioProvider
from app.clean_link_builder import build_cuelinks_url
from app.config import Settings
from app.models import AffiliateLink

log = logging.getLogger(__name__)

BLOCKED_DOMAINS = ("flipkart.com",)


def _rejected(product_id: str, product_url: str, reason: str, campaign_name: str = None) -> AffiliateLink:
    return AffiliateLink(
        product_id=product_id,
        provider="rejected",
        original_url=product_url,
        tracking_url="",
        status="rejected",
        reason=reason,
        campaign_name=campaign_name,
    )


def resolve_affiliate_link(
    product_id: str,
    product_url: str,
    settings: Settings,
    subid: str = "affiliate_bot",
) -> AffiliateLink:
    """Resolve a product URL to a tracking link, or a rejected AffiliateLink."""
    url = (product_url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return _rejected(product_id, url, "Product URL must start with http:// or https://")

    netloc = urlparse(url).netloc.lower()
    if any(blocked in netloc for blocked in BLOCKED_DOMAINS):
        return _rejected(product_id, url, "Flipkart is disabled by policy", campaign_name="flipkart")

    if "ajio.com" in netloc:
        provider = AjioProvider(
            api_key=settings.ajio_api_key,
            campaign_id=settings.ajio_campaign_id,
            pub_id=settings.ajio_pub_id,
            tracking_base=settings.ajio_tracking_base,
            shorten=getattr(settings, "shorten_affiliate_links", False),
        )
        return provider.build_link(product_id, url, subid=subid)

    if not settings.cuelinks_cid:
        return _rejected(product_id, url, "CUELINKS_CID is not configured for non-AJIO URLs")

    try:
        tracking_url = build_cuelinks_url(url, settings.cuelinks_cid, channel_subid=subid)
    except ValueError as exc:
        return _rejected(product_id, url, str(exc))

    return AffiliateLink(
        product_id=product_id,
        provider="cuelinks",
        original_url=url,
        tracking_url=tracking_url,
        status="verified",
        reason="Cuelinks redirect built",
        campaign_name="Cuelinks",
    )
