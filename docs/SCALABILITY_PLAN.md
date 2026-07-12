# Scalability plan — turning Blueprint into a sellable multi-team SaaS

Context for Claude: this file is the compressed memory of a long planning
conversation with Sam. Read this fully before doing any work on the
scalability effort. Branch: `claude/fitness-dashboard-scalability-h4q7ac`.

## ⚠️ UNAPPLIED SECURITY FIX — check this first

`supabase/migrations/0005_fix_cross_tenant_privilege_escalation.sql`
fixes a confirmed, reproduced cross-tenant privilege escalation: every
UPDATE RLS policy from 0002/0004 was missing a WITH CHECK clause, so any
authenticated user could PATCH their own `profiles.org_id` to any other
org's ID and immediately gain full coach-level read/write access to
that org's real data — no new login needed, same JWT. Same bug class
existed on `team_config`/`players`/`injuries`/`posts`/`integrations`
(org_id reassignable on any row a user could otherwise legitimately
update). Reproduced against two throwaway orgs, never against real
data — see the M3 section below for the exact repro steps if this needs
re-verifying. **Check whether Sam has run 0005 yet before assuming RLS
tenant isolation actually holds** — if it hasn't been applied, the
isolation guarantee tested and celebrated throughout M1 does not
currently hold against a malicious authenticated user, only against
unauthenticated ones. Especially don't build or ship any new
self-service signup/join flow (M3's join-code athlete signup) before
confirming this is applied — that feature is what turns this from a
theoretical risk into "any stranger who signs up can read/write any
team's data."

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

## M2 status / where we left off

M2 = integration abstraction + real Slack OAuth ("Add to Slack" instead
of manual bot-token copy/paste). Task list:
1. Design `integrations`/`integration_credentials` tables — DONE
2. Design `MessagingProvider` interface — DONE
3. Implement `SlackProvider` + real OAuth install flow — DONE (code), see below
4. Test end-to-end with a real workspace install — BLOCKED, see below

### What exists now

- `supabase/migrations/0004_integrations.sql` — confirmed live (verified
  by successfully reading/writing both tables directly, empty/200 not
  404/42P01). Two tables, split for a real security
  boundary: `integrations` (non-secret config: team id/name, channel,
  granted scopes — coach-readable via RLS) and `integration_credentials`
  (bot token — zero grants to `authenticated`/`anon` at all, service-role
  only, enforced at the GRANT level not just RLS, so even a coach's own
  valid session token cannot read a live bot token via PostgREST).
- `app/messaging/base.py` — `MessagingProvider` ABC (`install_url`,
  `exchange_code`, `fetch_recent_messages`), `Message`/`OAuthResult`
  value types. Discord or anything else later implements this same
  interface; nothing else in the app needs to change.
- `app/messaging/slack_provider.py` — `SlackProvider`: real OAuth v2
  handshake against `slack.com/oauth/v2/authorize` +
  `oauth.v2.access`, scopes `channels:history,channels:read,users:read`
  (least privilege for what M2 does — add `chat:write` later if/when a
  posting feature exists, don't request it early). Also
  `resolve_channel()` (find a channel by name the bot can see — bot
  still needs `/invite @BotName` in Slack itself, OAuth alone doesn't
  grant channel membership) and `fetch_recent_messages()` (paginated
  `conversations.history` + `users.info` name resolution, same
  date/user/text/has_photo shape as `data/messages_sample.json`, so it
  can be a drop-in replacement for the RESYNC.md/MCP-connector pull path
  in a deployed instance with real internet access).
- `app/messaging/store.py` — Supabase persistence, split to match the
  schema: `save_integration()` uses the coach's own access token (RLS
  scoped), `save_credentials()` uses the service-role key. Never let
  these swap — that's the whole point of the split.
- New Flask routes: `GET /integrations/slack/install` (coach-only,
  generates CSRF state, redirects to Slack), `GET
  /integrations/slack/callback` (verifies state, exchanges code, writes
  both tables).
- Sam already had a Slack App registered (**"Blueprint Dashboard
  Tracker"**, App ID `A0BFH2CNKQS`, workspace Blueprint 2026) from
  before this session — didn't need to create one. Configured this
  session: Bot Token Scopes (`channels:history`, `channels:read`,
  `users:read`) and Redirect URL
  (`http://localhost:5055/integrations/slack/callback` — plain `http`
  works for Slack's `localhost` exception, no HTTPS/tunnel needed for
  this dev-loop). `SLACK_CLIENT_ID`/`SLACK_CLIENT_SECRET` are in `.env`
  (gitignored, as always) — Sam pasted them mid-session, don't ask again
  in a future session, just prompt him to re-paste like the Supabase
  keys.

### Verification done, and why full end-to-end is still blocked

Couldn't drive a real browser from this sandbox reliably (Playwright's
Chromium hit `ERR_CONNECTION_RESET` going through the agent proxy even
with `proxy={'server': ...}` set explicitly — didn't dig further, ran
out of patience budget before Sam wanted to stop for the night; worth
revisiting if browser automation is needed again). Fell back to having
Sam click the real authorize URL himself in his own browser and report
back what he saw — this caught a real bug: the redirect URL wasn't
actually saved in Slack's app config (or "Save URLs" wasn't clicked),
producing `redirect_uri did not match any configured URIs`. Sam fixed
it; re-checked via a plain HTTPS GET from the sandbox (not a full
browser, but enough to look for that specific error string, which
disappeared, plus a session cookie now gets set where none did before)
— reasonably confident the app config is now correct, but this is
inference from response fingerprinting, not a rendered page. If in
doubt, ask Sam to click the link once more and describe what loads:
```
https://slack.com/oauth/v2/authorize?client_id=<SLACK_CLIENT_ID from .env>&scope=channels%3Ahistory%2Cchannels%3Aread%2Cusers%3Aread&redirect_uri=http%3A%2F%2Flocalhost%3A5055%2Fintegrations%2Fslack%2Fcallback&state=<any-string>
```

**Why task 4 (real end-to-end test) is still blocked, not just
untested**: completing the OAuth handshake for real requires Slack to
redirect the browser to `redirect_uri` with a `code` param, which this
sandbox can't receive (it's not internet-reachable), and Sam's own
`localhost:5055` isn't running anything either unless *he* clones the
repo and runs `.venv/bin/flask --app app.web run --port 5055` on his
own machine. Two ways to actually finish task 4 in a future session:
1. Ask Sam to run the Flask app locally himself, click through the real
   install flow, and confirm an `integrations`/`integration_credentials`
   row appears for his org — the most realistic test of the real
   product experience.
2. Wait until M5 (ops hardening / hosting deploy) gives this a real
   public HTTPS URL, register that as an additional Slack redirect URL,
   and test against the deployed instance instead.

Don't just mark task 4 done from a sandbox-side check again — the
config-is-correct verification done this session is real but partial.

### Sync job — done, tested with a faked Slack response

`sync_slack.py` (new, checked in): `.venv/bin/python sync_slack.py
<org_id>`. Looks up the org's Slack config+credentials via
`get_integration_for_sync()`, calls
`SlackProvider.fetch_recent_messages()` since either the org's most
recent stored post date or a 14-day default lookback (first sync ever),
classifies each message with the existing `app/classify.py`, and
upserts into `posts` keyed on `(org_id, slack_ts)` with
`resolution=ignore-duplicates` — safe to run on a schedule (cron, etc.)
without ever creating duplicate posts on re-runs, unlike the one-off
`migrate_to_supabase.py`.

Refactored `migrate_to_supabase.py` at the same time to stop duplicating
its own REST/player-lookup helpers — pulled the shared bits out into
`app/supabase_rest.py` (`service_rest()`, generic service-role PostgREST
call) and `app/roster_store.py` (`player_id_for_slack_name()`,
find-or-create). Both scripts and the sync job now share these; don't
reintroduce a third copy.

Verified with a throwaway test org (created, cleaned up after) and a
mocked `fetch_recent_messages()` returning 3 fake messages: first run
stored all 3 with correct classifications, second run against the exact
same fake messages stored 0 new (all correctly detected as
already-synced) — confirms the dedup logic actually works, not just
that it compiles. This was mocked at the provider boundary (never called
the real Slack API), since there's still no live bot token — see the
OAuth end-to-end blocker above.

### Channel selection — done

`GET/POST /integrations/slack/channel` (coach-only): after OAuth
completes, the callback now redirects here instead of straight to
`/account`. Coach types a channel name (no `#`), the route calls
`SlackProvider.resolve_channel()` against the org's real stored bot
token (fetched server-side via `get_integration_for_sync`, never
exposed to the browser), and on success merges `channel_id`/
`channel_name` into the existing `integrations.config` — **merges**, not
overwrites, so `team_id`/`team_name` survive. On failure (channel
doesn't exist, or bot hasn't been invited to it — OAuth scopes alone
don't grant channel membership, Slack still requires `/invite
@Blueprint Dashboard Tracker` in the target channel) shows a clear
on-page error instead of crashing. `sync_slack.py` still correctly
refuses to run until `channel_id` is set.

Verified with `app.test_client()` in-process against a throwaway
org/coach/fake-integration (`resolve_channel` mocked, same reasoning as
the sync job test — no live bot token to test against yet): form shows
the connected team name, successful resolution redirects to `/account`
and the stored config is confirmed merged correctly (not clobbered),
failed resolution returns 400 with the expected error text instead of a
500. Cleaned up after.

### Not done / open for later

- Actually scheduling `sync_slack.py` to run (cron, etc.) instead of
  someone invoking it by hand — an M5 ops-hardening concern once
  there's a deployed instance to schedule it on.
- Discord or any second `MessagingProvider` implementation — not
  started, interface is ready for it whenever it's wanted.
- The real end-to-end OAuth test (task 4 above) is still the main open
  item before M2 can be called fully done — everything downstream of it
  (sync job, channel selection) has only ever been tested against
  mocked/faked Slack responses, never a real bot token. Don't let that
  fact get lost — "tested" in this doc almost always means "tested with
  a mock," not "proven against live Slack."

## M3 status / where we left off

M3 = coach onboarding UI (join flow) + per-team config UI. Only the
join-flow half is started; team-config UI is not.

### Roster join flow (email/Slack invite OR shareable code) — code done, tested

Product decision required both invite-by-email/Slack AND a shareable
join code. Only the join-code half is built so far — invite-by-email
for *athletes* specifically (as opposed to the coach invite pattern
already used once, manually, in M1) isn't built; re-check the plan
before assuming both exist.

What exists now:
- `app/onboarding_store.py` — `generate_join_code()` (coach's own
  token — RLS + the column grant from migration 0005 already allow a
  coach to edit their own org's `join_code`, no service role needed),
  `redeem_join_code()` (service-role only, both steps: looking up an
  org by code, and the profiles UPDATE — the redeeming user has no org
  yet so their own token can't see `organizations` at all, and
  `profiles.org_id`/`role` are service-role-only since 0005 regardless).
  The redemption UPDATE includes `org_id=is.null` as a query filter, so
  it's an atomic single request that only succeeds if the user doesn't
  already belong to an org — no separate check-then-write race.
- `app.supabase_auth.sign_up()` — self-service account creation
  (athletes only; coaches still get invited manually by Sam, org
  creation itself stays non-self-serve per the product decision).
  Returns whatever Supabase's `/auth/v1/signup` gives back as-is: an
  `access_token` if the project has email confirmation OFF, none if
  it's ON (this project has it ON — confirmed by hitting Supabase's
  real signup endpoint and getting `email rate limit exceeded`, which
  only happens if it actually tries to send a confirmation email).
  Both branches are handled by the `/signup` route.
- New routes: `GET/POST /signup` (public), `GET/POST /join`
  (login-required, redirects to `/account` if the user already has an
  org — won't let someone switch orgs by replaying it),
  `GET/POST /settings/join-code` (coach-only).
- `templates/signup.html`, `templates/join.html`, `templates/join_code.html`.
- `templates/account.html` got small nav links: "Join a team" (if no
  org yet), "Team join code" + "Connect Slack" (if coach).

Verified with `app.test_client()` in-process against a throwaway
org/coach/athlete (all via admin-API-created users with
`email_confirm: true`, sidestepping the real rate limit for testing —
only the actual `/signup` → real Supabase signup path was mocked, not
tested against live Supabase again after confirming the rate limit
exists): coach generates a code, code persists in Supabase; non-coach
correctly blocked from generating one (403); athlete blocked from
redeeming a wrong code; athlete successfully redeems the right code and
`profiles.org_id`/`role` update correctly; **an already-joined athlete
replaying `/join` gets bounced straight to `/account`, doesn't get to
switch orgs**; both `/signup` branches (email-confirmation-required vs.
immediate session) verified via mocking `sign_up` directly, avoiding
hitting Supabase's email rate limit a third time this session. Cleaned
up all test data after.

Notably: `redeem_join_code()` was written to use the service-role key
*before* discovering the 0005 vulnerability, simply because it was the
obviously-correct pattern (an org-less user's own token has no way to
even look up an org by code, RLS blocks it). Turned out to also be the
only safe way to do it once the vulnerability was found — worth noting
as a case where following the established "service role for
org_id/role writes" convention from M1 already prevented a whole class
of bug in new code, independent of whether 0005 has been applied yet.

### Per-team config UI — done

`GET/POST /settings/config` (coach-only). Deliberately a raw-JSON
textarea for `categories` (not a dynamic add/remove-row form builder) —
a real UX limitation worth upgrading later, but building a full JS form
for this felt like premature polish before even one real coach has
asked to edit their config; a JSON textarea is honest about being v0.
`required_categories`/`cardio_credit_categories` are simpler
comma-separated text inputs.

`app/config_store.py` (new): `get_team_config()`/`save_team_config()`,
both through the coach's own token (RLS already allows a coach to
read/write their own org's `team_config`, no service role needed).
`save_team_config()` validates before writing — categories must be a
non-empty list of `{key, keywords, ...}` dicts, `required_categories`/
`cardio_credit_categories` can't reference a category key that doesn't
exist, and it actually constructs a real `Classifier` from the proposed
config (reusing `Classifier.__init__`'s own validation, e.g. "can't have
zero required categories") so a coach can never save something that
would crash `sync_slack.py` on the next run.

Verified in-process against a throwaway org/coach/athlete: non-coach
blocked (403), invalid JSON rejected with a clear message, a
required-category referencing an undefined category key rejected,
valid config saves and persists correctly, GET after save shows it
pre-filled, and — the actual point of the whole M3 classifier effort —
`classifier_for_org()` (the same function `sync_slack.py` uses)
immediately picks up the coach-saved config and classifies differently
based on it. Cleaned up after (one test-data keyword gap along the way,
not a bug — same class of gotcha as the earlier basketball-config test).

### Not done / open for later

- Athlete invite-by-email/Slack (the other half of the "build both"
  product decision) — not started.
- Linking a redeemed athlete's profile to an existing roster `players`
  row (there's a `players.profile_id` column for exactly this, unused
  so far) — no name-matching UI/logic exists yet. Right now a joined
  athlete has an account but isn't connected to their roster entry.
- The config UI's raw-JSON-textarea UX — functional, not friendly. A
  real add/remove-category form is the natural upgrade whenever that
  matters more than shipping speed does.

### Classifier is now team_config-aware — done

Was flagged above as a blocker for the config UI (no point building an
edit UI for config nothing reads) — fixed. `app/classify.py` now has a
`Classifier` class parameterized by `categories`/`required_categories`/
`credit_categories`, with `Classifier.from_team_config()` building one
from a `team_config` row. The old module-level `KEYWORDS`/
`IGNORE_PHRASES`/`classify()` all still exist and work exactly as
before — `classify()` is now a thin wrapper around a default
`Classifier` built from those same constants, kept for milestone2-4
(single-team, pre-multi-tenant) scripts and anywhere not yet org-aware.

Deliberately did NOT generalize the required-categories shape beyond
what `team_config` already encoded in M1 (a primary category + one
credit-expandable secondary category, e.g. throwing+cardio) — a team
needing e.g. three genuinely independent required boxes is a new
product decision, not something to silently invent. `Classifier`
currently supports `required_categories` of length 1 or 2 only
(enforced: raises if empty, treats index 1+ as the sole "secondary/
credit" box).

`app/team_config_store.py` (new, shared) — `classifier_for_org(org_id)`:
fetches the org's real `team_config` row and builds a `Classifier` from
it, falling back to Blueprint's hardcoded default with a printed
warning if the org has no config row yet (e.g. brand new team, no
config UI exists to set one). Both `sync_slack.py` and
`migrate_to_supabase.py` now use this instead of the bare `classify()`
function — the whole point of the exercise, since those are the actual
multi-tenant data-ingestion paths.

Verification, in order:
1. Re-ran the exact M1 task-6 regression (rebuild `blueprint.db` via
   `milestone3_load_db.py`, diff the printed compliance grid) — **byte-
   identical** to the pre-refactor output captured earlier this session.
   Confirms the default `classify()` path has zero behavior change.
2. Fetched Blueprint's *real* stored `team_config` row from Supabase,
   built a `Classifier` from it via `from_team_config()`, and compared
   its output against the hardcoded `classify()` default on 6 sample
   texts (including an `IGNORE_PHRASES` case) — identical tags and
   labels on every one. Confirms the from-config path, not just the
   default path, reproduces Blueprint's exact rules when fed Blueprint's
   exact config.
3. The real test of the feature: built a throwaway org with a
   *genuinely different* team_config (a hypothetical basketball team —
   categories "shooting"/"conditioning"/"lifting", no "throwing"
   category at all) and ran `sync_slack.py` against it with mocked
   messages. `"Threw the frisbee around"` — which Blueprint's rules
   would tag `throwing` — correctly came back `unclassified` for this
   team, since they have no such category. `"Hit some threes and
   suicides"` correctly combined shooting+conditioning. This is the
   actual point of M1's product decision ("make the keyword/slang list
   and categories per-team configurable instead of hardcoded to one
   team's slang") — confirmed working, not just plausible-looking code.
   Cleaned up after (two false starts from a transient sandbox network
   reset and a test-data keyword gap — see git history if the exact
   detours matter, neither was a real bug).
4. Re-ran the sync-job dedup test (from the sync-job section above)
   after this refactor to confirm the `app/team_config_store.py`
   extraction didn't regress it — still passes.
- Coach "create org" self-serve UI — deliberately out of scope per the
  product decision (manual onboarding only, Sam sets up each new team
  himself for now).

## Working agreements

- Confirm before risky actions (pushes, destructive ops) per standard
  practice — nothing here changes that.
- Real team roster/message data must never be committed (repo is
  public) — see existing `.gitignore` and `docs/RESYNC.md` for the
  existing convention.
- Ask clarifying questions when a genuine product/architecture decision
  is unresolved; don't silently assume.
