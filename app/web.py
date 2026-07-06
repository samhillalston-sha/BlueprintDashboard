"""Milestone 4: the web dashboard.

A small Flask web app (Flask = a Python library that turns functions into
web pages). One page: the roster, one row per player, one column per week,
with throwing/cardio check chips in every cell.

Run it two ways:
  - as a live website:      python milestone4_dashboard.py --serve
  - as a one-off HTML file: python milestone4_dashboard.py
"""

from datetime import date, timedelta
from pathlib import Path

from flask import Flask, render_template

from app import db

POSITION_ORDER = ["O Handler", "O Cutter", "D Handler", "D Cutter", "Utility / Misc"]

app = Flask(__name__, template_folder=str(Path(__file__).parent.parent / "templates"))

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


def build_context(today: date | None = None) -> dict:
    """Gather everything the dashboard page needs from the database."""
    today = today or date.today()
    conn = db.connect()
    weeks = season_weeks(conn, today)
    compliance = db.weekly_compliance(conn)
    current_week = db.week_start_of(today).isoformat()

    # Group rostered players by position, building each row's cells.
    groups = []
    for position in POSITION_ORDER:
        players = [p for p in db.roster_players(conn) if p["position"] == position]
        if not players:
            continue
        rows = []
        for player in players:
            player_weeks = compliance.get(player["name"], {})
            cells = []
            complete_count = 0
            ended_count = 0
            for week in weeks:
                status = player_weeks.get(week)
                ended = date.fromisoformat(week) + timedelta(days=7) <= today
                if ended:
                    ended_count += 1
                cell = {
                    "throwing": bool(status and status["throwing"]),
                    "cardio": bool(status and status["cardio"]),
                    "silent": status is None,
                    "current": week == current_week,
                }
                if ended and cell["throwing"] and cell["cardio"]:
                    complete_count += 1
                cells.append(cell)
            rows.append({
                "name": player["name"],
                "cells": cells,
                "score": f"{complete_count}/{ended_count}",
            })
        groups.append({"position": position, "rows": rows})

    # Headline numbers for the most recent COMPLETED week.
    ended_weeks = [w for w in weeks
                   if date.fromisoformat(w) + timedelta(days=7) <= today]
    stats = {"week_label": "—", "full": 0, "partial": 0, "silent": 0, "total": 0}
    if ended_weeks:
        last_week = max(ended_weeks)
        stats["week_label"] = week_label(last_week)
        for group in groups:
            for row in group["rows"]:
                status = compliance.get(row["name"], {}).get(last_week)
                stats["total"] += 1
                if status is None:
                    stats["silent"] += 1
                elif status["throwing"] and status["cardio"]:
                    stats["full"] += 1
                else:
                    stats["partial"] += 1

    context = {
        "groups": groups,
        "weeks": weeks,
        "week_labels": [week_label(w) for w in weeks],
        "current_week": current_week,
        "stats": stats,
        "unrostered": db.unrostered_posters(conn),
        "today": today.strftime("%Y-%m-%d"),
    }
    conn.close()
    return context


@app.route("/")
def dashboard():
    return render_template("dashboard.html", **build_context())


def render_static(output_path: Path) -> Path:
    """Save the dashboard as a single HTML file (for sharing/previewing)."""
    with app.test_client() as client:
        html = client.get("/").get_data(as_text=True)
    output_path.write_text(html)
    return output_path
