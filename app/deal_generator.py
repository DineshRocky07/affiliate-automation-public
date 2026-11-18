"""Safe template deal text generation with fallback for AI."""
import html
from app.models import Product, AffiliateLink


def make_safe_caption(product: Product, link: AffiliateLink, custom_text: str = "") -> str:
    """Format final deal message for Telegram HTML."""
    title_escaped = html.escape(product.title)
    
    price_line = ""
    if product.price_verified and product.price > 0:
        price_line = f"\n💰 <b>Price:</b> ₹{product.price:,.0f}"
        if product.mrp and product.mrp > product.price:
            price_line += f" <s>₹{product.mrp:,.0f}</s> ({product.discount_pct}% OFF)"
    else:
        price_line = "\n🔍 <i>Check the latest deal price directly on the store!</i>"

    desc = html.escape(custom_text) if custom_text else f"Top trending find in <b>{html.escape(product.category)}</b>."

    caption = (
        f"🔥 <b>{title_escaped}</b>\n"
        f"{price_line}\n\n"
        f"📝 {desc}\n\n"
        f"👉 <a href=\"{link.tracking_url}\"><b>Get this deal here</b></a>\n\n"
        f"<i>ℹ️ Affiliate link — I may earn a small commission at no extra cost to you.</i>"
    )
    return caption
