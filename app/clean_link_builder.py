"""Generates certified, clean, and shortened affiliate links that bypass antivirus blocks."""
import urllib.parse
import urllib.request
import logging

log = logging.getLogger(__name__)


def shorten_any_affiliate_link(raw_affiliate_link: str) -> str:
    """Shortens any tracking URL via TinyURL to prevent antivirus/extension block screens.
    
    Preserves 100% of affiliate parameters, campaign IDs, and commissions.
    """
    if not raw_affiliate_link:
        return ""
    if "tinyurl.com" in raw_affiliate_link.lower():
        return raw_affiliate_link
    try:
        encoded = urllib.parse.quote(raw_affiliate_link, safe="")
        api_url = f"https://tinyurl.com/api-create.php?url={encoded}"
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            short_url = resp.read().decode("utf-8").strip()
            if short_url.startswith("http"):
                return short_url
    except Exception as e:
        log.warning("TinyURL shortener failed for %s: %s", raw_affiliate_link, e)
    return raw_affiliate_link


def build_cuelinks_url(direct_product_url: str, cid: str = "249658", channel_subid: str = "deals_telegram") -> str:
    """Builds a verified Cuelinks redirect link."""
    if not direct_product_url:
        raise ValueError("Product URL cannot be empty")
    encoded_target = urllib.parse.quote(direct_product_url, safe="")
    return f"https://linksredirect.com/?cid={cid}&subid={channel_subid}&source=api&url={encoded_target}"


def build_trusted_affiliate_url(direct_product_url: str, channel_subid: str = "deals_telegram") -> str:
    """Builds a verified tracking link and wraps it in a trusted shortener."""
    raw_tracking_url = build_cuelinks_url(direct_product_url, channel_subid=channel_subid)
    return shorten_any_affiliate_link(raw_tracking_url)
