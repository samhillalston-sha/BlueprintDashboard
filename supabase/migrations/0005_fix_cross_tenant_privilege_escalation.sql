-- SECURITY FIX: every UPDATE policy from 0002/0004 checked the *existing*
-- row's org_id (via USING) but never constrained the *new* row's org_id
-- (no WITH CHECK). Postgres RLS treats USING and WITH CHECK as separate
-- clauses — without WITH CHECK, an authenticated user can UPDATE a row
-- they legitimately own and change its org_id to point at ANY other org.
--
-- Confirmed exploitable and reproduced against two throwaway orgs (never
-- against real data): a coach of org A PATCHed their own `profiles` row,
-- setting org_id to org B, and immediately read org B's real data with
-- the same already-issued JWT — a complete cross-tenant bypass. The same
-- missing-WITH-CHECK pattern existed on team_config/players/injuries/
-- posts/integrations too (a coach could reassign any row they own to a
-- different org's namespace).
--
-- Run this after 0004_integrations.sql, same way (paste into the
-- Supabase SQL Editor and run). Treat this as urgent — apply it before
-- any second real user/org exists, and definitely before building any
-- self-service join flow (M3) that lets a stranger get an authenticated
-- session at all.

-- ---------------------------------------------------------------------
-- profiles + organizations: org_id/role (profiles) and id (organizations)
-- should never be settable by `authenticated` at all — those transitions
-- only ever happen through a controlled server-side flow (join-code
-- redemption, invite acceptance, manual onboarding) using the
-- service-role key, which bypasses RLS and column grants entirely.
-- Column-level GRANTs enforce this at the SQL level, not just RLS.
-- ---------------------------------------------------------------------
revoke update on public.profiles from authenticated;
grant update (display_name) on public.profiles to authenticated;

revoke update on public.organizations from authenticated;
grant update (name, slug, join_code) on public.organizations to authenticated;

-- ---------------------------------------------------------------------
-- team_config / players / injuries / posts / integrations: add WITH
-- CHECK so org_id cannot change value across an UPDATE. Since a caller's
-- current_org_id() is fixed within a request, requiring the new row to
-- also satisfy org_id = current_org_id() means old org_id must equal
-- new org_id — no drift possible.
-- ---------------------------------------------------------------------
drop policy "coach can update their org's config" on team_config;
create policy "coach can update their org's config"
    on team_config for update
    using (org_id = current_org_id() and is_coach())
    with check (org_id = current_org_id() and is_coach());

drop policy "coach can update their org's players" on players;
create policy "coach can update their org's players"
    on players for update
    using (org_id = current_org_id() and is_coach())
    with check (org_id = current_org_id() and is_coach());

drop policy "coach can update their org's injuries" on injuries;
create policy "coach can update their org's injuries"
    on injuries for update
    using (org_id = current_org_id() and is_coach())
    with check (org_id = current_org_id() and is_coach());

drop policy "coach can update their org's posts" on posts;
create policy "coach can update their org's posts"
    on posts for update
    using (org_id = current_org_id() and is_coach())
    with check (org_id = current_org_id() and is_coach());

drop policy "coach can update their org's integrations" on integrations;
create policy "coach can update their org's integrations"
    on integrations for update
    using (org_id = current_org_id() and is_coach())
    with check (org_id = current_org_id() and is_coach());
