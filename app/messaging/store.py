"""M2: persistence for integrations — the Supabase side of the OAuth flow.

Split to match the schema's security boundary: the non-secret
`integrations` row is written with the coach's own access token (RLS
enforces it's their org, coach role); the `integration_credentials` row
is written with the service-role key, since `authenticated` has zero
grants on that table by design — a browser session must never be able
to write (or read) a live bot token.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")


def save_integration(user_access_token: str, org_id: str, provider_type: str,
                      config: dict, installed_by: str) -> int:
    """Upsert the non-secret integration row; returns its id."""
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/integrations",
        headers={
            "apikey": SUPABASE_PUBLISHABLE_KEY,
            "Authorization": f"Bearer {user_access_token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates",
        },
        params={"on_conflict": "org_id,provider_type"},
        json={"org_id": org_id, "provider_type": provider_type,
              "config": config, "installed_by": installed_by},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()[0]["id"]


def save_credentials(integration_id: int, credentials: dict) -> None:
    """Upsert the secret credentials row, service-role only."""
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/integration_credentials",
        headers={
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        params={"on_conflict": "integration_id"},
        json={"integration_id": integration_id, "credentials": credentials},
        timeout=10,
    )
    response.raise_for_status()


def get_integration_for_sync(org_id: str, provider_type: str) -> tuple[dict, dict] | None:
    """Service-role lookup of (config, credentials) for a sync job.

    Unlike get_integration(), this deliberately uses the service-role
    key on both tables — a background sync job has no logged-in user's
    access token to act as, and integration_credentials has zero grants
    for `authenticated` anyway (only service_role can ever read a bot
    token). Returns None if the org has no integration for this provider.
    """
    headers = {
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
    }
    integrations = requests.get(
        f"{SUPABASE_URL}/rest/v1/integrations",
        headers=headers,
        params={"org_id": f"eq.{org_id}", "provider_type": f"eq.{provider_type}", "select": "*"},
        timeout=10,
    )
    integrations.raise_for_status()
    rows = integrations.json()
    if not rows:
        return None
    integration = rows[0]

    creds = requests.get(
        f"{SUPABASE_URL}/rest/v1/integration_credentials",
        headers=headers,
        params={"integration_id": f"eq.{integration['id']}", "select": "credentials"},
        timeout=10,
    )
    creds.raise_for_status()
    cred_rows = creds.json()
    if not cred_rows:
        return None
    return integration["config"], cred_rows[0]["credentials"]


def get_integration(user_access_token: str, org_id: str, provider_type: str) -> dict | None:
    """Read back the non-secret config for the caller's org (RLS-scoped)."""
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/integrations",
        headers={
            "apikey": SUPABASE_PUBLISHABLE_KEY,
            "Authorization": f"Bearer {user_access_token}",
        },
        params={"org_id": f"eq.{org_id}", "provider_type": f"eq.{provider_type}", "select": "*"},
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None
