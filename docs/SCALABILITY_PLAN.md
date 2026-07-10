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

Blocker hit and resolved: the sandbox's network egress proxy explicitly
never supports raw-TCP database connections (port 5432) regardless of
network policy tier — this is a hard proxy limitation, not
session-specific. It also returned a 403 policy denial for HTTPS calls
to `*.supabase.co` under the "Trusted" network tier. Sam has since
changed this environment's network access setting to **"Full"** and is
starting a fresh session so it takes effect (network policy changes only
apply to new sessions).

Even with Full network access, direct psql/Postgres (port 5432) may
still not work through the proxy (raw-TCP DBs are called out as
unsupported in `/root/.ccr/README.md` regardless of tier) — if so,
don't fight it: run schema/RLS/migration SQL through the Supabase
dashboard's SQL Editor (Sam pastes SQL there, no connection needed from
the sandbox), and use the HTTPS-based Supabase REST/Auth APIs (which
Full access should unblock) for everything else, including the actual
app's runtime DB access via Supabase's client libraries/PostgREST
instead of a direct psycopg2 connection if needed.

Task list existed for M1 (created via TaskCreate in the prior session,
IDs won't carry over — recreate if useful):
1. Design multi-tenant schema (organizations, users, team_config, org_id FKs)
2. Write RLS policies for tenant isolation
3. Migrate existing SQLite data to Postgres/Supabase
4. Wire Supabase Auth into Flask app
5. Test tenant isolation with two fake orgs
6. Manual verification against real team data

None of these were completed yet — schema design had just started when
the network blocker was hit. Start from task 1.

## Working agreements

- Confirm before risky actions (pushes, destructive ops) per standard
  practice — nothing here changes that.
- Real team roster/message data must never be committed (repo is
  public) — see existing `.gitignore` and `docs/RESYNC.md` for the
  existing convention.
- Ask clarifying questions when a genuine product/architecture decision
  is unresolved; don't silently assume.
