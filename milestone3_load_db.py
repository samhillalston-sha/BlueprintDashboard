"""Milestone 3: load real posts into the database and print weekly compliance.

Starts the database fresh each run (safe: everything is rebuilt from the
message data), classifies every post, stores it, then prints the
player-by-week compliance grid — a text preview of the future dashboard.

Run it with:  python milestone3_load_db.py
"""

import json
from datetime import date
from pathlib import Path

from app import db
from app.classify import classify

DATA_FILE = Path(__file__).parent / "data" / "messages_sample.json"
ROSTER_FILE = Path(__file__).parent / "roster.json"
INJURY_FILE = Path(__file__).parent / "data" / "injuries.json"
# Who is *pictured* in each post (manual review, milestone6_review.py). Lives at
# the repo root, not in data/, so the human effort survives a fresh container.
APPEARANCE_FILE = Path(__file__).parent / "appearances.json"

# The commissioner ruled: the season starts June 8. Earlier posts are ignored.
SEASON_START = date(2026, 6, 8)

CREDITABLE = {"throwing", "cardio", "combined"}


def apply_appearances(conn, posts_by_ts: dict) -> int:
    """Grant appearance credit from appearances.json.

    Format: {source_ts: {"players": [display names pictured], "reviewed": bool}}.
    The poster already has their own post, so they need not be listed. Each
    named player gets the source post's activity credited for that week.
    Returns how many individual credits were applied.
    """
    if not APPEARANCE_FILE.exists():
        return 0
    data = json.loads(APPEARANCE_FILE.read_text())
    applied = 0
    for source_ts, entry in data.items():
        post = posts_by_ts.get(source_ts)
        if post is None:
            continue  # post not in the current window / data — skip quietly
        result = classify(post["text"])
        if result.label not in CREDITABLE:
            continue  # nothing to credit (strength/PT/recovery post)
        for name in entry.get("players", []):
            player_id = db.player_for_slack_name(conn, name)
            db.add_appearance_credit(
                conn,
                player_id=player_id,
                posted_on=date.fromisoformat(post["date"]),
                label=result.label,
                source_ts=source_ts,
                source_poster=post["user"],
            )
            applied += 1
    return applied


def main() -> None:
    if not DATA_FILE.exists():
        print(f"No data file at {DATA_FILE} — pull messages from Slack first.")
        return

    # Fresh start each run, so re-running never duplicates anything.
    db.DB_FILE.unlink(missing_ok=True)
    conn = db.connect()

    # The roster goes in first, so every rostered player exists even if
    # they've never posted. Posters not on the roster are kept but hidden.
    db.seed_roster(conn, json.loads(ROSTER_FILE.read_text())["players"])

    messages = [m for m in json.loads(DATA_FILE.read_text())
                if date.fromisoformat(m["date"]) >= SEASON_START]
    # Remember each post's verdict by its Slack ts so appearance credits can
    # inherit the right activity + date without re-classifying.
    posts_by_ts: dict = {}
    for message in messages:
        result = classify(message["text"])
        player_id = db.player_for_slack_name(conn, message["user"])
        db.add_post(
            conn,
            player_id=player_id,
            posted_on=date.fromisoformat(message["date"]),
            text=message["text"],
            label=result.label,
            tags=result.tags,
            has_photo=message.get("has_photo", False),
            slack_ts=message.get("ts"),
        )
        if message.get("ts"):
            posts_by_ts[message["ts"]] = message

    # Appearance credit: being pictured in a throwing/cardio/combined post
    # counts exactly like posting it yourself. Non-creditable posts (strength,
    # PT, recovery) tick no box, so appearing in one earns nothing — skip them.
    appearances_applied = apply_appearances(conn, posts_by_ts)

    # Injuries go in last (players must exist first).
    if INJURY_FILE.exists():
        for injury in json.loads(INJURY_FILE.read_text())["injuries"]:
            db.add_injury(conn, injury["player"], injury["description"],
                          injury["excused_from"], injury["start_date"],
                          injury["end_date"])
    conn.commit()

    weeks = db.all_weeks(conn)
    compliance = db.weekly_compliance(conn)
    print(f"Loaded {len(messages)} posts by {len(compliance)} players "
          f"across {len(weeks)} weeks into {db.DB_FILE.name}")
    print(f"Applied {appearances_applied} appearance credit(s) "
          f"from {APPEARANCE_FILE.name}\n")

    # Print the compliance grid: one row per player, one column per week.
    # T = throwing done, C = cardio done, · = box not ticked.
    header = "PLAYER".ljust(24) + "".join(f"wk {w[5:]} " for w in weeks)
    print(header)
    print("-" * len(header))
    for name in sorted(compliance):
        cells = []
        for week in weeks:
            status = compliance[name].get(week)
            if status is None:
                cell = "  --  "
            else:
                t = "T" if status["throwing"] else "·"
                c = "C" if status["cardio"] else "·"
                cell = f"  {t}{c}  "
            cells.append(cell)
        print(name.ljust(24) + " ".join(cells))

    print("\nT = throwing ✓   C = cardio ✓   · = missing   -- = no posts that week")


if __name__ == "__main__":
    main()
