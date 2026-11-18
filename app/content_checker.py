"""Deterministic guardrails for generated post captions."""
import re
from typing import List, Optional
from app.models import Product

BANNED_WORDS = [
    r"\bloot\b",
    r"\bhack\b",
    r"\bguarantee\b",
    r"\bsteal\b",
    r"\blowest price\b",
    r"\bhurry\b",
    r"\bdon't miss\b"
]


class ContentRejected(Exception):
    """Raised when a caption fails deterministic guardrails."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def check_caption_safety(headline: str, caption: str, product: Product) -> Optional[List[str]]:
    """Return errors if content violates safety, ethical, or truthfulness guidelines."""
    errors = []
    full_text = f"{headline} {caption}".lower()

    # Rule 1: Banned hype phrases
    for pat in BANNED_WORDS:
        if re.search(pat, full_text):
            errors.append(f"Contains banned hype term matching: {pat}")

    # Rule 2: Disclosure requirement
    if "affiliate link" not in full_text and "commission" not in full_text:
        errors.append("Missing mandatory affiliate disclosure")

    # Rule 3: Emoji spam (> 8 emojis)
    emoji_count = len(re.findall(r"[\U00010000-\U0010ffff]", full_text))
    if emoji_count > 8:
        errors.append(f"Too many emojis ({emoji_count} > 8)")

    return errors if errors else None


def enforce_caption_safety(headline: str, caption: str, product: Product) -> None:
    """Raise ContentRejected if the caption breaks a hard rule. Call before posting."""
    errors = check_caption_safety(headline, caption, product)
    if errors:
        raise ContentRejected(errors)
