"""Settings loader for environment variables."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


DEFAULT_SHEET_ID = "YOUR_GOOGLE_SHEET_ID"


def _clean_sheet_id(val: str) -> str:
    cleaned = (val or "").strip().strip('"\'')
    if not cleaned:
        return DEFAULT_SHEET_ID
    if len(cleaned) == 43 and (cleaned in DEFAULT_SHEET_ID or DEFAULT_SHEET_ID.startswith(cleaned) or DEFAULT_SHEET_ID.endswith(cleaned)):
        return DEFAULT_SHEET_ID
    return cleaned


def _bool(val: str, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    dry_run: bool = True
    use_ai: bool = True

    # Cuelinks
    cuelinks_api_key: str = ""
    cuelinks_api_url: str = "https://developers.cuelinks.com/pub_api/v3"
    cuelinks_auth_scheme: str = "Token"
    cuelinks_cid: str = ""

    # AJIO
    ajio_api_key: str = ""
    ajio_campaign_id: int = 1
    ajio_pub_id: int = 0
    ajio_tracking_base: str = ""
    ajio_feed_url: str = ""
    shorten_affiliate_links: bool = False

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = "@YourDealsChannel"

    # Google Sheet inbox
    google_sheet_id: str = ""
    google_worksheet: str = "deals"
    google_credentials_file: str = ""
    google_sheet_csv_url: str = ""
    sheet_clear_after_post: bool = False
    sheet_clear_webhook_url: str = ""
    sheet_clear_secret: str = ""

    # Database
    db_path: str = "data/affiliate.db"
    deals_csv: str = "data/sample_deals.csv"
    shirts_csv: str = "data/shirts.csv"
    max_posts_per_run: int = 3
    max_posts_per_day: int = 100
    post_interval_seconds: int = 600
    monthly_target_inr: int = 2000
    allow_csv_inventory: bool = False
    force_repost: bool = False
    reset_seen_cache: bool = False


def get_settings() -> Settings:
    e = os.getenv
    return Settings(
        dry_run=_bool(e("DRY_RUN", "true"), True),
        use_ai=_bool(e("USE_AI", "true"), True),
        cuelinks_api_key=e("CUELINKS_API_KEY", ""),
        cuelinks_api_url=e("CUELINKS_API_URL", "https://developers.cuelinks.com/pub_api/v3"),
        cuelinks_auth_scheme=e("CUELINKS_AUTH_SCHEME", "Token"),
        cuelinks_cid=e("CUELINKS_CID", ""),
        ajio_api_key=e("AJIO_API_KEY", ""),
        ajio_campaign_id=int(e("AJIO_CAMPAIGN_ID", "1")),
        ajio_pub_id=int(e("AJIO_PUB_ID", "0")),
        ajio_tracking_base=e("AJIO_TRACKING_BASE", ""),
        ajio_feed_url=e("AJIO_FEED_URL", ""),
        shorten_affiliate_links=_bool(e("SHORTEN_AFFILIATE_LINKS", "true"), True),
        gemini_api_key=e("GEMINI_API_KEY", ""),
        gemini_model=e("GEMINI_MODEL", "gemini-2.5-flash"),
        telegram_bot_token=e("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=e("TELEGRAM_CHAT_ID", "@YourDealsChannel"),
        google_sheet_id=_clean_sheet_id(e("GOOGLE_SHEET_ID", DEFAULT_SHEET_ID)),
        google_worksheet=e("GOOGLE_WORKSHEET", "deals"),
        google_credentials_file=e("GOOGLE_CREDENTIALS_FILE", ""),
        google_sheet_csv_url=e("GOOGLE_SHEET_CSV_URL", ""),
        sheet_clear_after_post=_bool(e("SHEET_CLEAR_AFTER_POST", "false"), False),
        sheet_clear_webhook_url=e("SHEET_CLEAR_WEBHOOK_URL", ""),
        sheet_clear_secret=e("SHEET_CLEAR_SECRET", ""),
        db_path=e("DB_PATH", "data/affiliate.db"),
        deals_csv=e("DEALS_CSV", "data/sample_deals.csv"),
        shirts_csv=e("SHIRTS_CSV", "data/shirts.csv"),
        max_posts_per_run=int(e("MAX_POSTS_PER_RUN", "3")),
        max_posts_per_day=0 if _bool(e("POST_ALL", "false"), False) else int(e("MAX_POSTS_PER_DAY", "100")),
        post_interval_seconds=int(e("POST_INTERVAL_SECONDS", "600")),
        monthly_target_inr=int(e("MONTHLY_TARGET_INR", "2000")),
        allow_csv_inventory=_bool(e("ALLOW_CSV_INVENTORY", "false"), False),
        force_repost=_bool(e("FORCE_REPOST", "false"), False),
        reset_seen_cache=_bool(e("RESET_SEEN_CACHE", "false"), False),
    )
