"""Windows background task scheduler to auto-post daily without touching anything."""
import time
import schedule
from datetime import datetime
from app.config import get_settings
from app.run_daily import main as run_daily_job


def job():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ Executing Daily Google Sheet Publisher...")
    res = run_daily_job()
    print("Result code:", res)


def run_scheduler():
    from app.console import enable_utf8
    enable_utf8()

    print("🚀 Auto Affiliate Bot Daemon started.")
    print("Running initial pass right now...")
    job()

    # Schedule daily at 09:00 AM and 06:00 PM
    schedule.every().day.at("09:00").do(job)
    schedule.every().day.at("18:00").do(job)

    print("📅 Scheduled to auto-run every day at 09:00 AM & 06:00 PM.")
    print("Bot is listening in background... (Press Ctrl+C to stop)")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run_scheduler()
