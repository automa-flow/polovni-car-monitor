"""SQLite store for processed listings."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS ads (
  ad_id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT,
  first_seen_ts INTEGER NOT NULL,
  last_seen_ts INTEGER NOT NULL,
  content_hash TEXT,
  last_score INTEGER DEFAULT 0,
  notified INTEGER NOT NULL DEFAULT 0,
  last_price INTEGER,
  price_checked_ts INTEGER
);

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
"""

# Columns added after the first release; applied to pre-existing databases.
_MIGRATIONS = {
    "last_price": "ALTER TABLE ads ADD COLUMN last_price INTEGER",
    "price_checked_ts": "ALTER TABLE ads ADD COLUMN price_checked_ts INTEGER",
}


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add any columns missing from an older `ads` table (SQLite has no
    ``ADD COLUMN IF NOT EXISTS``)."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(ads)")}
    for column, ddl in _MIGRATIONS.items():
        if column not in existing:
            conn.execute(ddl)


def count_ads(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0]


def count_notified_since(conn: sqlite3.Connection, since_ts: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM ads WHERE notified = 1 AND first_seen_ts >= ?",
        (since_ts,),
    ).fetchone()[0]


def get_ad(conn: sqlite3.Connection, ad_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM ads WHERE ad_id = ?", (ad_id,)).fetchone()


def iter_notified(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """All listings that were ever notified, newest first (for export)."""
    return conn.execute(
        "SELECT * FROM ads WHERE notified = 1 ORDER BY first_seen_ts DESC"
    ).fetchall()


def touch_ad(conn: sqlite3.Connection, ad_id: str, ts: int) -> None:
    """Mark a known listing as still present (updates last_seen_ts only)."""
    conn.execute("UPDATE ads SET last_seen_ts = ? WHERE ad_id = ?", (ts, ad_id))


def update_price(conn: sqlite3.Connection, ad_id: str, price: int | None, ts: int) -> None:
    """Record the latest observed price for a known listing after a re-check."""
    conn.execute(
        "UPDATE ads SET last_price = ?, price_checked_ts = ?, last_seen_ts = ? "
        "WHERE ad_id = ?",
        (price, ts, ts, ad_id),
    )


def seed_ad(
    conn: sqlite3.Connection, ad_id: str, url: str, title: str | None, ts: int
) -> None:
    """Remember a listing during seeding. notified=1 => never notify retroactively."""
    conn.execute(
        """
        INSERT INTO ads (ad_id, url, title, first_seen_ts, last_seen_ts,
                         content_hash, last_score, notified)
        VALUES (?, ?, ?, ?, ?, NULL, 0, 1)
        ON CONFLICT(ad_id) DO UPDATE SET last_seen_ts = excluded.last_seen_ts
        """,
        (ad_id, url, title, ts, ts),
    )


def save_ad(
    conn: sqlite3.Connection,
    ad_id: str,
    url: str,
    title: str | None,
    ts: int,
    content_hash: str,
    score: int,
    notified: int,
    price: int | None = None,
) -> None:
    """Insert or update a row. first_seen_ts is preserved on update."""
    conn.execute(
        """
        INSERT INTO ads (ad_id, url, title, first_seen_ts, last_seen_ts,
                         content_hash, last_score, notified,
                         last_price, price_checked_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ad_id) DO UPDATE SET
            url = excluded.url,
            title = COALESCE(excluded.title, ads.title),
            last_seen_ts = excluded.last_seen_ts,
            content_hash = excluded.content_hash,
            last_score = excluded.last_score,
            notified = excluded.notified,
            last_price = excluded.last_price,
            price_checked_ts = excluded.price_checked_ts
        """,
        (ad_id, url, title, ts, ts, content_hash, score, notified, price, ts),
    )


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
