"""SQL database layer using SQLite with clean schema design."""
import sqlite3
import os
from contextlib import contextmanager
from typing import List, Optional
from datetime import datetime


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self):
        """Create tables for products, published posts, and performance metrics."""
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS products (
                    product_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    price REAL,
                    mrp REAL,
                    category TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    affiliate_url TEXT NOT NULL,
                    headline TEXT,
                    caption TEXT,
                    telegram_message_id INTEGER,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (product_id) REFERENCES products(product_id)
                );

                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    clicks INTEGER DEFAULT 0,
                    orders INTEGER DEFAULT 0,
                    commission REAL DEFAULT 0.0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES posts(id)
                );

                CREATE TABLE IF NOT EXISTS seen_products (
                    product_id TEXT PRIMARY KEY,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    dry_run INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_posts_product_id ON posts(product_id);
                INSERT OR IGNORE INTO seen_products (product_id, dry_run)
                    SELECT product_id, 0 FROM posts;
            """)

    def is_product_posted(self, product_id: str) -> bool:
        with self._connection() as conn:
            cur = conn.execute("SELECT 1 FROM posts WHERE product_id = ?", (product_id,))
            return cur.fetchone() is not None

    def is_seen(self, product_id: str, include_dry_run: bool = True) -> bool:
        """True if already handled. Live runs ignore dry-run-only previews."""
        query = "SELECT 1 FROM seen_products WHERE product_id = ?"
        params = [product_id]
        if not include_dry_run:
            query += " AND dry_run = 0"
        with self._connection() as conn:
            cur = conn.execute(query, params)
            return cur.fetchone() is not None

    def mark_seen(self, product_id: str, dry_run: bool = False) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO seen_products (product_id, dry_run) VALUES (?, ?)",
                (product_id, 1 if dry_run else 0),
            )

    def record_post(self, product_id: str, provider: str, affiliate_url: str,
                    headline: str, caption: str, telegram_message_id: Optional[int] = None) -> int:
        with self._connection() as conn:
            cur = conn.execute("""
                INSERT INTO posts (product_id, provider, affiliate_url, headline, caption, telegram_message_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (product_id, provider, affiliate_url, headline, caption, telegram_message_id))
            return cur.lastrowid

    def report(self, limit: int = 10) -> dict:
        """Read-only summary for the CLI: post counts, seen ledger, metrics, recent posts."""
        with self._connection() as conn:
            posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            seen = conn.execute("SELECT COUNT(*) FROM seen_products").fetchone()[0]
            dry_seen = conn.execute(
                "SELECT COUNT(*) FROM seen_products WHERE dry_run = 1"
            ).fetchone()[0]
            metrics = conn.execute("""
                SELECT COUNT(*) AS rows,
                       COALESCE(SUM(clicks), 0) AS clicks,
                       COALESCE(SUM(orders), 0) AS orders,
                       COALESCE(SUM(commission), 0) AS commission
                FROM metrics
            """).fetchone()
            recent = conn.execute("""
                SELECT id, product_id, provider, posted_at, affiliate_url
                FROM posts ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()
            top = conn.execute("""
                SELECT product_id, COUNT(*) AS posts
                FROM posts GROUP BY product_id ORDER BY posts DESC LIMIT ?
            """, (limit,)).fetchall()
            commission_month = conn.execute("""
                SELECT COALESCE(SUM(commission), 0) FROM metrics
                WHERE strftime('%Y-%m', updated_at) = strftime('%Y-%m', 'now')
            """).fetchone()[0]
        return {
            "posts": posts,
            "seen": seen,
            "dry_run_seen": dry_seen,
            "metrics": dict(metrics),
            "commission_month": float(commission_month),
            "recent": [dict(r) for r in recent],
            "top": [dict(r) for r in top],
        }

    def reset_history(self) -> dict:
        """DANGER: delete posts, metrics and the seen ledger (manual testing only)."""
        with self._connection() as conn:
            metrics = conn.execute("DELETE FROM metrics").rowcount
            posts = conn.execute("DELETE FROM posts").rowcount
            seen = conn.execute("DELETE FROM seen_products").rowcount
        return {"posts": posts, "seen": seen, "metrics": metrics}

    def post_exists(self, post_id: int) -> bool:
        with self._connection() as conn:
            row = conn.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone()
            return row is not None

    def record_commission(self, post_id: int, amount: float) -> None:
        """Set the confirmed commission for one post (overwrite, never double-count)."""
        with self._connection() as conn:
            exists = conn.execute("SELECT 1 FROM metrics WHERE post_id = ?", (post_id,)).fetchone()
            if exists:
                conn.execute(
                    "UPDATE metrics SET commission = ?, updated_at = CURRENT_TIMESTAMP WHERE post_id = ?",
                    (amount, post_id),
                )
            else:
                conn.execute(
                    "INSERT INTO metrics (post_id, commission) VALUES (?, ?)",
                    (post_id, amount),
                )

    def commission_this_month(self) -> float:
        with self._connection() as conn:
            row = conn.execute("""
                SELECT COALESCE(SUM(commission), 0) FROM metrics
                WHERE strftime('%Y-%m', updated_at) = strftime('%Y-%m', 'now')
            """).fetchone()
            return float(row[0])
