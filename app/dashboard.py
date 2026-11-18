"""Streamlit frontend dashboard for the AJIO Affiliate Automation Bot.

Run locally with:
    streamlit run app/dashboard.py
"""
from dataclasses import replace
import glob
import os
import sys

# Ensure project root is importable when launched as `streamlit run app/dashboard.py`
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st

from app.config import Settings, get_settings
from app.db import Database
from app.google_sheet_source import append_sheet_row, load_sheet_rows
from app.link_service import resolve_affiliate_link
from app.models import Product
from app.shirts_publisher import build_shirt_caption, publish_rows


def _read_latest_log(log_dir: str = "logs", max_lines: int = 80) -> tuple[str, str]:
    files = sorted(glob.glob(os.path.join(log_dir, "daily_*.log")))
    if not files:
        return "", "No daily log files found yet."
    latest = files[-1]
    with open(latest, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()[-max_lines:]
    return os.path.basename(latest), "".join(lines)


def _format_sheet_table(rows: list[dict], db=None) -> list[dict]:
    table = []
    for r in rows:
        price = float(r.get("price") or 0)
        mrp = float(r.get("mrp") or 0)
        disc = int(round((1.0 - (price / mrp)) * 100)) if r.get("price_verified") and mrp > 0 else 0
        status = "🟢 Ready"
        if db:
            if db.is_product_posted(r["product_id"]):
                status = "✓ Posted"
            elif getattr(db, "is_seen", None) and db.is_seen(r["product_id"], include_dry_run=False):
                status = "👁️ Seen"
        table.append({
            "Status": status,
            "Product ID": r["product_id"],
            "Title": r["title"],
            "Deal Price": f"Rs {price:,.0f}" if r.get("price_verified") else "Check Store",
            "MRP": f"Rs {mrp:,.0f}" if r.get("price_verified") else "-",
            "Discount": f"{disc}%" if disc > 0 else "-",
            "Has Image": "Yes" if r.get("image_url") else "No",
        })
    return table


def _render_header(s: Settings, report: dict) -> None:
    st.set_page_config(page_title="AJIO Affiliate Bot", page_icon="🛍️", layout="wide")
    st.title("🛍️ AJIO Affiliate Automation Dashboard")

    mode_badge = "🟢 LIVE MODE (DRY_RUN=false)" if not s.dry_run else "🟡 DRY-RUN MODE (Safe Preview)"
    st.caption(
        f"{mode_badge}  •  Channel: `{s.telegram_chat_id}`  •  "
        f"AJIO ACE Pub ID: `{s.ajio_pub_id}`  •  Campaign ID: `{s.ajio_campaign_id}`"
    )

    target = max(int(s.monthly_target_inr or 2000), 1)
    earned = float(report.get("commission_month") or 0.0)
    progress = min(1.0, earned / target)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Live Posts Sent", report.get("posts", 0))
    c2.metric("Seen Products (SQLite)", report.get("seen", 0))
    c3.metric("Month Commission", f"Rs {earned:,.0f}", f"Target Rs {target:,.0f}")
    c4.metric("Daily Cap", s.max_posts_per_day)

    st.progress(progress, text=f"Monthly Target Progress: Rs {earned:,.0f} / Rs {target:,.0f} ({progress * 100:.1f}%)")


def _render_sheet_tab(s: Settings, db=None) -> None:
    st.subheader("📲 Google Sheet Inbox & Publisher")

    col_refresh, col_clear, col_info = st.columns([1, 1.3, 3])
    with col_refresh:
        if st.button("🔄 Refresh Sheet", use_container_width=True):
            st.rerun()
    with col_clear:
        if db and st.button("🧹 Clear Test Seen Cache", use_container_width=True, help="Clears dry-run seen records so you can test products again"):
            with db._connection() as conn:
                conn.execute("DELETE FROM seen_products WHERE dry_run = 1")
            st.success("Test seen cache cleared!")
            st.rerun()
    with col_info:
        clear_msg = "kept intact (dedupe in SQLite)" if not s.sheet_clear_after_post else "cleared after live post"
        st.info(f"Sheet ID: `{s.google_sheet_id or 'Not configured'}`  |  Tab: `{s.google_worksheet}`  |  Posted rows are **{clear_msg}**.")

    rows, errors = load_sheet_rows(s)
    if errors:
        with st.expander(f"⚠️ Sheet Warnings ({len(errors)})"):
            for err in errors:
                st.write(f"- {err}")

    if rows:
        st.dataframe(_format_sheet_table(rows, db=db), width="stretch", hide_index=True)

        st.markdown("### 🚀 Run Publisher")
        col_choice, col_force = st.columns([2, 1])
        with col_choice:
            product_options = ["Auto: Next unposted product in line"] + [
                f"Row {i+1} [{r['product_id']}]: {r['title']} (₹{r.get('price', 0):,.0f})"
                for i, r in enumerate(rows)
            ]
            selected_target = st.selectbox("🎯 Target product for testing / publishing:", options=product_options)
        with col_force:
            force = st.checkbox("🧪 Force re-post seen products", value=False, help="Check this to test posting items that are already marked as posted in SQLite.")

        if selected_target.startswith("Row "):
            row_idx = int(selected_target.split()[1]) - 1
            target_rows = [rows[row_idx]]
            effective_force = True
        else:
            target_rows = rows
            effective_force = force

        c_left, c_right = st.columns([1, 2])
        with c_left:
            max_posts = st.number_input("Max posts this run", min_value=1, max_value=50, value=1)
        with c_right:
            st.write("")
            btn_preview, btn_live = st.columns(2)
            run_preview = btn_preview.button("🧪 Dry-Run Preview", width="stretch")
            run_live = btn_live.button("📤 Publish Now", type="primary", width="stretch")

        if run_preview:
            preview_settings = replace(s, dry_run=True)
            with st.spinner("Running safe dry-run preview..."):
                res = publish_rows(target_rows, max_posts=int(max_posts), settings=preview_settings, force=effective_force)
            st.success(f"Preview complete: {res}")
            if target_rows:
                sample = target_rows[0]
                link = resolve_affiliate_link(sample["product_id"], sample["url"], preview_settings, subid="deals_shirts")
                prod = Product(
                    product_id=sample["product_id"],
                    title=sample["title"],
                    url=sample["url"],
                    price=float(sample.get("price") or 0),
                    mrp=float(sample.get("mrp") or 0),
                    category=sample.get("category") or "Shirt",
                    image_url=sample.get("image_url") or "",
                    price_verified=bool(sample.get("price_verified")),
                )
                st.code(build_shirt_caption(prod, link.tracking_url), language="html")

        if run_live:
            if s.dry_run:
                st.warning("DRY_RUN=true in .env — running in simulation mode (nothing sent to Telegram).")
            with st.spinner("Publishing from Google Sheet..."):
                res = publish_rows(target_rows, max_posts=int(max_posts), settings=s, force=effective_force)
            st.success(f"Run finished: {res}")
            st.rerun()
    else:
        st.warning("No valid AJIO rows found in Google Sheet.")

    st.divider()
    st.markdown("### ➕ Add New AJIO Deal to Google Sheet")
    with st.form("add_deal_form", clear_on_submit=True):
        title = st.text_input("Product Title*", placeholder="Men Graphic Print Oversized T-Shirt")
        url = st.text_input("AJIO Product URL*", placeholder="https://www.ajio.com/.../p/...")
        c1, c2, c3 = st.columns(3)
        price = c1.text_input("Deal Price (INR)", placeholder="300")
        mrp = c2.text_input("MRP (INR)", placeholder="1999")
        image_url = c3.text_input("AJIO Image URL", placeholder="https://assets-jiocdn.ajio.com/...")
        submitted = st.form_submit_button("💾 Save to Google Sheet")

        if submitted:
            saved, err = append_sheet_row(
                s,
                title=title,
                url=url,
                price=price,
                mrp=mrp,
                image_url=image_url,
                platform="ajio",
            )
            if err:
                st.error(f"Rejected: {err}")
            else:
                st.success(f"Added `{saved['product_id']}` to Google Sheet! Refreshing...")
                st.rerun()


def _render_link_tab(s: Settings) -> None:
    st.subheader("🔗 Affiliate Link Checker & Guardrail Tester")
    test_url = st.text_input(
        "Paste any product URL (AJIO works; Flipkart is automatically blocked)",
        value="https://www.ajio.com/crazymonk-men-graphic-print-oversized-crew-neck-t-shirt/p/703488518_black",
    )
    subid = st.text_input("Sub-ID (p1)", value="deals_shirts")
    if st.button("🔍 Generate & Verify Link"):
        link = resolve_affiliate_link("CHECK-UI", test_url, s, subid=subid)
        if link.is_eligible:
            st.success(f"Eligible ({link.provider} — {link.campaign_name})")
            st.code(link.tracking_url, language="text")
            st.markdown(f"[Test Opening Tracking Link ↗]({link.tracking_url})")
        else:
            st.error(f"Rejected ({link.provider}): {link.reason}")


def _render_analytics_tab(s: Settings, db: Database, report: dict) -> None:
    st.subheader("💰 Confirmed Posts & Commission Tracker")
    st.caption("Only record real confirmed commission after verifying in your Vibconnect / AJIO ACE Conversion Report.")

    recent = report.get("recent", [])
    if recent:
        st.dataframe(recent, width="stretch", hide_index=True)
    else:
        st.info("No live posts recorded yet.")

    st.markdown("### 📝 Record Confirmed Vibconnect Commission")
    with st.form("commission_form"):
        c1, c2 = st.columns(2)
        post_id = c1.number_input("Post ID (from table above)", min_value=1, step=1)
        amount = c2.number_input("Confirmed Commission (INR)", min_value=0.0, step=10.0)
        confirmed = st.checkbox("I verified this exact commission in Vibconnect / AJIO ACE dashboard")
        save_comm = st.form_submit_button("Save Commission")
        if save_comm:
            if not confirmed:
                st.error("Check the verification box first — never guess or fabricate commissions.")
            elif not db.post_exists(int(post_id)):
                st.error(f"Post #{int(post_id)} not found in SQLite database.")
            else:
                db.record_commission(int(post_id), float(amount))
                st.success(f"Saved Rs {amount:,.2f} for Post #{int(post_id)}.")
                st.rerun()


def _render_logs_tab() -> None:
    st.subheader("📜 Daily Scheduler Logs")
    name, content = _read_latest_log()
    if name:
        st.caption(f"Latest log file: `logs/{name}`")
        st.code(content or "(log is empty)", language="log")
    else:
        st.info(content)


def main() -> None:
    s = get_settings()
    db = Database(s.db_path)
    db.init()
    report = db.report(limit=25)

    _render_header(s, report)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📲 Sheet & Publish",
        "🔗 Link Checker",
        "💰 Earnings & Posts",
        "📜 Daily Logs",
    ])
    with tab1:
        _render_sheet_tab(s, db=db)
    with tab2:
        _render_link_tab(s)
    with tab3:
        _render_analytics_tab(s, db, report)
    with tab4:
        _render_logs_tab()


if __name__ == "__main__":
    main()
