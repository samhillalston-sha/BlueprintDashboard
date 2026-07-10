-- M1: row-level security for tenant isolation.
--
-- Run this after 0001_multi_tenant_foundation.sql, same way (paste into
-- the Supabase SQL Editor and run).
--
-- The one property to keep re-verifying at every milestone: a user in
-- org A can never read or write a row belonging to org B, enforced here
-- at the database layer, not just in application code.

-- ---------------------------------------------------------------------
-- Helper functions. Both are SECURITY DEFINER so they run as the
-- function owner (which bypasses RLS) rather than the querying role —
-- otherwise a policy on `profiles` that calls a function which queries
-- `profiles` would recurse into its own RLS check.
-- ---------------------------------------------------------------------
create function public.current_org_id()
returns uuid
language sql
stable
security definer set search_path = public
as $$
    select org_id from public.profiles where id = auth.uid();
$$;

create function public.is_coach()
returns boolean
language sql
stable
security definer set search_path = public
as $$
    select exists (
        select 1 from public.profiles
        where id = auth.uid() and role = 'coach'
    );
$$;

-- ---------------------------------------------------------------------
-- organizations
-- Manual onboarding only in this phase (no self-serve signup UI), so
-- there's deliberately no insert policy for authenticated users — org
-- creation goes through the service-role key, which bypasses RLS.
-- ---------------------------------------------------------------------
alter table organizations enable row level security;

create policy "members can view their own org"
    on organizations for select
    using (id = current_org_id());

create policy "coach can update their own org"
    on organizations for update
    using (id = current_org_id() and is_coach());

-- ---------------------------------------------------------------------
-- profiles
-- ---------------------------------------------------------------------
alter table profiles enable row level security;

create policy "members can view profiles in their org"
    on profiles for select
    using (org_id = current_org_id() or id = auth.uid());

create policy "users can update their own profile"
    on profiles for update
    using (id = auth.uid());

-- ---------------------------------------------------------------------
-- team_config
-- ---------------------------------------------------------------------
alter table team_config enable row level security;

create policy "members can view their org's config"
    on team_config for select
    using (org_id = current_org_id());

create policy "coach can manage their org's config"
    on team_config for insert
    with check (org_id = current_org_id() and is_coach());

create policy "coach can update their org's config"
    on team_config for update
    using (org_id = current_org_id() and is_coach());

-- ---------------------------------------------------------------------
-- players / injuries / posts
-- Reads are open to any member of the org (coach + athletes both see
-- the compliance grid). Writes are coach-only from the app's point of
-- view; the Slack sync job writes through the service-role key instead
-- (bypasses RLS), so this mostly guards a future in-app edit UI.
-- ---------------------------------------------------------------------
alter table players  enable row level security;
alter table injuries enable row level security;
alter table posts    enable row level security;

create policy "members can view their org's players"
    on players for select
    using (org_id = current_org_id());

create policy "coach can manage their org's players"
    on players for insert
    with check (org_id = current_org_id() and is_coach());

create policy "coach can update their org's players"
    on players for update
    using (org_id = current_org_id() and is_coach());

create policy "coach can delete their org's players"
    on players for delete
    using (org_id = current_org_id() and is_coach());

create policy "members can view their org's injuries"
    on injuries for select
    using (org_id = current_org_id());

create policy "coach can manage their org's injuries"
    on injuries for insert
    with check (org_id = current_org_id() and is_coach());

create policy "coach can update their org's injuries"
    on injuries for update
    using (org_id = current_org_id() and is_coach());

create policy "coach can delete their org's injuries"
    on injuries for delete
    using (org_id = current_org_id() and is_coach());

create policy "members can view their org's posts"
    on posts for select
    using (org_id = current_org_id());

create policy "coach can manage their org's posts"
    on posts for insert
    with check (org_id = current_org_id() and is_coach());

create policy "coach can update their org's posts"
    on posts for update
    using (org_id = current_org_id() and is_coach());

create policy "coach can delete their org's posts"
    on posts for delete
    using (org_id = current_org_id() and is_coach());
