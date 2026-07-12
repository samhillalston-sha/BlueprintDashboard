"""M3: roster join flow — coach-generated join codes, athlete redemption.

Two different security contexts on purpose:
  - generate_join_code / get_org go through the coach's OWN access
    token — RLS + the join_code/name/slug column grant (see migration
    0005) already allow a coach to edit their own org, no service role
    needed.
  - redeem_join_code MUST use the service-role key: the redeeming user
    has no org yet, so their own token can't even see the organizations
    table (current_org_id() is null for them), and profiles.org_id/role
    are only settable via service role at all since 0005 — a client
    token can never set them directly, by design.
"""

import os
import secrets
import string

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")

CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_LENGTH = 8


def get_org(user_access_token: str, org_id: str) -> dict | None:
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/organizations",
        headers={"apikey": SUPABASE_PUBLISHABLE_KEY,
                 "Authorization": f"Bearer {user_access_token}"},
        params={"id": f"eq.{org_id}", "select": "*"},
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def generate_join_code(user_access_token: str, org_id: str) -> str:
    """Coach generates/regenerates their org's shareable join code."""
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    response = requests.patch(
        f"{SUPABASE_URL}/rest/v1/organizations",
        headers={
            "apikey": SUPABASE_PUBLISHABLE_KEY,
            "Authorization": f"Bearer {user_access_token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        params={"id": f"eq.{org_id}"},
        json={"join_code": code},
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        raise PermissionError("Could not set a join code — are you a coach of this org?")
    return rows[0]["join_code"]


def redeem_join_code(user_id: str, code: str) -> dict | None:
    """Look up the org by code and, only if the user has no org yet,
    assign org_id/role='athlete'. Returns the org row on success, None
    if the code doesn't match anything OR the user already belongs to
    an org (won't silently switch them)."""
    headers = {
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    lookup = requests.get(
        f"{SUPABASE_URL}/rest/v1/organizations",
        headers=headers,
        params={"join_code": f"eq.{code}", "select": "*"},
        timeout=10,
    )
    lookup.raise_for_status()
    rows = lookup.json()
    if not rows:
        return None
    org = rows[0]

    update = requests.patch(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers={**headers, "Prefer": "return=representation"},
        params={"id": f"eq.{user_id}", "org_id": "is.null"},
        json={"org_id": org["id"], "role": "athlete"},
        timeout=10,
    )
    update.raise_for_status()
    if not update.json():
        return None  # already belonged to an org — refused to overwrite it
    return org
