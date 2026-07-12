"""M2: the provider-agnostic interface every messaging integration implements.

Slack is the first implementation (app/messaging/slack_provider.py).
Discord or anything else later plugs in here without the rest of the app
(install flow, sync job, dashboard) needing to know which provider a
given org uses.
"""

from abc import ABC, abstractmethod
from datetime import date


class OAuthResult:
    """What a completed OAuth handshake hands back to the app.

    config: non-secret, safe to show a coach and to store in the
        `integrations` table (team name, channel, granted scopes).
    credentials: secrets (bot tokens, etc) — only ever written to
        `integration_credentials`, never returned to a browser session.
    """

    def __init__(self, config: dict, credentials: dict):
        self.config = config
        self.credentials = credentials


class Message:
    """One historical post, in the shape the classifier/sync job expects.

    provider_message_id is the provider's own immutable ID for this
    message (Slack's `ts`) — lets a repeated sync run safely skip
    messages it's already stored instead of creating duplicates.
    """

    def __init__(self, posted_on: date, user: str, text: str, has_photo: bool,
                 provider_message_id: str):
        self.posted_on = posted_on
        self.user = user
        self.text = text
        self.has_photo = has_photo
        self.provider_message_id = provider_message_id


class MessagingProvider(ABC):
    provider_type: str

    @abstractmethod
    def install_url(self, redirect_uri: str, state: str) -> str:
        """The URL to send a coach to for the 'Add to <Provider>' flow."""

    @abstractmethod
    def exchange_code(self, code: str, redirect_uri: str) -> OAuthResult:
        """Trade the OAuth callback's code for a live connection."""

    @abstractmethod
    def fetch_recent_messages(self, credentials: dict, config: dict,
                               since: date) -> list[Message]:
        """Pull every message from the connected channel since the given date."""
