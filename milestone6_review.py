"""Milestone 6: the appearance review tool.

A selfie can picture more than one player, and being *in* a throwing or cardio
photo counts for you exactly like posting it yourself. Image recognition isn't
reliable enough to hand out that credit, so this is a human-in-the-loop tool:
it walks you through the posts that could earn credit and lets you tick who else
is pictured. Your answers are saved to appearances.json, which milestone3 reads
back in to award the extra boxes.

Only posts classified throwing / cardio / combined are shown — appearing in a
strength or PT photo earns nobody a box, so there's nothing to review there.

Run it:
  python milestone6_review.py            # http://localhost:8001
Then open the URL, tick who's in each photo (use the "Open in Slack" button to
see the actual picture), and re-run  python milestone3_load_db.py  when done.
"""

import json
import re
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

from app.classify import classify

ROOT = Path(__file__).parent
DATA_FILE = ROOT / "data" / "messages_sample.json"
ROSTER_FILE = ROOT / "roster.json"
APPEARANCE_FILE = ROOT / "data" / "appearances.json"

CREDITABLE = {"throwing", "cardio", "combined"}

# For building "Open in Slack" deep links (workspace blueprint2026).
SLACK_WORKSPACE = "blueprint2026"
SLACK_CHANNEL = "C0B7Y6NVDKK"

app = Flask(__name__, template_folder=str(ROOT / "templates"))

_MENTION = re.compile(r"<@[^|>]+\|([^>]+)>")   # <@U123|Jane> -> @Jane
_LINK = re.compile(r"<([^|>]+)\|([^>]+)>")      # <url|label>  -> label


def humanize(text: str) -> str:
    """Turn Slack markup into something readable in the review UI."""
    text = _MENTION.sub(r"@\1", text)
    text = _LINK.sub(r"\2", text)
    return text.strip()


def slack_permalink(ts: str) -> str:
    return f"https://{SLACK_WORKSPACE}.slack.com/archives/{SLACK_CHANNEL}/p{ts.replace('.', '')}"


def load_candidates(messages: list) -> tuple:
    """The names you can tick for a photo: every rostered player plus everyone
    who has posted. Returns (candidates, slack_to_value) where a candidate is
    {"value","label","group"} and slack_to_value maps a Slack display name to
    the candidate value that represents that same person (so a poster can be
    matched and locked)."""
    roster = json.loads(ROSTER_FILE.read_text())["players"]
    candidates = []
    slack_to_value = {}
    seen = set()
    for p in roster:
        candidates.append({"value": p["name"], "label": p["name"], "group": p["position"]})
        seen.add(p["name"])
        if p.get("slack_name"):
            slack_to_value[p["slack_name"]] = p["name"]
    # Anyone who posts but isn't rostered — so practice players can get credit too.
    for m in messages:
        user = m["user"]
        value = slack_to_value.get(user, user)
        if value not in seen:
            candidates.append({"value": value, "label": user, "group": "Practice / unrostered"})
            seen.add(value)
            slack_to_value.setdefault(user, value)
    return candidates, slack_to_value


def review_posts() -> list:
    """The ordered list of creditable photo posts to review."""
    messages = json.loads(DATA_FILE.read_text())
    posts = []
    for m in messages:
        if not m.get("has_photo"):
            continue
        if classify(m["text"]).label not in CREDITABLE:
            continue
        posts.append(m)
    return posts


def load_appearances() -> dict:
    if APPEARANCE_FILE.exists():
        return json.loads(APPEARANCE_FILE.read_text())
    return {}


def save_appearances(data: dict) -> None:
    APPEARANCE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


@app.route("/")
def home():
    posts = review_posts()
    saved = load_appearances()
    # Jump to the first post you haven't reviewed yet.
    for i, post in enumerate(posts):
        if not saved.get(post["ts"], {}).get("reviewed"):
            return redirect(url_for("review", idx=i))
    return redirect(url_for("review", idx=0))


@app.route("/review/<int:idx>")
def review(idx: int):
    posts = review_posts()
    if not posts:
        return "No creditable photo posts found — run a re-sync first.", 404
    idx = max(0, min(idx, len(posts) - 1))
    post = posts[idx]
    messages = json.loads(DATA_FILE.read_text())
    candidates, slack_to_value = load_candidates(messages)
    saved = load_appearances()
    entry = saved.get(post["ts"], {})

    poster_value = slack_to_value.get(post["user"], post["user"])
    reviewed_count = sum(1 for p in posts if saved.get(p["ts"], {}).get("reviewed"))

    return render_template(
        "review.html",
        idx=idx,
        total=len(posts),
        reviewed_count=reviewed_count,
        post=post,
        text=humanize(post["text"]) or "(no caption)",
        label=classify(post["text"]).label,
        permalink=slack_permalink(post["ts"]),
        candidates=candidates,
        poster_value=poster_value,
        poster_label=post["user"],
        selected=set(entry.get("players", [])),
        is_reviewed=bool(entry.get("reviewed")),
        prev_idx=idx - 1 if idx > 0 else None,
        next_idx=idx + 1 if idx < len(posts) - 1 else None,
    )


@app.route("/api/save", methods=["POST"])
def api_save():
    payload = request.get_json(force=True)
    ts = payload["ts"]
    poster_value = payload.get("poster_value")
    # The poster always has their own credit; never store them as an appearance.
    players = [p for p in payload.get("players", []) if p != poster_value]
    saved = load_appearances()
    saved[ts] = {"reviewed": True, "players": players}
    save_appearances(saved)
    posts = review_posts()
    reviewed_count = sum(1 for p in posts if saved.get(p["ts"], {}).get("reviewed"))
    return jsonify(ok=True, reviewed_count=reviewed_count, total=len(posts))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8001, debug=False)
