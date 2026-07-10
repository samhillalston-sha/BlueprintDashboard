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

Task list (recreated via TaskCreate this session — IDs won't carry over
to a new session, recreate if useful):
1. Design multi-tenant schema (organizations, users, team_config, org_id FKs) — DONE
2. Write RLS policies for tenant isolation — DONE
3. Migrate existing SQLite data to Postgres/Supabase — NOT STARTED, see below
4. Wire Supabase Auth into Flask app — not started
5. Test tenant isolation with two fake orgs — DONE, see below
6. Manual verification against real team data — blocked on task 3

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

### Task 3 — deliberately not started yet

Started to auto-regenerate `data/messages_sample.json` from a live Slack
pull (per `docs/RESYNC.md`) in order to have something to migrate, since
`blueprint.db`/`data/` don't survive a fresh session (gitignored by
design). Sam stopped this: pulling real team data into a brand-new,
unproven multi-tenant system before it's fully wired up (auth included)
was premature — fake-org testing (task 5) was the right thing to prove
out first, which is now done. **Don't restart the real-data migration
without checking with Sam first** — it's not just an engineering
step, it's real athlete data going into new infra for the first time
this season.

Once it's time: the plan is still to re-sync from Slack (`docs/RESYNC.md`)
to rebuild the source JSON, then write a one-off script that reads it
(reusing `app/classify.py` logic, or by then whatever `team_config`
replaces it with) and inserts into Supabase via the REST API under
Sam's real org — created first, with his own coach profile properly
linked, not the throwaway service-role-only pattern used for the RLS test.

### Task 4 — not started

Wire Supabase Auth into `app/web.py`: verify incoming JWTs against
`SUPABASE_JWKS_URL`, look up `org_id`/`role` from `profiles`, scope every
query by it. No decisions made yet on session mechanism (cookie vs
bearer) — that's still open.

## Working agreements

- Confirm before risky actions (pushes, destructive ops) per standard
  practice — nothing here changes that.
- Real team roster/message data must never be committed (repo is
  public) — see existing `.gitignore` and `docs/RESYNC.md` for the
  existing convention.
- Ask clarifying questions when a genuine product/architecture decision
  is unresolved; don't silently assume.
