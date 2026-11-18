"""Domain models for products, deals, and affiliate links."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Product:
    product_id: str
    title: str
    url: str
    price: float
    mrp: float
    category: str = "General"
    image_url: str = ""
    source: str = "amazon"
    price_verified: bool = False
    rating: Optional[float] = None
    rating_count: Optional[int] = None

    @property
    def discount_pct(self) -> int:
        if self.mrp and self.mrp > self.price > 0:
            return int(round((1.0 - (self.price / self.mrp)) * 100))
        return 0


@dataclass
class AffiliateLink:
    product_id: str
    provider: str         # "ajio", "cuelinks", "direct"
    original_url: str
    tracking_url: str
    status: str           # "verified", "rejected"
    reason: str
    campaign_name: Optional[str] = None

    @property
    def is_eligible(self) -> bool:
        return self.status == "verified" and bool(self.tracking_url)
