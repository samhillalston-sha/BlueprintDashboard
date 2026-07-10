-- M1: multi-tenant foundation.
--
-- How to run this: paste the whole file into the Supabase dashboard's
-- SQL Editor (Project -> SQL Editor -> New query) and run it. The sandbox
-- this was written in cannot open a direct Postgres connection (raw TCP
-- is blocked by the network proxy regardless of network tier), so there's
-- no automated way to apply this from here.
--
-- Safe to run once against a fresh project. Not written to be re-run.

-- ---------------------------------------------------------------------
-- organizations: one row per customer team.
-- ---------------------------------------------------------------------
create table organizations (
    id         uuid primary key default gen_random_uuid(),
    name       text not null,
    slug       text not null unique,
    join_code  text unique,  -- shareable athlete self-join code; coach can regenerate
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- profiles: one row per logged-in user (coach or athlete), 1:1 with
-- Supabase's auth.users. org_id/role start null and get filled in during
-- onboarding (invite accept or join-code redemption) since a brand new
-- signup doesn't know its org yet.
-- ---------------------------------------------------------------------
create table profiles (
    id           uuid primary key references auth.users(id) on delete cascade,
    org_id       uuid references organizations(id) on delete cascade,
    role         text check (role in ('coach', 'athlete')),
    display_name text,
    created_at   timestamptz not null default now()
);

-- Every new Supabase Auth signup gets a blank profile row automatically.
create function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
    insert into public.profiles (id, display_name)
    values (new.id, new.raw_user_meta_data ->> 'display_name');
    return new;
end;
$$;

create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------
-- team_config: per-org rules engine config (categories/keywords/which
-- categories count toward which compliance box). One row per org.
-- Shape mirrors app/classify.py's KEYWORDS dict + the throwing/cardio
-- credit rules, so a team's config can fully replace the hardcoded
-- Python version. The config UI to edit this is M3 — for M1 this just
-- needs to exist and hold a valid default per org.
-- ---------------------------------------------------------------------
create table team_config (
    org_id                     uuid primary key references organizations(id) on delete cascade,
    categories                 jsonb not null default '[]'::jsonb,
    -- categories: [{"key": "throwing", "label": "Throwing", "keywords": [...]}, ...]
    required_categories        jsonb not null default '[]'::jsonb,
    -- which category keys must be posted weekly for compliance, e.g. ["throwing", "cardio"]
    cardio_credit_categories   jsonb not null default '[]'::jsonb,
    -- category keys that also satisfy the "cardio" box, e.g. ["cardio", "ultimate", "sports"]
    updated_at                 timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- players / injuries / posts: existing SQLite tables, now org-scoped.
-- org_id is denormalized onto every row (not just reachable via a join)
-- so RLS policies can filter directly without a subquery through players.
-- ---------------------------------------------------------------------
create table players (
    id            bigint generated always as identity primary key,
    org_id        uuid not null references organizations(id) on delete cascade,
    profile_id    uuid references profiles(id) on delete set null,  -- set once the athlete has a login
    name          text not null,
    slack_name    text,
    slack_user_id text,
    position      text,
    is_rostered   boolean not null default false,
    is_active     boolean not null default true,
    unique (org_id, name),
    unique (org_id, slack_name),
    unique (org_id, slack_user_id)
);

create table injuries (
    id           bigint generated always as identity primary key,
    org_id       uuid not null references organizations(id) on delete cascade,
    player_id    bigint not null references players(id) on delete cascade,
    description  text not null,
    excused_from text not null check (excused_from in ('throwing', 'cardio', 'both')),
    start_date   date not null,
    end_date     date
);

create table posts (
    id         bigint generated always as identity primary key,
    org_id     uuid not null references organizations(id) on delete cascade,
    player_id  bigint not null references players(id) on delete cascade,
    posted_on  date not null,
    week_start date not null,
    text       text not null,
    label      text not null,
    tags       text not null default '',
    has_photo  boolean not null default false,
    slack_ts   text,
    unique (org_id, slack_ts)
);

create index players_org_id_idx on players (org_id);
create index injuries_org_id_idx on injuries (org_id);
create index posts_org_id_idx on posts (org_id);
create index posts_org_id_week_start_idx on posts (org_id, week_start);
