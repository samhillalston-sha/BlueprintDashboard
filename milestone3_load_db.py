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


def main() -> None:
    if not DATA_FILE.exists():
        print(f"No data file at {DATA_FILE} — pull messages from Slack first.")
        return

    # Fresh start each run, so re-running never duplicates anything.
    db.DB_FILE.unlink(missing_ok=True)
    conn = db.connect()

    messages = json.loads(DATA_FILE.read_text())
    for message in messages:
        result = classify(message["text"])
        player_id = db.get_or_create_player(conn, message["user"])
        db.add_post(
            conn,
            player_id=player_id,
            posted_on=date.fromisoformat(message["date"]),
            text=message["text"],
            label=result.label,
            tags=result.tags,
        )
    conn.commit()

    weeks = db.all_weeks(conn)
    compliance = db.weekly_compliance(conn)
    print(f"Loaded {len(messages)} posts by {len(compliance)} players "
          f"across {len(weeks)} weeks into {db.DB_FILE.name}\n")

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
