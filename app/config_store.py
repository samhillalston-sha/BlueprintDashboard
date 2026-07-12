"""M3: coach-facing team_config editing.

Goes through the coach's own access token throughout — RLS (org_id =
current_org_id() and is_coach()) already allows a coach to
select/insert/update their own org's team_config row, no service role
needed. See supabase/migrations/0001 (schema) and 0002 (RLS).
"""

import os

import requests
from dotenv import load_dotenv

from app.classify import Classifier

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")


def get_team_config(user_access_token: str, org_id: str) -> dict | None:
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/team_config",
        headers={"apikey": SUPABASE_PUBLISHABLE_KEY,
                 "Authorization": f"Bearer {user_access_token}"},
        params={"org_id": f"eq.{org_id}", "select": "*"},
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def save_team_config(user_access_token: str, org_id: str, categories: list,
                      required_categories: list, cardio_credit_categories: list) -> None:
    """Validate the proposed config actually builds a working Classifier
    before saving — never let a coach save something that would make
    sync_slack.py/migrate_to_supabase.py crash on the next run. Raises
    ValueError with a user-facing message if it doesn't validate."""
    if not isinstance(categories, list) or not categories:
        raise ValueError("Categories must be a non-empty list.")
    for entry in categories:
        if not isinstance(entry, dict) or "key" not in entry or "keywords" not in entry:
            raise ValueError('Each category needs at least a "key" and a "keywords" list.')

    category_keys = {c["key"] for c in categories}
    for key in required_categories:
        if key not in category_keys:
            raise ValueError(f'required_categories references unknown category "{key}".')
    for key in cardio_credit_categories:
        if key not in category_keys:
            raise ValueError(f'cardio_credit_categories references unknown category "{key}".')

    # Reuses Classifier's own validation (e.g. required_categories can't
    # be empty) instead of duplicating those rules here.
    Classifier(
        categories={c["key"]: c["keywords"] for c in categories},
        required_categories=required_categories,
        credit_categories=set(cardio_credit_categories),
    )

    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/team_config",
        headers={
            "apikey": SUPABASE_PUBLISHABLE_KEY,
            "Authorization": f"Bearer {user_access_token}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        params={"on_conflict": "org_id"},
        json={"org_id": org_id, "categories": categories,
              "required_categories": required_categories,
              "cardio_credit_categories": cardio_credit_categories},
        timeout=10,
    )
    response.raise_for_status()
