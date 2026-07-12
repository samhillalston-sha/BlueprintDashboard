"""M1: Supabase Auth wiring — sign-in, JWT verification, and org/role lookup.

This is deliberately independent of the existing SQLite-backed dashboard
(app/web.py, app/db.py). It talks to Supabase over HTTPS only: the Auth
API to sign a user in, and PostgREST (via the user's own access token,
so Row Level Security scopes the result) to read their profile. Nothing
here reaches into Postgres directly — see docs/SCALABILITY_PLAN.md for
why (raw Postgres connections aren't reachable from the dev sandbox).
"""

import functools
import os

import jwt
import requests
from dotenv import load_dotenv
from flask import g, redirect, request, session, url_for

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
SUPABASE_JWKS_URL = os.environ.get("SUPABASE_JWKS_URL", "")

_jwk_client: jwt.PyJWKClient | None = None


def _jwks_client() -> jwt.PyJWKClient:
    """Lazily build the JWKS client (fetches/caches Supabase's signing keys)."""
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = jwt.PyJWKClient(SUPABASE_JWKS_URL)
    return _jwk_client


class AuthError(Exception):
    """A login attempt or token check failed; .message is safe to show a user."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def sign_up(email: str, password: str) -> dict:
    """Self-service account creation (athletes joining via a code — coaches
    are still invited by Sam manually, per the product decision that org
    creation itself stays manual/non-self-serve for now).

    Returns the Supabase signup response as-is: it includes an
    access_token only if the project's email-confirmation setting is
    off; otherwise the caller needs to tell the user to check their
    email and log in afterward. Raises AuthError on validation failure
    (weak password, already-registered email, etc).
    """
    response = requests.post(
        f"{SUPABASE_URL}/auth/v1/signup",
        headers={"apikey": SUPABASE_PUBLISHABLE_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=10,
    )
    if response.status_code >= 400:
        body = response.json()
        raise AuthError(body.get("error_description") or body.get("msg") or "Could not create account.")
    return response.json()


def sign_in(email: str, password: str) -> dict:
    """Exchange email/password for a Supabase session (access + refresh token).

    Raises AuthError with a user-facing message on bad credentials.
    """
    response = requests.post(
        f"{SUPABASE_URL}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": SUPABASE_PUBLISHABLE_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=10,
    )
    if response.status_code != 200:
        raise AuthError("Incorrect email or password.")
    return response.json()


def verify_access_token(access_token: str) -> dict:
    """Verify a Supabase-issued JWT's signature/expiry and return its claims.

    Raises AuthError if the token is missing, expired, or invalid.
    """
    if not access_token:
        raise AuthError("Not signed in.")
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(access_token)
        return jwt.decode(
            access_token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise AuthError("Your session has expired — please sign in again.") from exc


def fetch_profile(access_token: str, user_id: str) -> dict | None:
    """Look up a signed-in user's profile (org_id, role, display_name).

    Uses the user's own access token against PostgREST, so RLS naturally
    limits this to their own row — no separate authorization check needed
    here beyond "is this a valid token for this user".
    """
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        params={"id": f"eq.{user_id}", "select": "*"},
        headers={
            "apikey": SUPABASE_PUBLISHABLE_KEY,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def current_user() -> dict | None:
    """The signed-in user's identity + org/role, or None if not signed in.

    Verifies the token fresh on every call (no caching across requests) —
    this is a low-traffic internal dashboard, not worth the complexity of
    a refresh-token flow yet.
    """
    access_token = session.get("access_token")
    if not access_token:
        return None
    try:
        claims = verify_access_token(access_token)
    except AuthError:
        return None
    profile = fetch_profile(access_token, claims["sub"])
    return {
        "id": claims["sub"],
        "email": claims.get("email"),
        "org_id": profile["org_id"] if profile else None,
        "role": profile["role"] if profile else None,
        "display_name": profile["display_name"] if profile else None,
    }


def login_required(view):
    """Route decorator: redirect to /login unless there's a valid session."""

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return redirect(url_for("login", next=request.path))
        g.user = user
        return view(*args, **kwargs)

    return wrapped
