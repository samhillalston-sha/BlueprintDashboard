"""Find-or-create player lookups, shared by the one-off migration script
and the recurring Slack sync job."""

from app.supabase_rest import SERVICE_HEADERS, service_rest


def player_id_for_slack_name(org_id: str, slack_name: str, cache: dict) -> int:
    """Find-or-create a player row by Slack display name, scoped to the org.

    Mirrors app/db.py's player_for_slack_name: posters not on the roster
    still get stored (as unrostered), matched by slack_name OR name.
    """
    if slack_name in cache:
        return cache[slack_name]
    existing = service_rest(
        "GET", "players",
        params={"org_id": f"eq.{org_id}",
                "or": f"(slack_name.eq.{slack_name},name.eq.{slack_name})",
                "select": "id"},
    ).json()
    if existing:
        cache[slack_name] = existing[0]["id"]
        return existing[0]["id"]
    created = service_rest(
        "POST", "players",
        json={"org_id": org_id, "name": slack_name, "slack_name": slack_name,
              "is_rostered": False},
        headers={**SERVICE_HEADERS, "Prefer": "return=representation"},
    ).json()
    cache[slack_name] = created[0]["id"]
    return created[0]["id"]
