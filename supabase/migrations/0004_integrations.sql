-- M2: integrations — per-org messaging provider connections (Slack now,
-- Discord/others later via the same MessagingProvider interface).
--
-- Run this after 0003_grants.sql, same way (paste into the Supabase SQL
-- Editor and run).
--
-- Split into two tables on purpose:
--   - integrations: non-secret config (team name, default channel, which
--     scopes were granted). Coaches can see this — it's what a settings
--     page would show ("Connected to #doyoulikefitness on Blueprint2026").
--   - integration_credentials: the actual bot token / secrets. NOT
--     exposed to `authenticated` at all (no RLS policy, no table grant).
--     Only the service-role key (server-side sync jobs) can ever read
--     this — a coach's browser session must never see a live bot token.

create table integrations (
    id            bigint generated always as identity primary key,
    org_id        uuid not null references organizations(id) on delete cascade,
    provider_type text not null check (provider_type in ('slack')),
    config        jsonb not null default '{}'::jsonb,
    -- config (Slack): {"team_id", "team_name", "channel_id", "channel_name", "scopes": [...]}
    installed_by  uuid references profiles(id) on delete set null,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (org_id, provider_type)  -- one Slack connection per org, for now
);

create table integration_credentials (
    integration_id bigint primary key references integrations(id) on delete cascade,
    credentials    jsonb not null default '{}'::jsonb,
    -- credentials (Slack): {"bot_token", "bot_user_id", "authed_user_id"}
    updated_at     timestamptz not null default now()
);

create index integrations_org_id_idx on integrations (org_id);

alter table integrations enable row level security;
alter table integration_credentials enable row level security;
-- integration_credentials gets RLS enabled but deliberately NO policies
-- and NO grants below — that combination means even service_role's
-- table grant is what allows access, not a policy (service_role bypasses
-- RLS entirely); `authenticated`/`anon` get nothing, ever, on this table.

create policy "members can view their org's integrations"
    on integrations for select
    using (org_id = current_org_id());

create policy "coach can manage their org's integrations"
    on integrations for insert
    with check (org_id = current_org_id() and is_coach());

create policy "coach can update their org's integrations"
    on integrations for update
    using (org_id = current_org_id() and is_coach());

create policy "coach can delete their org's integrations"
    on integrations for delete
    using (org_id = current_org_id() and is_coach());

grant select, insert, update, delete on public.integrations to service_role, authenticated;
grant select, insert, update, delete on public.integration_credentials to service_role;
grant usage, select on all sequences in schema public to service_role, authenticated;
