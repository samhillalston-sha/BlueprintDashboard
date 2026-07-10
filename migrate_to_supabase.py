"""M1 task 3: load real posts + injuries into Supabase for one org.

The Postgres/multi-tenant equivalent of milestone3_load_db.py. Talks to
Supabase over the REST API (PostgREST) using the service-role key —
there's no raw Postgres connection available from this environment (see
docs/SCALABILITY_PLAN.md). Assumes the org, its team_config, and its
roster (players) already exist — this script only adds posts and
injuries.

Run it with:  .venv/bin/python migrate_to_supabase.py <org_id>
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

from app.classify import classify
from app.db import week_start_of

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
HEADERS = {
    "apikey": os.environ["SUPABASE_SECRET_KEY"],
    "Authorization": f"Bearer {os.environ['SUPABASE_SECRET_KEY']}",
    "Content-Type": "application/json",
}

DATA_FILE = Path(__file__).parent / "data" / "messages_sample.json"
INJURY_FILE = Path(__file__).parent / "data" / "injuries.json"

# The commissioner ruled: the season starts June 8. Earlier posts are ignored.
SEASON_START = date(2026, 6, 8)


def rest(method: str, path: str, *, headers: dict | None = None, **kwargs) -> requests.Response:
    response = requests.request(method, f"{SUPABASE_URL}/rest/v1/{path}",
                                 headers=headers or HEADERS, timeout=15, **kwargs)
    response.raise_for_status()
    return response


def player_id_for_slack_name(org_id: str, slack_name: str, cache: dict) -> int:
    """Find-or-create a player row by Slack display name, scoped to the org.

    Mirrors app/db.py's player_for_slack_name: posters not on the roster
    still get stored (as unrostered), matched by slack_name OR name.
    """
    if slack_name in cache:
        return cache[slack_name]
    existing = rest(
        "GET", "players",
        params={"org_id": f"eq.{org_id}",
                "or": f"(slack_name.eq.{slack_name},name.eq.{slack_name})",
                "select": "id"},
    ).json()
    if existing:
        cache[slack_name] = existing[0]["id"]
        return existing[0]["id"]
    created = rest(
        "POST", "players",
        json={"org_id": org_id, "name": slack_name, "slack_name": slack_name,
              "is_rostered": False},
        headers={**HEADERS, "Prefer": "return=representation"},
    ).json()
    cache[slack_name] = created[0]["id"]
    return created[0]["id"]


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: migrate_to_supabase.py <org_id>")
        sys.exit(1)
    org_id = sys.argv[1]

    if not DATA_FILE.exists():
        print(f"No data file at {DATA_FILE} — pull messages from Slack first.")
        sys.exit(1)

    messages = [m for m in json.loads(DATA_FILE.read_text())
                if date.fromisoformat(m["date"]) >= SEASON_START]

    player_cache: dict = {}
    posts_payload = []
    for message in messages:
        result = classify(message["text"])
        player_id = player_id_for_slack_name(org_id, message["user"], player_cache)
        posted_on = date.fromisoformat(message["date"])
        posts_payload.append({
            "org_id": org_id,
            "player_id": player_id,
            "posted_on": posted_on.isoformat(),
            "week_start": week_start_of(posted_on).isoformat(),
            "text": message["text"],
            "label": result.label,
            "tags": ",".join(sorted(result.tags)),
            "has_photo": message.get("has_photo", False),
        })

    # Batch insert — PostgREST accepts an array body for bulk insert.
    BATCH = 200
    inserted = 0
    for i in range(0, len(posts_payload), BATCH):
        batch = posts_payload[i:i + BATCH]
        rest("POST", "posts", json=batch, headers={**HEADERS, "Prefer": "return=minimal"})
        inserted += len(batch)
    print(f"Inserted {inserted} posts across {len(player_cache)} distinct posters.")

    if INJURY_FILE.exists():
        injuries = json.loads(INJURY_FILE.read_text())["injuries"]
        injury_count = 0
        for injury in injuries:
            existing = rest(
                "GET", "players",
                params={"org_id": f"eq.{org_id}", "name": f"eq.{injury['player']}", "select": "id"},
            ).json()
            if not existing:
                print(f"  skipping injury for unknown player {injury['player']!r}")
                continue
            rest("POST", "injuries", json={
                "org_id": org_id,
                "player_id": existing[0]["id"],
                "description": injury["description"],
                "excused_from": injury["excused_from"],
                "start_date": injury["start_date"],
                "end_date": injury.get("end_date"),
            })
            injury_count += 1
        print(f"Inserted {injury_count} injuries.")
    else:
        print(f"No injury file at {INJURY_FILE} — skipping (none to migrate).")


if __name__ == "__main__":
    main()
