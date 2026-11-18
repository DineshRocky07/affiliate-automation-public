"""Synchronizes real-time conversion and commission data from Cuelinks /transactions API."""
import logging
from typing import Dict, Any, List
import requests
from app.config import Settings
from app.db import Database

log = logging.getLogger(__name__)


def sync_cuelinks_transactions(settings: Settings) -> Dict[str, Any]:
    """Pulls confirmed orders and commissions directly from Cuelinks v3 REST API.
    
    Matches subid / transaction parameters and updates SQLite metrics.
    """
    if not settings.cuelinks_api_key:
        return {"status": "error", "message": "CUELINKS_API_KEY is not configured"}

    url = f"{settings.cuelinks_api_url.rstrip('/')}/transactions"
    headers = {
        "Authorization": f"{settings.cuelinks_auth_scheme} {settings.cuelinks_api_key}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            log.error("Failed to fetch Cuelinks transactions HTTP %s: %s", r.status_code, r.text[:200])
            return {"status": "error", "code": r.status_code, "message": r.text[:100]}

        body = r.json()
        transactions: List[Dict[str, Any]] = body.get("data", [])
        log.info("Pulled %d transaction records from Cuelinks API", len(transactions))

        db = Database(settings.db_path)
        db.init()
        updated = 0
        total_commission = 0.0

        for t in transactions:
            # Transaction structure typically contains: id, subid, commission, status, sale_amount
            tx_id = t.get("id")
            subid = str(t.get("subid") or "").strip()
            commission = float(t.get("commission") or 0.0)
            status = str(t.get("status") or "pending").lower()
            total_commission += commission

            # Match subid to post_id if formatted as integer or 'post_<id>'
            post_id = None
            if subid.isdigit():
                post_id = int(subid)
            elif subid.startswith("post_"):
                try:
                    post_id = int(subid.split("_")[1])
                except (IndexError, ValueError):
                    pass

            if post_id and db.post_exists(post_id) and commission > 0:
                db.record_commission(post_id, commission)
                updated += 1

        return {
            "status": "success",
            "total_transactions": len(transactions),
            "synced_records": updated,
            "total_commission_inr": total_commission
        }

    except requests.RequestException as e:
        log.error("Network error while syncing Cuelinks transactions: %s", e)
        return {"status": "error", "message": str(e)}
