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
    name          TEXT NOT NULL UNIQUE,  -- roster display name (or Slack name if unrostered)
    slack_name    TEXT UNIQUE,           -- how they appear in Slack messages
    slack_user_id TEXT UNIQUE,           -- Slack's ID for them, e.g. U0123ABC
    position      TEXT,                  -- O Handler / O Cutter / D Handler / D Cutter / ...
    is_rostered   INTEGER NOT NULL DEFAULT 0,  -- 1 = on the official roster
    is_active     INTEGER NOT NULL DEFAULT 1   -- 0 = filtered off the dashboard
);

CREATE TABLE IF NOT EXISTS injuries (
    id           INTEGER PRIMARY KEY,
    player_id    INTEGER NOT NULL REFERENCES players(id),
    description  TEXT NOT NULL,     -- what happened, e.g. 'turf toe'
    excused_from TEXT NOT NULL CHECK (excused_from IN ('throwing', 'cardio', 'both')),
    start_date   TEXT NOT NULL,     -- YYYY-MM-DD
    end_date     TEXT               -- YYYY-MM-DD, or NULL while still recovering
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


def seed_roster(conn, roster_players: list) -> None:
    """Load the official roster so every rostered player exists in the
    database — even ones who have never posted (they show as non-compliant,
    which is the whole point of an accountability dashboard)."""
    for entry in roster_players:
        conn.execute(
            """INSERT INTO players (name, slack_name, position, is_rostered)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(name) DO UPDATE
               SET slack_name = excluded.slack_name,
                   position = excluded.position,
                   is_rostered = 1""",
            (entry["name"], entry["slack_name"], entry["position"]),
        )


def player_for_slack_name(conn, slack_name: str) -> int:
    """Find the player who posts under this Slack name. People who post but
    aren't on the roster still get stored (as unrostered), so no data is
    ever thrown away — the dashboard just doesn't show them by default."""
    row = conn.execute(
        "SELECT id FROM players WHERE slack_name = ? OR name = ?",
        (slack_name, slack_name),
    ).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO players (name, slack_name, is_rostered) VALUES (?, ?, 0)",
        (slack_name, slack_name),
    )
    return cursor.lastrowid


def roster_players(conn) -> list:
    """Every rostered, non-filtered player, in roster (position) order."""
    position_order = "CASE position WHEN 'O Handler' THEN 0 WHEN 'O Cutter' THEN 1 " \
                     "WHEN 'D Handler' THEN 2 WHEN 'D Cutter' THEN 3 ELSE 4 END"
    rows = conn.execute(
        f"""SELECT id, name, position FROM players
            WHERE is_rostered = 1 AND is_active = 1
            ORDER BY {position_order}, id"""
    )
    return [dict(row) for row in rows]


def unrostered_posters(conn) -> list:
    """People who post in the channel but aren't on the official roster."""
    rows = conn.execute(
        """SELECT DISTINCT p.name FROM players p
           JOIN posts po ON po.player_id = p.id
           WHERE p.is_rostered = 0 ORDER BY p.name"""
    )
    return [row["name"] for row in rows]


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


def add_injury(conn, player_name: str, description: str, excused_from: str,
               start_date: str, end_date: str | None = None) -> None:
    """Record an injury so the player is excused instead of non-compliant."""
    row = conn.execute("SELECT id FROM players WHERE name = ?", (player_name,)).fetchone()
    if row is None:
        raise ValueError(f"No player named {player_name!r} — check the spelling")
    conn.execute(
        """INSERT INTO injuries (player_id, description, excused_from, start_date, end_date)
           VALUES (?, ?, ?, ?, ?)""",
        (row["id"], description, excused_from, start_date, end_date),
    )


def injuries_by_player(conn) -> dict:
    """{player_name: [injury rows]} for every recorded injury."""
    rows = conn.execute(
        """SELECT p.name, i.description, i.excused_from, i.start_date, i.end_date
           FROM injuries i JOIN players p ON p.id = i.player_id"""
    )
    result: dict = {}
    for row in rows:
        result.setdefault(row["name"], []).append(dict(row))
    return result


def injury_excuses_for_week(injuries: list, week_start: str) -> tuple:
    """Given one player's injuries, which boxes are excused this week?

    An injury covers a week if the two date ranges overlap at all.
    Returns (throwing_excused, cardio_excused, note).
    """
    week_end = (date.fromisoformat(week_start) + timedelta(days=6)).isoformat()
    throwing = cardio = False
    notes = []
    for injury in injuries:
        started_before_week_ended = injury["start_date"] <= week_end
        still_active = injury["end_date"] is None or injury["end_date"] >= week_start
        if started_before_week_ended and still_active:
            if injury["excused_from"] in ("throwing", "both"):
                throwing = True
            if injury["excused_from"] in ("cardio", "both"):
                cardio = True
            notes.append(f"{injury['description']} (excused: {injury['excused_from']})")
    return throwing, cardio, "; ".join(notes)


def all_weeks(conn) -> list:
    """Every week (as its Monday date string) that has at least one post."""
    rows = conn.execute("SELECT DISTINCT week_start FROM posts ORDER BY week_start")
    return [row["week_start"] for row in rows]


def weekly_compliance(conn, rostered_only: bool = True) -> dict:
    """The heart of the dashboard.

    Returns {player_name: {week_start: {"throwing": bool, "cardio": bool}}}.
    Every included player appears, even with zero posts (empty inner dict).
    A week missing from a player's dict means they posted nothing that week.
    """
    where = "p.is_active = 1" + (" AND p.is_rostered = 1" if rostered_only else "")
    rows = conn.execute(
        f"""SELECT p.name, po.week_start,
                   MAX(po.label IN ('throwing', 'combined')) AS throwing_ok,
                   MAX(po.label IN ('cardio', 'combined'))   AS cardio_ok
            FROM players p LEFT JOIN posts po ON po.player_id = p.id
            WHERE {where}
            GROUP BY p.name, po.week_start
            ORDER BY p.name, po.week_start"""
    )
    result: dict = {}
    for row in rows:
        result.setdefault(row["name"], {})
        if row["week_start"] is not None:
            result[row["name"]][row["week_start"]] = {
                "throwing": bool(row["throwing_ok"]),
                "cardio": bool(row["cardio_ok"]),
            }
    return result
