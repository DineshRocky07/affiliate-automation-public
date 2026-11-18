"""CLI command entry point for testing and running the pipeline."""
import argparse
from app.config import get_settings
from app.db import Database
from app.ajio_feed import fetch_feed_rows, merge_into_inventory
from app.google_sheet_source import clear_processed_rows, load_sheet_rows
from app.models import Product
from app.deal_generator import make_safe_caption
from app.link_service import resolve_affiliate_link
from app.telegram_publisher import TelegramPublisher


def cmd_init_db(s):
    db = Database(s.db_path)
    db.init()
    print(f"SQLite Database initialized at: {s.db_path}")


def cmd_check_link(s, url: str):
    print(f"\nTesting URL: {url}")
    link = resolve_affiliate_link("TEST-LINK", url, s)

    print(f"Provider : {link.provider}")
    print(f"Status   : {link.status}")
    print(f"Eligible : {link.is_eligible}")
    print(f"Campaign : {link.campaign_name}")
    print(f"Reason   : {link.reason}")
    print(f"Tracking : {link.tracking_url}")


def cmd_demo_post(s, url: str, title: str):
    print(f"\nCreating sample deal post for: {title}")
    link = resolve_affiliate_link("DEMO-1", url, s)

    if not link.is_eligible:
        print(f"Cannot post: {link.reason}")
        return

    prod = Product(
        product_id="DEMO-1",
        title=title,
        url=url,
        price=0,
        mrp=0,
        category="Fashion",
        price_verified=False
    )
    caption = make_safe_caption(prod, link)
    publisher = TelegramPublisher(s.telegram_bot_token, s.telegram_chat_id, dry_run=s.dry_run)
    res = publisher.send_deal(caption, tracking_url=link.tracking_url)
    print("Result:", res)


from app.auto_pipeline import run_autonomous_deal_publisher
from app.dress_publisher import publish_individual_dresses
from app.real_product_publisher import publish_real_product, publish_batch_products
from app.shirts_publisher import load_shirts, publish_rows, publish_shirts


def cmd_publish_shirts(limit, csv_path):
    print(f"\nPosting AJIO shirts (limit={limit or 'daily cap'}, DRY_RUN aware)...")
    res = publish_shirts(csv_path=csv_path, max_posts=limit)
    print("Result:", res)


def cmd_validate_inventory(s, csv_path):
    path = csv_path or s.shirts_csv
    rows, errors = load_shirts(path)
    print(f"\nInventory: {path}")
    print(f"Valid rows: {len(rows)}")
    if errors:
        print(f"Problems: {len(errors)}")
        for err in errors:
            print(f" - {err}")
    else:
        print("No problems found.")


def cmd_fetch_ajio_feed(s, limit, csv_path):
    if not s.ajio_feed_url:
        print("AJIO_FEED_URL is not set in .env. Paste the feed URL from your AJIO ACE dashboard.")
        return
    rows, errors = fetch_feed_rows(s.ajio_feed_url, s.ajio_api_key, limit=limit)
    print(f"Fetched valid AJIO rows: {len(rows)}")
    for err in errors[:10]:
        print(f" - {err}")
    if len(errors) > 10:
        print(f" ... and {len(errors) - 10} more")
    if rows:
        path = csv_path or s.shirts_csv
        added = merge_into_inventory(rows, path)
        print(f"Added {added} new rows to {path}")
    else:
        print("No rows added; inventory left unchanged.")



def cmd_run_sheet(s, limit, force: bool = False):
    print("\nReading Google Sheet inbox...")
    rows, errors = load_sheet_rows(s)
    print(f"Valid rows: {len(rows)}")
    for err in errors[:10]:
        print(f" - {err}")
    if len(errors) > 10:
        print(f" ... and {len(errors) - 10} more")
    if not rows:
        print("No valid rows. Check the sheet, service-account sharing, or GOOGLE_SHEET_CSV_URL.")
        return

    result = publish_rows(rows, max_posts=limit, settings=s, force=force)
    print("Result:", result)

    if result.get("posted_ids") and not s.dry_run and s.sheet_clear_after_post:
        cleared = clear_processed_rows(s, result["posted_ids"])
        print(f"Sheet rows cleared: {cleared}")
    elif result.get("posted_ids") and s.dry_run:
        print("Dry run: sheet rows are NOT deleted.")
    elif result.get("posted_ids"):
        print("SHEET_CLEAR_AFTER_POST=false: sheet rows are kept (dedupe still prevents repeats).")


def cmd_report(s, limit: int = 10):
    db = Database(s.db_path)
    db.init()
    data = db.report(limit=limit)
    print(f"\nDatabase: {s.db_path}")
    print(f"Live posts         : {data['posts']}")
    print(f"Seen (all)         : {data['seen']}")
    print(f"Seen (dry-run only): {data['dry_run_seen']}")
    m = data["metrics"]
    print(f"Metrics rows       : {m['rows']} (clicks {m['clicks']}, orders {m['orders']}, commission {m['commission']})")
    target = max(int(getattr(s, "monthly_target_inr", 0) or 0), 0)
    earned = data["commission_month"]
    pct = (earned / target * 100) if target else 0.0
    print(f"Commission (month) : Rs {earned:,.0f} / Rs {target:,.0f} ({pct:.1f}%)")
    print("Note: clicks/commission are only real when synced from Vibconnect.")
    if data["recent"]:
        print("\nRecent posts:")
        for r in data["recent"]:
            print(f"  #{r['id']} {r['product_id']} [{r['provider']}] {r['posted_at']}")
            print(f"     {r['affiliate_url'][:90]}")
    else:
        print("\nNo posts yet.")
    if data["top"]:
        print("\nMost posted products:")
        for r in data["top"]:
            print(f"  {r['product_id']} x{r['posts']}")


def cmd_commission(s, post_id: int, amount: float, confirmed: bool):
    if not confirmed:
        print("Refusing: only confirmed commission is recorded. Re-run with --confirmed after checking Vibconnect.")
        return
    if amount < 0:
        print("Amount must be 0 or more.")
        return
    db = Database(s.db_path)
    db.init()
    if not db.post_exists(post_id):
        print(f"Post #{post_id} not found. Run `python -m app.main report` to list post ids.")
        return
    db.record_commission(post_id, amount)
    earned = db.commission_this_month()
    target = max(int(getattr(s, "monthly_target_inr", 0) or 0), 0)
    pct = (earned / target * 100) if target else 0.0
    print(f"Saved Rs {amount:,.0f} confirmed commission for post #{post_id}.")
    print(f"Month total: Rs {earned:,.0f} / Rs {target:,.0f} ({pct:.1f}%)")


def cmd_post_real_product(url: str):
    print(f"\n🛍️ Scraping Real Amazon Product Photo, Live Price & Generating Link...")
    res = publish_real_product(url)
    print("Result:", res)


def cmd_publish_dresses(limit: int = 2):
    print(f"\n👗 Publishing Individual Dress Products with Photo & Buy Buttons...")
    res = publish_individual_dresses(max_posts=limit)
    print("\n🏁 Dress Publishing Result:")
    print(res)


def cmd_auto_publish(s, limit: int = 2):
    print(f"\n🤖 Running Autonomous Deal Pipeline (DRY_RUN={s.dry_run})...")
    res = run_autonomous_deal_publisher(s, max_posts=limit)
    print("\n🏁 Autonomous Execution Complete:")
    print(res)


def main():
    import logging
    from app.console import enable_utf8
    enable_utf8()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Affiliate Bot Course CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db")

    p_check = sub.add_parser("check-link")
    p_check.add_argument("url", help="Product URL to convert and verify")

    sub.add_parser("sync-conversions")

    p_demo = sub.add_parser("demo-post")
    p_demo.add_argument("url", help="Product URL")
    p_demo.add_argument("--title", default="AJIO Premium Cotton Casual Shirt", help="Product Title")

    p_auto = sub.add_parser("auto-publish")
    p_auto.add_argument("--limit", type=int, default=2, help="Number of deals to post")

    p_dresses = sub.add_parser("publish-dresses")
    p_dresses.add_argument("--limit", type=int, default=2, help="Number of individual dresses to post")

    p_real = sub.add_parser("post-real")
    p_real.add_argument("url", help="Amazon product URL or ASIN")

    p_shirts = sub.add_parser("publish-shirts")
    p_shirts.add_argument("--limit", type=int, default=None, help="Max shirts to post this run")
    p_shirts.add_argument("--csv", default=None, help="Path to shirt inventory CSV")

    p_validate = sub.add_parser("validate-inventory")
    p_validate.add_argument("--csv", default=None, help="Path to shirt inventory CSV")

    p_feed = sub.add_parser("fetch-ajio-feed")
    p_feed.add_argument("--limit", type=int, default=0, help="Max feed items to request (0 = all)")
    p_feed.add_argument("--csv", default=None, help="Inventory CSV to merge into")

    p_sheet = sub.add_parser("run-sheet")
    p_sheet.add_argument("--limit", type=int, default=None, help="Max posts this run")
    p_sheet.add_argument("--force", action="store_true", help="Re-post rows already seen/posted")

    p_report = sub.add_parser("report")
    p_report.add_argument("--limit", type=int, default=10, help="Rows to show")

    p_comm = sub.add_parser("commission")
    p_comm.add_argument("--post", type=int, required=True, help="Post id from report")
    p_comm.add_argument("--amount", type=float, required=True, help="Confirmed commission in INR")
    p_comm.add_argument("--confirmed", action="store_true", help="Confirm this came from Vibconnect")

    args = parser.parse_args()
    s = get_settings()

    if args.cmd == "init-db":
        cmd_init_db(s)
    elif args.cmd == "sync-conversions":
        from app.cuelinks_sync import sync_cuelinks_transactions
        res = sync_cuelinks_transactions(s)
        print("Conversion Sync Result:", res)
    elif args.cmd == "check-link":
        cmd_check_link(s, args.url)
    elif args.cmd == "demo-post":
        cmd_demo_post(s, args.url, args.title)
    elif args.cmd == "auto-publish":
        cmd_auto_publish(s, args.limit)
    elif args.cmd == "publish-dresses":
        cmd_publish_dresses(args.limit)
    elif args.cmd == "post-real":
        cmd_post_real_product(args.url)
    elif args.cmd == "publish-shirts":
        cmd_publish_shirts(args.limit, args.csv)
    elif args.cmd == "validate-inventory":
        cmd_validate_inventory(s, args.csv)
    elif args.cmd == "fetch-ajio-feed":
        cmd_fetch_ajio_feed(s, args.limit, args.csv)
    elif args.cmd == "run-sheet":
        cmd_run_sheet(s, args.limit, force=args.force)
    elif args.cmd == "report":
        cmd_report(s, args.limit)
    elif args.cmd == "commission":
        cmd_commission(s, args.post, args.amount, args.confirmed)


if __name__ == "__main__":
    main()
