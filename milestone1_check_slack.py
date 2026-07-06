"""Milestone 1: connect to Slack and print recent messages from the channel.

This script proves the whole pipeline can work. It:
  1. loads your bot token from the .env file,
  2. finds the #doyoulikefitness channel,
  3. fetches the 20 most recent messages,
  4. prints each one with the author's name and the date.

Run it with:  python milestone1_check_slack.py
"""

import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

HOW_MANY_MESSAGES = 20


def fail(message: str) -> None:
    """Print a friendly error and stop the program."""
    print(f"\n❌ {message}")
    print("   (See the troubleshooting table at the bottom of docs/SLACK_SETUP.md)")
    sys.exit(1)


def find_channel_id(client: WebClient, channel_name: str) -> str:
    """Slack identifies channels by an ID like 'C0123ABC', not by name.

    This looks through every channel the bot can see and returns the ID of
    the one whose name matches. Results come in pages, so we keep asking for
    the next page until Slack says there are no more.
    """
    cursor = None
    while True:
        response = client.conversations_list(
            types="public_channel,private_channel",
            limit=200,
            cursor=cursor,
        )
        for channel in response["channels"]:
            if channel["name"] == channel_name:
                return channel["id"]
        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            fail(
                f"Couldn't find a channel named #{channel_name}. "
                "Check the spelling in your .env file, and make sure the bot "
                "was invited to the channel (Step 4 of the setup guide)."
            )


def get_display_name(client: WebClient, user_id: str, name_cache: dict) -> str:
    """Turn a raw Slack user ID (like 'U0456DEF') into a human name.

    We remember names we've already looked up (the "cache") so we don't ask
    Slack for the same person twice.
    """
    if user_id not in name_cache:
        try:
            info = client.users_info(user=user_id)
            profile = info["user"]["profile"]
            name_cache[user_id] = (
                profile.get("display_name") or profile.get("real_name") or user_id
            )
        except SlackApiError:
            name_cache[user_id] = user_id  # fall back to the raw ID
    return name_cache[user_id]


def main() -> None:
    load_dotenv()  # read the .env file into this program's environment

    token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel_name = os.environ.get("SLACK_CHANNEL_NAME", "doyoulikefitness")

    if not token:
        fail(
            "No Slack token found. Copy .env.example to .env and paste your "
            "real bot token into it (Step 5 of docs/SLACK_SETUP.md)."
        )

    client = WebClient(token=token)

    # First, a quick handshake to confirm the token itself works.
    try:
        auth = client.auth_test()
    except SlackApiError as error:
        if error.response["error"] == "invalid_auth":
            fail("Slack rejected the token. Re-copy it from the OAuth & Permissions page.")
        fail(f"Couldn't connect to Slack: {error.response['error']}")

    print(f"✅ Connected to Slack workspace: {auth['team']} (as {auth['user']})")

    channel_id = find_channel_id(client, channel_name)
    print(f"✅ Found #{channel_name}")

    try:
        history = client.conversations_history(channel=channel_id, limit=HOW_MANY_MESSAGES)
    except SlackApiError as error:
        if error.response["error"] == "not_in_channel":
            fail(
                f"The bot isn't a member of #{channel_name} yet. In Slack, go "
                "to the channel and type: /invite @Blueprint Fitness Bot"
            )
        fail(f"Couldn't read messages: {error.response['error']}")

    messages = history["messages"]
    if not messages:
        print(f"\nThe channel exists but has no messages yet. Post something and re-run!")
        return

    print(f"\n📋 Last {len(messages)} messages in #{channel_name} (newest first):\n")

    name_cache: dict = {}
    for message in messages:
        # Slack timestamps are seconds-since-1970 in a string; make them readable.
        when = datetime.fromtimestamp(float(message["ts"])).strftime("%a %b %d, %Y %I:%M %p")
        who = get_display_name(client, message.get("user", "unknown"), name_cache)
        text = message.get("text", "").strip() or "(no text)"
        has_photo = any(
            f.get("mimetype", "").startswith("image/") for f in message.get("files", [])
        )
        photo_note = "  📷 [includes photo]" if has_photo else ""
        print(f"  [{when}] {who}: {text}{photo_note}")

    print("\n🎉 Milestone 1 complete — the pipeline works!")


if __name__ == "__main__":
    main()
