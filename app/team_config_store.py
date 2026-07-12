"""Look up an org's classification rules, shared by every script that
turns raw messages into classified posts (the recurring sync job and the
one-off historical migration alike)."""

from app.classify import CARDIO_CREDIT_CATEGORIES, KEYWORDS, REQUIRED_CATEGORIES, Classifier
from app.supabase_rest import service_rest


def classifier_for_org(org_id: str) -> Classifier:
    """The org's own team_config, falling back to Blueprint's default
    rules if the org hasn't been given one yet (no per-team config UI
    exists as of M3 — see docs/SCALABILITY_PLAN.md)."""
    rows = service_rest(
        "GET", "team_config",
        params={"org_id": f"eq.{org_id}", "select": "*"},
    ).json()
    if not rows:
        print(f"No team_config for org {org_id} — using Blueprint's default rules.")
        return Classifier(categories=KEYWORDS, required_categories=REQUIRED_CATEGORIES,
                           credit_categories=CARDIO_CREDIT_CATEGORIES)
    return Classifier.from_team_config(rows[0])
