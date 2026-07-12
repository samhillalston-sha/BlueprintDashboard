"""M2: recurring Slack sync — the OAuth-based replacement for the manual
RESYNC.md pull, for any org that's completed the /integrations/slack/install
flow. Safe to run repeatedly: posts are keyed on (org_id, slack_ts), so an
already-synced message is silently skipped, never duplicated.

Run it with:  .venv/bin/python sync_slack.py <org_id>
"""

import sys
from datetime import date, timedelta

from app.classify import classify
from app.db import week_start_of
from app.messaging.slack_provider import SlackProvider
from app.messaging.store import get_integration_for_sync
from app.roster_store import player_id_for_slack_name
from app.supabase_rest import SERVICE_HEADERS, service_rest

# If an org has never synced before, how far back to catch up. Once
# there's at least one post, we sync forward from the latest one instead.
DEFAULT_LOOKBACK_DAYS = 14


def last_synced_date(org_id: str) -> date | None:
    rows = service_rest(
        "GET", "posts",
        params={"org_id": f"eq.{org_id}", "select": "posted_on",
                "order": "posted_on.desc", "limit": "1"},
    ).json()
    return date.fromisoformat(rows[0]["posted_on"]) if rows else None


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: sync_slack.py <org_id>")
        sys.exit(1)
    org_id = sys.argv[1]

    integration = get_integration_for_sync(org_id, "slack")
    if integration is None:
        print(f"No Slack integration for org {org_id} — "
              f"run the /integrations/slack/install flow first.")
        sys.exit(1)
    config, credentials = integration
    if not config.get("channel_id"):
        print("Slack is connected but no channel has been picked yet for this org "
              "(config.channel_id is unset) — nothing to sync.")
        sys.exit(1)

    since = last_synced_date(org_id) or (date.today() - timedelta(days=DEFAULT_LOOKBACK_DAYS))
    provider = SlackProvider()
    messages = provider.fetch_recent_messages(credentials, config, since)

    if not messages:
        print("No messages found since", since.isoformat())
        return

    player_cache: dict = {}
    posts_payload = []
    for message in messages:
        result = classify(message.text)
        player_id = player_id_for_slack_name(org_id, message.user, player_cache)
        posts_payload.append({
            "org_id": org_id,
            "player_id": player_id,
            "posted_on": message.posted_on.isoformat(),
            "week_start": week_start_of(message.posted_on).isoformat(),
            "text": message.text,
            "label": result.label,
            "tags": ",".join(sorted(result.tags)),
            "has_photo": message.has_photo,
            "slack_ts": message.provider_message_id,
        })

    inserted = service_rest(
        "POST", "posts",
        params={"on_conflict": "org_id,slack_ts"},
        json=posts_payload,
        headers={**SERVICE_HEADERS, "Prefer": "resolution=ignore-duplicates,return=representation"},
    ).json()
    skipped = len(posts_payload) - len(inserted)
    print(f"Fetched {len(posts_payload)} messages since {since.isoformat()}: "
          f"{len(inserted)} new posts stored, {skipped} already synced (skipped).")


if __name__ == "__main__":
    main()
