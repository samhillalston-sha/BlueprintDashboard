"""M2: SlackProvider — the real 'Add to Slack' OAuth install flow.

Replaces the old per-customer "copy your bot token into .env" approach
with Slack's standard OAuth v2 handshake. Uses slack-sdk directly against
the Slack Web API (not the dev-sandbox MCP connector, which was only a
workaround for this environment's earlier network restrictions — see
docs/RESYNC.md and docs/SCALABILITY_PLAN.md; a deployed instance of this
app has normal internet access and doesn't need that workaround).
"""

import os
from datetime import date, datetime, timezone
from urllib.parse import urlencode

import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.messaging.base import Message, MessagingProvider, OAuthResult

# Least privilege for what M2 actually does: read channel history and
# resolve user IDs to display names. Posting/reminders would add
# chat:write later, when that feature exists — don't request it early.
SCOPES = "channels:history,channels:read,users:read"

AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
ACCESS_URL = "https://slack.com/api/oauth.v2.access"


class SlackOAuthError(Exception):
    pass


class SlackProvider(MessagingProvider):
    provider_type = "slack"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        self.client_id = client_id or os.environ.get("SLACK_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("SLACK_CLIENT_SECRET", "")

    def install_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "scope": SCOPES,
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> OAuthResult:
        response = requests.post(ACCESS_URL, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }, timeout=10)
        body = response.json()
        if not body.get("ok"):
            raise SlackOAuthError(body.get("error", "unknown_error"))

        config = {
            "team_id": body["team"]["id"],
            "team_name": body["team"]["name"],
            "scopes": body.get("scope", "").split(","),
            "channel_id": None,      # picked later, once the bot's been invited to a channel
            "channel_name": None,
        }
        credentials = {
            "bot_token": body["access_token"],
            "bot_user_id": body["bot_user_id"],
            "authed_user_id": body["authed_user"]["id"],
        }
        return OAuthResult(config=config, credentials=credentials)

    def resolve_channel(self, credentials: dict, channel_name: str) -> dict | None:
        """Find a public channel the bot can see by name (no leading #).

        The bot must already be a member of the channel (invited via
        `/invite @BotName` in Slack, same as any other app) for its
        history to be readable — OAuth alone doesn't grant that.
        """
        client = WebClient(token=credentials["bot_token"])
        cursor = None
        while True:
            response = client.conversations_list(types="public_channel", cursor=cursor, limit=200)
            for channel in response["channels"]:
                if channel["name"] == channel_name:
                    return {"id": channel["id"], "name": channel["name"]}
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                return None

    def fetch_recent_messages(self, credentials: dict, config: dict,
                               since: date) -> list[Message]:
        client = WebClient(token=credentials["bot_token"])
        channel_id = config["channel_id"]
        oldest_ts = datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc).timestamp()

        user_names: dict[str, str] = {}

        def display_name(user_id: str) -> str:
            if user_id not in user_names:
                try:
                    info = client.users_info(user=user_id)["user"]
                    user_names[user_id] = info.get("real_name") or info["name"]
                except SlackApiError:
                    user_names[user_id] = user_id
            return user_names[user_id]

        messages: list[Message] = []
        cursor = None
        while True:
            response = client.conversations_history(
                channel=channel_id, oldest=str(oldest_ts), cursor=cursor, limit=200,
            )
            for raw in response["messages"]:
                if raw.get("subtype"):  # skip joins/leaves/system events, thread-only rows, etc.
                    continue
                posted_on = datetime.fromtimestamp(float(raw["ts"]), tz=timezone.utc).date()
                messages.append(Message(
                    posted_on=posted_on,
                    user=display_name(raw["user"]),
                    text=(raw.get("text") or "").strip(),
                    has_photo=bool(raw.get("files")),
                ))
            if not response.get("has_more"):
                break
            cursor = response.get("response_metadata", {}).get("next_cursor")
        return messages
