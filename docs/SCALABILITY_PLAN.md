# Scalability plan — turning Blueprint into a sellable multi-team SaaS

Context for Claude: this file is the compressed memory of a long planning
conversation with Sam. Read this fully before doing any work on the
scalability effort. Branch: `claude/fitness-dashboard-scalability-h4q7ac`.

## Vision

Turn this from a single-team personal dashboard into a product Sam can
sell to any sports team (not just football/frisbee) to track offseason
workout compliance. Two integration branches planned long-term: Slack
(build first) and a standalone web/mobile intake (later). Prove it out
on Slack only for now.

## Key product decisions (already made, don't re-litigate)

- **Multi-tenancy**: shared schema, every tenant table scoped by `org_id`,
  not separate instances per customer.
- **Target users**: any sports team, any sport. Workout categories and
  compliance rules must be fully custom per team, not hardcoded presets.
- **Auth + DB**: Supabase (Postgres + Auth). Use Supabase's Row Level
  Security to enforce tenant isolation at the DB layer, not just in app
  code — this is the single most important property to keep testing.
- **Roles (v1)**: Coach (admin over their org) and Athlete only. Parent
  view-only role is explicitly deferred to later.
- **Roster join flow**: coach's choice of invite-by-email/Slack OR a
  shareable join code. Build both.
- **Onboarding**: manual for now — Sam sets up each new team himself.
  No public self-serve signup UI in this phase.
- **Slack integration**: build the real "Add to Slack" OAuth install
  flow now (not manual bot-token copy/paste per customer), through a
  `MessagingProvider` interface designed to also support Discord (and
  other channels) later without rewriting core logic. Slack becomes just
  the first implementation of that interface.
- **Rules engine**: keep the existing free-text slang classification
  approach (see `app/classify.py`), but make the keyword/slang list and
  categories per-team configurable instead of hardcoded to one team's
  slang ("sprintos", "leggos", "mccarren", etc).
- **Billing**: Stripe, flat fee per team (not per-seat).
- **Cost target**: stay on free tiers as long as possible ($0/mo until
  there are paying teams) — Supabase free tier, free/hobby hosting tier,
  Stripe has no fixed fee.
- **Model choice for building this**: Sonnet 5 as the default coding
  model for the whole build (best cost/capability balance for this kind
  of well-trodden CRUD/auth/integration work); reach for Opus only for a
  focused pass on something genuinely hard (e.g. a subtle RLS bug), not
  as the default.

## Current app state (as of the original architecture audit)

Very early-stage: Flask app (`app/web.py`) + raw `sqlite3` (`app/db.py`),
no ORM, no auth, no users/teams concept. Tables: `players`, `injuries`,
`posts`, all implicitly scoped to one team via `roster.json` (hardcoded
real names) and one Slack channel/bot token in `.env`. No Dockerfile, no
CI, no migrations tooling, no tests. `templates/dashboard.html` was
missing from the repo entirely at audit time.

## Milestone plan

Ordering rationale: most foundational + highest-uncertainty work first
(data model/auth, then the Slack OAuth integration since external APIs
are the biggest source of surprises), product-facing config next, billing
only once there's a real product to gate, ops hardening last since it'd
otherwise need redoing every time the schema changes.

- **M1 — Multi-tenant foundation** (IN PROGRESS, see status below):
  `organizations`, `users`, `team_config` tables; `org_id` added to
  `players`/`posts`/`injuries`; migrate off SQLite to Supabase Postgres;
  RLS policies for tenant isolation; Supabase Auth wired into Flask.
  Test: two fake orgs, assert cross-org access is blocked by RLS. Also
  manually verify Sam's real team data survived the migration.
- **M2 — Integration abstraction + Slack OAuth**: `MessagingProvider`
  interface + `integrations` table (`org_id`, `provider_type`,
  `credentials`, `config`); `SlackProvider` implementing it via the real
  Slack OAuth "Add to Slack" install flow.
- **M3 — Roster & per-team rules config**: coach onboarding UI (create
  org, invite athletes or generate join code); per-team config UI for
  keyword list / categories / compliance rules, replacing hardcoded
  `classify.py` logic.
- **M4 — Billing**: Stripe flat-fee subscription per org, checkout +
  webhook handling, gate access on subscription status.
- **M5 — Ops hardening**: Dockerfile, migrations tooling, free-tier
  hosting deploy, basic CI, error monitoring.

Test plan for every milestone follows the same shape: automated tests
proving the specific new mechanism works in isolation (e.g. RLS policy
tests, rules-engine tests with two different configs, Stripe webhook
handling in test mode), plus a manual end-to-end dry run creating a
*second, independent* test org and confirming it doesn't collide with
the first. That "does a second org work independently" check is the one
property to keep re-verifying at every milestone — it's the whole point
of the product.

## M1 status / where we left off

Supabase project created: `qcekzlgdqkycldmitmun.supabase.co`.
`.env` already populated locally (gitignored, not in this file on
purpose) with `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`,
`SUPABASE_SECRET_KEY`, `SUPABASE_JWKS_URL`, `DATABASE_URL`.

**Important**: `.env` does NOT survive a fresh session/container (it's
gitignored by design, and each new session clones the repo fresh). If
you're starting a new session to continue this work, ask Sam to
re-paste those same values — he has them saved from the prior session.

Network blocker from the previous session is resolved and confirmed
permanent, not worth re-testing every session: Full network access
unblocks HTTPS to `*.supabase.co` (REST/Auth APIs work fine), but raw
Postgres (port 5432, including the IPv4 connection pooler on 6543) is
still blocked by the proxy — confirmed by a raw TCP connect timeout, not
just a DNS/config issue. Don't attempt a direct psql/psycopg2
connection again. Workflow going forward: schema/RLS/grant changes are
written as numbered SQL files in `supabase/migrations/` and Sam pastes
them into the Supabase dashboard's SQL Editor; everything else (app
runtime, data migration, testing) goes through the HTTPS REST/Auth APIs
using `curl` or a Python HTTP client — no `supabase-py`/`psycopg2`
installed in the sandbox, and none needed so far.

**M1 is fully complete as of this session — all 6 tasks done.** Next
session should start on M2 (integration abstraction + Slack OAuth) per
the milestone plan, unless Sam redirects.

Task list (recreated via TaskCreate this session — IDs won't carry over
to a new session, recreate if useful):
1. Design multi-tenant schema (organizations, users, team_config, org_id FKs) — DONE
2. Write RLS policies for tenant isolation — DONE
3. Migrate existing SQLite data to Postgres/Supabase — DONE, see below
4. Wire Supabase Auth into Flask app — DONE, see below
5. Test tenant isolation with two fake orgs — DONE, see below
6. Manual verification against real team data — DONE, see below

### Task 1 + 2 — done, schema is live

Three migration files exist and have all been run successfully against
the live Supabase project (Sam pasted them into the SQL Editor):
- `supabase/migrations/0001_multi_tenant_foundation.sql` — `organizations`,
  `profiles` (1:1 with `auth.users`, auto-created via an
  `on_auth_user_created` trigger, `org_id`/`role` start null and get
  filled in during onboarding), `team_config` (per-org JSONB
  categories/keywords/rules, replacing hardcoded `app/classify.py`), and
  `players`/`injuries`/`posts` with `org_id` denormalized onto every row.
- `supabase/migrations/0002_row_level_security.sql` — RLS on all six
  tables via two `SECURITY DEFINER` helpers (`current_org_id()`,
  `is_coach()`); reads scoped to the caller's org, writes restricted to
  the coach role (the Slack sync job will keep writing through the
  service-role key, which bypasses RLS, same pattern as the SQLite
  version's ingestion script).
- `supabase/migrations/0003_grants.sql` — **required extra step**: tables
  created via the SQL Editor did NOT automatically get `service_role`/
  `authenticated` grants on this project (got 42501 permission-denied on
  every table until this ran). If a future migration adds a new table,
  remember to grant it too — don't assume Supabase does this by default.

### Task 5 — done, RLS verified against real auth tokens

Created two fake orgs + two fake `auth.users` (via the Auth admin API,
`email_confirm: true` so no email step needed) + one player each,
assigned org/role on their profiles, then **signed in as each fake user
via the real password grant** (`/auth/v1/token?grant_type=password`) to
get actual JWTs — not just service-role testing. Confirmed with those
JWTs against PostgREST:
- Org Alpha's user sees only Alpha's player/org/profile rows; same for Beta.
- Explicitly filtering for the other org's `org_id` returns empty, not
  an error and not the row.
- Cross-org INSERT gets an explicit 403 (`new row violates row-level
  security policy`).
- Cross-org UPDATE/DELETE by row id silently affect 0 rows (verified by
  re-reading the target row from the other org's own token afterward —
  data was untouched, not silently corrupted).

All test orgs/users/rows were deleted afterward; all six tables were
confirmed empty again. This is the "two independent orgs" check the
plan calls out as worth re-verifying at every milestone — it passed
cleanly for M1's schema. Re-run something like this again after task 4
(Auth wired into Flask) and again at M2/M3 as the schema grows.

### Task 3 — done: Blueprint's real season is now the M1 proving ground

Sam initially stopped an auto-started Slack pull (pulling real data into
unproven infra before auth existed was premature) — fake-org testing
(task 5) went first instead. Once that passed and auth (task 4) was
wired up, Sam explicitly approved using Blueprint's own real 2026 season
as the test case for proving out the multi-tenant migration, rather than
building a second throwaway synthetic dataset.

What exists now, all live in Supabase under one real org:
- Org **"Blueprint 2026"** (slug `blueprint-2026`) created via service role.
- Sam invited as coach via the Auth admin `/invite` endpoint (sends a
  real email so he sets his own password — nobody generated one for
  him); his `profiles` row has `org_id`/`role='coach'` set immediately
  (doesn't need to wait for him to accept the invite).
- `team_config` seeded **programmatically from `app/classify.py`'s
  `KEYWORDS` dict** (not hand-retyped, so it can't drift):
  `required_categories: ["throwing","cardio"]`,
  `cardio_credit_categories: ["cardio","ultimate","sports"]`, matching
  `Classification.label`'s existing rules exactly.
- All 26 roster entries from `roster.json` loaded into `players`.
- Full season pulled from Slack via a subagent (paginated
  `mcp__Slack__slack_read_channel`, `response_format: "detailed"` — note
  `"concise"` silently drops file-attachment info, breaking `has_photo`;
  re-pulled once already, use `"detailed"` from the start next time) —
  330 top-level messages, 2026-06-08 through 2026-07-10, no gaps, every
  known roster `slack_name` seen posting. Written to
  `data/messages_sample.json` (gitignored, as always).
- `migrate_to_supabase.py` (new script, checked in) — the Postgres/REST
  equivalent of `milestone3_load_db.py`: classifies each message with
  the existing `app/classify.py`, finds-or-creates unrostered posters by
  Slack name, batch-inserts into `posts`. Run: `.venv/bin/python
  migrate_to_supabase.py <org_id>`. Result: 330 posts inserted, 39 total
  players (26 rostered + 13 unrostered who actually posted), 36 with at
  least one post. No `data/injuries.json` existed this session, so
  injuries weren't migrated — the script supports it (mirrors
  `add_injury`) whenever that file shows up.

### Task 4 — done, auth mechanism proven, NOT wired into the real dashboard

Deliberately scoped narrow per Sam's call: build the login mechanism as
independent, testable code and leave the existing `/` route (Sam's real,
currently-in-use dashboard, still reading local SQLite) completely
untouched. Don't gate `/` behind login or switch its data source until
Sam asks for it.

What exists now:
- `app/supabase_auth.py` — `sign_in()` (Auth password grant),
  `verify_access_token()` (local JWT verification via `PyJWKClient` +
  `SUPABASE_JWKS_URL`, algorithms ES256/RS256, audience "authenticated"),
  `fetch_profile()` (reads `profiles` via PostgREST **using the user's
  own access token**, so RLS — not app code — is what scopes it to their
  own row), `current_user()`, and a `login_required` decorator.
- New Flask routes in `app/web.py`: `GET/POST /login`, `POST /logout`,
  `GET /account` (a debug page showing the resolved email/org_id/role —
  this is the provable artifact for this task, not a real feature page).
  `app.secret_key` comes from `FLASK_SECRET_KEY` (added to `.env`/
  `.env.example`), falls back to a random key (session resets on
  restart) if unset.
- Session holds only the Supabase `access_token`; no refresh-token flow
  yet (token re-verified fresh on every request, ~1hr Supabase default
  expiry, fine for this traffic level — revisit if that's annoying).

Sandbox note: the system-installed `cryptography` package is broken here
(`_cffi_backend` missing, Rust panic on import) — PyJWT's signature
verification will silently fail to even import in the bare system
Python. Fixed by using a project venv (`python3 -m venv .venv && .venv/bin/pip
install -r requirements.txt`) instead of system Python; a fresh
`cryptography` wheel installs cleanly. Use `.venv/bin/python` /
`.venv/bin/flask` for anything touching `app/supabase_auth.py`, including
just running the dashboard.

Verified end-to-end against a real fake org+user (created via Auth admin
API, cleaned up after): unauthenticated `/account` redirects to
`/login?next=/account`; wrong password → 401 with on-page error;
correct password → session cookie set, redirects to `/account` showing
the right org_id/role (pulled through the real RLS-scoped profile
lookup, not hardcoded); `/logout` clears the session; a garbage/invalid
token is rejected by `verify_access_token`.

Sam should have a real invite email from Supabase Auth by now for
`sam.hill.alston@gmail.com` (Blueprint 2026 org) — once he sets a
password via that link, `/login` + `/account` should show his real
coach identity. Nobody has tested that specific end-to-end path yet
(only the throwaway fake-user path was tested) — worth Sam confirming
himself, or a future session re-verifying if he hasn't.

Not done / open for later: refresh-token handling, `/signup` (manual
onboarding only per the product decision, so maybe never needed as a
public route), rate limiting on `/login`, and — the big one — actually
pointing a real route's data at Postgres instead of SQLite (still
nobody's touched `/`, on purpose).

### Task 6 — done: Supabase data verified byte-identical to trusted SQLite output

Strategy: rebuild the exact same weekly compliance grid two ways from
the identical `data/messages_sample.json` + `roster.json` — once through
the old, trusted `milestone3_load_db.py` → SQLite → `app/db.py`
pipeline, once by re-fetching what actually landed in Supabase and
reimplementing `weekly_compliance`'s grouping logic in Python — and diff
them. First attempt mismatched (an off-by-omission bug in the
verification script itself: it skipped creating a week entry for posts
labeled `strength/recovery`/`unclassified`, showing `--` "no post" where
it should've shown `··` "posted, neither box ticked" — a bug in the
check, not the migration). Fixed, re-ran: **byte-identical match**, 330
posts, 26 rostered players, 5 weeks, both grids character-for-character
equal.

Also spot-checked that RLS/grants protect the real org, not just the
earlier throwaway test orgs: an unauthenticated request (anon key, no
user token) for Blueprint's `posts` gets an outright 403 permission
denial (not just an empty RLS-filtered result — `anon` has zero table
grants by design, see task-1/2 notes on `0003_grants.sql`).

The verification script itself was scratch/throwaway (written to the
session scratchpad, not checked into the repo) — if this needs
re-running later, it's a ~70 line script, quick to recreate: pull
`players`+`posts` for the org from PostgREST, regroup by
`(player_name, week_start)` exactly like `app/db.py`'s
`weekly_compliance` SQL does (every post creates an entry, not just
throwing/cardio/combined ones), and diff against
`app.db.weekly_compliance()`'s output on a freshly-loaded
`milestone3_load_db.py` run of the same source data.

## Working agreements

- Confirm before risky actions (pushes, destructive ops) per standard
  practice — nothing here changes that.
- Real team roster/message data must never be committed (repo is
  public) — see existing `.gitignore` and `docs/RESYNC.md` for the
  existing convention.
- Ask clarifying questions when a genuine product/architecture decision
  is unresolved; don't silently assume.
