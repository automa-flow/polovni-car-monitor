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
  notified INTEGER NOT NULL DEFAULT 0
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def count_ads(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0]


def get_ad(conn: sqlite3.Connection, ad_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM ads WHERE ad_id = ?", (ad_id,)).fetchone()


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
) -> None:
    """Insert or update a row. first_seen_ts is preserved on update."""
    conn.execute(
        """
        INSERT INTO ads (ad_id, url, title, first_seen_ts, last_seen_ts,
                         content_hash, last_score, notified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ad_id) DO UPDATE SET
            url = excluded.url,
            title = COALESCE(excluded.title, ads.title),
            last_seen_ts = excluded.last_seen_ts,
            content_hash = excluded.content_hash,
            last_score = excluded.last_score,
            notified = excluded.notified
        """,
        (ad_id, url, title, ts, ts, content_hash, score, notified),
    )
