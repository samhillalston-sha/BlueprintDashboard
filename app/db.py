"""Milestone 3: store players and their weekly submissions in SQLite.

SQLite is a whole database that lives in a single file (blueprint.db) —
no server to run, perfect for a team-sized project. This module owns
everything database-shaped:

  - the schema (the shape of our two tables, players and posts)
  - "weeks run Monday–Sunday" logic
  - the weekly compliance question: for each player and week,
    did they post throwing? did they post cardio?

Compliance rules (per the commissioner):
  - a "throwing" or "combined" post ticks the throwing box
  - a "cardio" or "combined" post ticks the cardio box
    (playing ultimate or another sport counts as cardio)
  - strength / PT / recovery posts tick neither box
"""

import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_FILE = Path(__file__).resolve().parent.parent / "blueprint.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    slack_user_id TEXT UNIQUE,           -- Slack's ID for them, e.g. U0123ABC
    is_active     INTEGER NOT NULL DEFAULT 1  -- 0 = filtered off the dashboard
);

CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY,
    player_id  INTEGER NOT NULL REFERENCES players(id),
    posted_on  TEXT NOT NULL,   -- calendar date, like '2026-07-04'
    week_start TEXT NOT NULL,   -- the Monday of that week (our week key)
    text       TEXT NOT NULL,
    label      TEXT NOT NULL,   -- classifier verdict: throwing/cardio/combined/...
    tags       TEXT NOT NULL DEFAULT '',  -- every category the post mentioned
    has_photo  INTEGER NOT NULL DEFAULT 0,
    slack_ts   TEXT UNIQUE      -- Slack's message ID; stops re-syncs duplicating
);
"""


def connect(db_file: Path = DB_FILE) -> sqlite3.Connection:
    """Open the database file, creating it (and the tables) if needed."""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row  # lets us read columns by name
    conn.executescript(SCHEMA)
    return conn


def week_start_of(day: date) -> date:
    """The Monday that starts this date's week (weeks run Mon–Sun)."""
    return day - timedelta(days=day.weekday())


def get_or_create_player(conn, name: str, slack_user_id: str | None = None) -> int:
    """Find a player by name, creating them on first sight. Returns their id."""
    row = conn.execute("SELECT id FROM players WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO players (name, slack_user_id) VALUES (?, ?)",
        (name, slack_user_id),
    )
    return cursor.lastrowid


def add_post(
    conn,
    player_id: int,
    posted_on: date,
    text: str,
    label: str,
    tags: set,
    has_photo: bool = False,
    slack_ts: str | None = None,
) -> None:
    """Store one classified post. Duplicate Slack messages are skipped."""
    conn.execute(
        """INSERT OR IGNORE INTO posts
           (player_id, posted_on, week_start, text, label, tags, has_photo, slack_ts)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            player_id,
            posted_on.isoformat(),
            week_start_of(posted_on).isoformat(),
            text,
            label,
            ",".join(sorted(tags)),
            int(has_photo),
            slack_ts,
        ),
    )


def all_weeks(conn) -> list:
    """Every week (as its Monday date string) that has at least one post."""
    rows = conn.execute("SELECT DISTINCT week_start FROM posts ORDER BY week_start")
    return [row["week_start"] for row in rows]


def weekly_compliance(conn) -> dict:
    """The heart of the dashboard.

    Returns {player_name: {week_start: {"throwing": bool, "cardio": bool}}}.
    A week that's missing from a player's dict means they posted nothing.
    """
    rows = conn.execute(
        """SELECT p.name, po.week_start,
                  MAX(po.label IN ('throwing', 'combined')) AS throwing_ok,
                  MAX(po.label IN ('cardio', 'combined'))   AS cardio_ok
           FROM posts po JOIN players p ON p.id = po.player_id
           WHERE p.is_active = 1
           GROUP BY p.name, po.week_start
           ORDER BY p.name, po.week_start"""
    )
    result: dict = {}
    for row in rows:
        result.setdefault(row["name"], {})[row["week_start"]] = {
            "throwing": bool(row["throwing_ok"]),
            "cardio": bool(row["cardio_ok"]),
        }
    return result
