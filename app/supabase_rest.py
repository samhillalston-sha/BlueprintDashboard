"""Shared service-role PostgREST helper for server-side scripts (bypasses RLS)."""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_HEADERS = {
    "apikey": os.environ.get("SUPABASE_SECRET_KEY", ""),
    "Authorization": f"Bearer {os.environ.get('SUPABASE_SECRET_KEY', '')}",
    "Content-Type": "application/json",
}


def service_rest(method: str, path: str, *, headers: dict | None = None, **kwargs) -> requests.Response:
    response = requests.request(method, f"{SUPABASE_URL}/rest/v1/{path}",
                                 headers=headers or SERVICE_HEADERS, timeout=15, **kwargs)
    response.raise_for_status()
    return response
