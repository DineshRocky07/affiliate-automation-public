"""One-shot daily runner (designed for Windows Task Scheduler).

Runs the paced AJIO shirt publisher once, writes a daily log, and uses a lock
file so overlapping runs can never double-post.
"""
import json
import logging
import os
import time
from datetime import datetime

from app.config import get_settings
from app.console import enable_utf8
from app.ajio_feed import fetch_feed_rows, merge_into_inventory
from app.db import Database
from app.google_sheet_source import clear_processed_rows, load_sheet_rows
from app.shirts_publisher import publish_rows, publish_shirts

LOCK_STALE_SECONDS = 6 * 60 * 60
LOCK_PATH = "data/.daily_run.lock"
SUMMARY_PATH = "logs/last_run_summary.json"


def _write_summary(summary: dict, path: str = SUMMARY_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def lock_is_active(path: str = LOCK_PATH, stale_seconds: int = LOCK_STALE_SECONDS, now=None) -> bool:
    now = time.time() if now is None else now
    try:
        with open(path, "r", encoding="utf-8") as f:
            started = float(json.load(f).get("started", 0))
    except (OSError, ValueError, TypeError):
        return False
    return (now - started) < stale_seconds


def acquire_lock(path: str = LOCK_PATH, stale_seconds: int = LOCK_STALE_SECONDS) -> bool:
    if lock_is_active(path, stale_seconds):
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"started": time.time(), "pid": os.getpid()}, f)
    return True


def release_lock(path: str = LOCK_PATH) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def main() -> int:
    enable_utf8()
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(f"logs/daily_{datetime.now():%Y%m%d}.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    log = logging.getLogger("run_daily")
    s = get_settings()

    if not acquire_lock():
        log.warning("Another daily run is still active (or crashed <6h ago). Skipping.")
        return 0

    try:
        log.info("Daily run started. dry_run=%s cap=%s interval=%ss force=%s reset=%s",
                 s.dry_run, s.max_posts_per_day, s.post_interval_seconds,
                 s.force_repost, s.reset_seen_cache)

        if s.reset_seen_cache:
            reset_db = Database(s.db_path)
            reset_db.init()
            cleared = reset_db.reset_history()
            log.warning("HARD RESET requested: cleared posts/seen/metrics -> %s", cleared)
        if s.force_repost:
            log.warning("FORCE_REPOST=true: already-posted sheet rows will be posted again")

        posted = 0
        sheet_rows = []
        sheet_errors = []
        sheet_summary = {}
        sheet_configured = bool(s.google_sheet_id or s.google_sheet_csv_url)

        if sheet_configured:
            sheet_rows, sheet_errors = load_sheet_rows(s)
            if sheet_errors:
                log.warning("Google Sheet warnings (%s): %s", len(sheet_errors), sheet_errors[:5])
            if sheet_rows:
                sheet_summary = publish_rows(
                    sheet_rows,
                    max_posts=s.max_posts_per_day,
                    settings=s,
                    force=s.force_repost,
                )
                posted += sheet_summary.get("posted", 0)
                log.info("Google Sheet inbox: %s", sheet_summary)
                if sheet_summary.get("posted_ids") and not s.dry_run and s.sheet_clear_after_post:
                    cleared = clear_processed_rows(s, sheet_summary["posted_ids"])
                    log.info("Sheet rows cleared: %s", cleared)
            else:
                log.error("Google Sheet inbox returned no rows: %s", sheet_errors[:5])
        else:
            log.warning("No Google Sheet configured (GOOGLE_SHEET_ID / GOOGLE_SHEET_CSV_URL)")

        if s.ajio_feed_url:
            rows, errors = fetch_feed_rows(s.ajio_feed_url, s.ajio_api_key)
            if rows:
                added = merge_into_inventory(rows, s.shirts_csv)
                log.info("AJIO feed: %s valid rows, %s new added", len(rows), added)
            else:
                log.warning("AJIO feed returned no rows: %s", errors[:3])

        if not s.allow_csv_inventory:
            status = "success" if sheet_configured else "error"
            message = None
            if sheet_configured and not sheet_rows and sheet_errors:
                status = "error"
                message = (
                    "Google Sheet could not be read - check the service-account secret, "
                    "sheet sharing and worksheet name"
                )
            elif sheet_summary.get("status") == "error":
                status = "error"
                message = sheet_summary.get("message") or "No sheet product could be published"
            elif sheet_configured and not sheet_rows:
                message = "Google Sheet has no deal rows"
            elif posted == 0 and sheet_summary.get("skipped"):
                message = (
                    "All sheet rows were already posted before - add new rows "
                    "or set SHEET_CLEAR_AFTER_POST=true"
                )

            summary = {
                "status": status,
                "dry_run": s.dry_run,
                "posted": posted,
                "skipped": sheet_summary.get("skipped", 0),
                "errors": (sheet_summary.get("errors") or sheet_errors)[:10],
                "note": "sheet-only mode (set ALLOW_CSV_INVENTORY=true to also use data/shirts.csv)",
            }
            if message:
                summary["message"] = message
        else:
            remaining = None if s.max_posts_per_day <= 0 else max(0, s.max_posts_per_day - posted)
            if remaining == 0:
                summary = {
                    "status": "success",
                    "dry_run": s.dry_run,
                    "posted": 0,
                    "note": "daily cap reached by Google Sheet inbox",
                }
            else:
                summary = publish_shirts(settings=s, max_posts=remaining)
        log.info("Daily run finished: %s", summary)
        _write_summary(summary)
        return 0 if summary.get("status") == "success" else 1
    except Exception as exc:
        log.exception("Daily run crashed")
        _write_summary({
            "status": "error",
            "message": f"Daily run crashed: {type(exc).__name__}: {exc}",
        })
        return 1
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
