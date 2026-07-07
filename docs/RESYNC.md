# Full Slack re-sync — runbook

Instructions for Claude (in any session with the Slack connector enabled)
to rebuild the dashboard's data from the real channel. The commissioner
(Sam) just needs to say: **"do the full re-sync"**.

## What to pull

- Channel: **#doyoulikefitness**, ID `C0B7Y6NVDKK` (workspace blueprint2026)
- Every message from **2026-06-08** (season start) to now — paginate with
  the Slack connector's read-channel tool until exhausted. Use the
  **detailed** response format: it's the one that includes each message's
  `Message TS:` and `Files:` lines.
- For each message keep: the Slack **ts** (e.g. `1781563087.985029`, the
  stable message ID), date (EDT), author's display name, text, and whether
  files/images are attached
- Skip: channel-join events, thread replies (top-level posts only for now)
- Also pull the **channel member list** (for roster gaps / lurkers)

## Where it goes

1. Write all messages to `data/messages_sample.json` as a JSON array of
   `{"ts": "<slack ts>", "date": "YYYY-MM-DD", "user": "<slack display
   name>", "text": "...", "has_photo": true/false}` (data/ is gitignored —
   team messages never go to GitHub; the repo is public). Keep it ordered
   oldest-first; `ts` must be unique.
2. Run `python milestone3_load_db.py` — rebuilds blueprint.db from
   scratch: seeds `roster.json`, classifies every post (app/classify.py),
   applies `data/injuries.json` and `appearances.json`, prints the
   compliance grid
3. Run `python milestone4_dashboard.py` — regenerates dashboard.html
4. Send Sam the refreshed dashboard.html + a screenshot

## Appearance credit (who's pictured)

Being pictured in a teammate's throwing/cardio/combined selfie earns the
same box, so `appearances.json` (repo **root**, committed — unlike data/,
so the manual review survives a fresh container) maps
`{"<source ts>": {"reviewed": true, "players": ["<name>", ...]}}`.
milestone3 reads it and grants each listed player the source post's credit.
It's keyed by `ts`, so it keeps working across re-syncs. To (re)do the
review, run `python milestone6_review.py` and open http://localhost:8001 —
it steps through only the creditable photo posts and autosaves your ticks.
New tags won't appear on the dashboard until you re-run steps 2–3.

## Name mapping

Slack display names → roster names live in `roster.json` (`slack_name`
field). Posters not in roster.json are stored automatically as
practice players / unrostered — no action needed. If a NEW roster player
appears under an unexpected Slack name, add their `slack_name` to
roster.json.

## Setup notes (if running in a fresh container)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

The direct Slack API route (milestone1_check_slack.py + bot token in
.env) is blocked by the environment's network policy — use the Slack
*connector*, not the Python script, unless the network policy has been
opened for slack.com.
