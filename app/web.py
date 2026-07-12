"""Milestone 4: the web dashboard.

A small Flask web app (Flask = a Python library that turns functions into
web pages). One page: the roster, one row per player, one column per week,
with throwing/cardio check chips in every cell.

Run it two ways:
  - as a live website:      python milestone4_dashboard.py --serve
  - as a one-off HTML file: python milestone4_dashboard.py
"""

import json
import os
import secrets
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, g, redirect, render_template, request, session, url_for

from app import config_store, db, onboarding_store
from app.messaging import store as integration_store
from app.messaging.slack_provider import SlackOAuthError, SlackProvider
from app.supabase_auth import AuthError, login_required, sign_in, sign_up

POSITION_ORDER = ["O Handler", "O Cutter", "D Handler", "D Cutter", "Utility / Misc"]

app = Flask(__name__, template_folder=str(Path(__file__).parent.parent / "templates"))
# Falls back to a random key if unset, which just means sessions reset on
# every restart — fine for now, but set FLASK_SECRET_KEY before this is
# used by more than one person at a time.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def week_label(week_start: str) -> str:
    """'2026-06-29' -> 'JUN 29 – JUL 05'."""
    start = date.fromisoformat(week_start)
    end = start + timedelta(days=6)
    if start.month == end.month:
        return f"{MONTHS[start.month - 1]} {start.day:02d}–{end.day:02d}"
    return f"{MONTHS[start.month - 1]} {start.day:02d} – {MONTHS[end.month - 1]} {end.day:02d}"


def season_weeks(conn, today: date) -> list:
    """Every Monday from the first post to this week, with no gaps."""
    posted_weeks = db.all_weeks(conn)
    if not posted_weeks:
        return []
    week = date.fromisoformat(min(posted_weeks))
    current = db.week_start_of(today)
    weeks = []
    while week <= current:
        weeks.append(week.isoformat())
        week += timedelta(days=7)
    return weeks


def build_row(name: str, player_weeks: dict, injuries: list, weeks: list,
              current_week: str, today: date) -> dict:
    """Build one player's dashboard row: a cell per week plus a season score.

    A box counts as satisfied if the player posted it OR an injury excuses
    them from it that week.
    """
    cells = []
    complete_count = 0
    ended_count = 0
    for week in weeks:
        status = player_weeks.get(week)
        ex_throwing, ex_cardio, note = db.injury_excuses_for_week(injuries, week)
        ended = date.fromisoformat(week) + timedelta(days=7) <= today
        cell = {
            "throwing": bool(status and status["throwing"]),
            "cardio": bool(status and status["cardio"]),
            "ex_throwing": ex_throwing,
            "ex_cardio": ex_cardio,
            "note": note,
            "silent": status is None and not (ex_throwing or ex_cardio),
            "current": week == current_week,
        }
        throwing_ok = cell["throwing"] or ex_throwing
        cardio_ok = cell["cardio"] or ex_cardio
        if ended:
            ended_count += 1
            if throwing_ok and cardio_ok:
                complete_count += 1
        cell["full"] = throwing_ok and cardio_ok
        cells.append(cell)
    return {"name": name, "cells": cells, "score": f"{complete_count}/{ended_count}"}


def build_context(today: date | None = None) -> dict:
    """Gather everything the dashboard page needs from the database."""
    today = today or date.today()
    conn = db.connect()
    weeks = season_weeks(conn, today)
    compliance_all = db.weekly_compliance(conn, rostered_only=False)
    injuries = db.injuries_by_player(conn)
    current_week = db.week_start_of(today).isoformat()

    def row_for(name: str) -> dict:
        return build_row(name, compliance_all.get(name, {}),
                         injuries.get(name, []), weeks, current_week, today)

    # Rostered players, grouped by position.
    groups = []
    rostered_names = set()
    for position in POSITION_ORDER:
        players = [p for p in db.roster_players(conn) if p["position"] == position]
        if not players:
            continue
        rostered_names.update(p["name"] for p in players)
        groups.append({
            "position": position,
            "rows": [row_for(p["name"]) for p in players],
            "practice": False,
        })

    # Practice players / unrostered posters — same rows, hidden by default.
    practice_names = db.unrostered_posters(conn)
    practice_group = {
        "position": "Practice players / unrostered",
        "rows": [row_for(name) for name in practice_names],
        "practice": True,
    }

    # Headline numbers for the most recent COMPLETED week (rostered only).
    ended_weeks = [w for w in weeks
                   if date.fromisoformat(w) + timedelta(days=7) <= today]
    stats = {"week_label": "—", "full": 0, "partial": 0, "silent": 0, "total": 0}
    if ended_weeks:
        last_week = max(ended_weeks)
        week_index = weeks.index(last_week)
        stats["week_label"] = week_label(last_week)
        for group in groups:
            for row in group["rows"]:
                cell = row["cells"][week_index]
                stats["total"] += 1
                if cell["full"]:
                    stats["full"] += 1
                elif cell["silent"]:
                    stats["silent"] += 1
                else:
                    stats["partial"] += 1

    context = {
        "groups": groups + ([practice_group] if practice_group["rows"] else []),
        "weeks": weeks,
        "week_labels": [week_label(w) for w in weeks],
        "current_week": current_week,
        "stats": stats,
        "today": today.strftime("%Y-%m-%d"),
    }
    conn.close()
    return context


@app.route("/")
def dashboard():
    return render_template("dashboard.html", **build_context())


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", error=None)
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    try:
        tokens = sign_in(email, password)
    except AuthError as exc:
        return render_template("login.html", error=exc.message), 401
    session["access_token"] = tokens["access_token"]
    return redirect(request.args.get("next") or url_for("account"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html", error=None, message=None)
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    try:
        result = sign_up(email, password)
    except AuthError as exc:
        return render_template("signup.html", error=exc.message, message=None), 400
    if result.get("access_token"):
        session["access_token"] = result["access_token"]
        return redirect(url_for("join"))
    return render_template("signup.html", error=None,
                            message="Account created — check your email to confirm it, then log in.")


@app.route("/join", methods=["GET", "POST"])
@login_required
def join():
    if g.user["org_id"]:
        return redirect(url_for("account"))
    if request.method == "GET":
        return render_template("join.html", error=None)
    code = request.form.get("code", "").strip().upper()
    org = onboarding_store.redeem_join_code(g.user["id"], code)
    if org is None:
        return render_template(
            "join.html",
            error="That code didn't match a team, or your account is already linked to one.",
        ), 400
    return redirect(url_for("account"))


@app.route("/settings/join-code", methods=["GET", "POST"])
@login_required
def join_code_settings():
    if g.user["role"] != "coach":
        return "Only a coach can manage the join code.", 403
    if request.method == "POST":
        code = onboarding_store.generate_join_code(session["access_token"], g.user["org_id"])
    else:
        org = onboarding_store.get_org(session["access_token"], g.user["org_id"])
        code = org["join_code"] if org else None
    return render_template("join_code.html", code=code)


@app.route("/settings/config", methods=["GET", "POST"])
@login_required
def team_config_settings():
    if g.user["role"] != "coach":
        return "Only a coach can edit team config.", 403
    access_token = session["access_token"]
    org_id = g.user["org_id"]

    if request.method == "POST":
        raw_config = {
            "org_id": org_id,
            "categories_json": request.form.get("categories_json", "[]"),
            "required_categories": request.form.get("required_categories", ""),
            "cardio_credit_categories": request.form.get("cardio_credit_categories", ""),
        }
        try:
            categories = json.loads(raw_config["categories_json"])
        except json.JSONDecodeError as exc:
            return render_template("team_config.html", config=raw_config,
                                    error=f"Categories isn't valid JSON: {exc}"), 400
        required = [c.strip() for c in raw_config["required_categories"].split(",") if c.strip()]
        credit = [c.strip() for c in raw_config["cardio_credit_categories"].split(",") if c.strip()]
        try:
            config_store.save_team_config(access_token, org_id, categories, required, credit)
        except ValueError as exc:
            return render_template("team_config.html", config=raw_config, error=str(exc)), 400
        return redirect(url_for("team_config_settings"))

    config = config_store.get_team_config(access_token, org_id)
    view_config = {
        "categories_json": json.dumps(config["categories"], indent=2) if config else "[]",
        "required_categories": ", ".join(config["required_categories"]) if config else "",
        "cardio_credit_categories": ", ".join(config["cardio_credit_categories"]) if config else "",
    }
    return render_template("team_config.html", config=view_config, error=None)


@app.route("/account")
@login_required
def account():
    return render_template("account.html", user=g.user)


@app.route("/integrations/slack/install")
@login_required
def slack_install():
    if g.user["role"] != "coach":
        return "Only a coach can connect Slack.", 403
    state = secrets.token_urlsafe(24)
    session["slack_oauth_state"] = state
    provider = SlackProvider()
    redirect_uri = url_for("slack_callback", _external=True)
    return redirect(provider.install_url(redirect_uri, state))


@app.route("/integrations/slack/callback")
@login_required
def slack_callback():
    expected_state = session.pop("slack_oauth_state", None)
    if not expected_state or request.args.get("state") != expected_state:
        return "Invalid or expired OAuth state — start the install again.", 400
    code = request.args.get("code")
    if not code:
        return f"Slack authorization failed: {request.args.get('error', 'no code returned')}", 400

    provider = SlackProvider()
    redirect_uri = url_for("slack_callback", _external=True)
    try:
        result = provider.exchange_code(code, redirect_uri)
    except SlackOAuthError as exc:
        return f"Slack authorization failed: {exc}", 400

    access_token = session["access_token"]
    integration_id = integration_store.save_integration(
        access_token, g.user["org_id"], "slack", result.config, g.user["id"],
    )
    integration_store.save_credentials(integration_id, result.credentials)
    return redirect(url_for("slack_channel"))


@app.route("/integrations/slack/channel", methods=["GET", "POST"])
@login_required
def slack_channel():
    if g.user["role"] != "coach":
        return "Only a coach can configure Slack.", 403

    existing = integration_store.get_integration_for_sync(g.user["org_id"], "slack")
    if existing is None:
        return redirect(url_for("slack_install"))
    config, credentials = existing

    if request.method == "GET":
        return render_template("slack_channel.html", error=None, config=config)

    channel_name = request.form.get("channel_name", "").strip().lstrip("#")
    channel = SlackProvider().resolve_channel(credentials, channel_name)
    if channel is None:
        error = (f'No public channel named "{channel_name}" found. Make sure the '
                  f"bot's been invited to it in Slack (type /invite @Blueprint Dashboard "
                  f"Tracker in that channel) and the name is spelled right, with no #.")
        return render_template("slack_channel.html", error=error, config=config), 400

    config["channel_id"] = channel["id"]
    config["channel_name"] = channel["name"]
    integration_store.save_integration(
        session["access_token"], g.user["org_id"], "slack", config, g.user["id"],
    )
    return redirect(url_for("account"))


def render_static(output_path: Path) -> Path:
    """Save the dashboard as a single HTML file (for sharing/previewing)."""
    with app.test_client() as client:
        html = client.get("/").get_data(as_text=True)
    output_path.write_text(html)
    return output_path
