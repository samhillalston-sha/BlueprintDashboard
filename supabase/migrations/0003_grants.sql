-- M1: table/sequence grants.
--
-- Run this after 0002_row_level_security.sql, same way (paste into the
-- Supabase SQL Editor and run).
--
-- RLS policies control *which rows* a role can see; these GRANTs control
-- whether a role can touch the table at all. service_role bypasses RLS
-- policies but still needs base privileges, and PostgREST requests fail
-- with "permission denied" (42501) without them. Supabase projects
-- usually get these by default, but this project's tables came back
-- denied on select, so wiring them explicitly here.

grant usage on schema public to service_role, authenticated, anon;

grant select, insert, update, delete on
    public.organizations,
    public.profiles,
    public.team_config,
    public.players,
    public.injuries,
    public.posts
to service_role, authenticated;

-- anon gets no table grants: unauthenticated requests should be rejected
-- outright, not merely filtered down to zero rows by RLS.

grant usage, select on all sequences in schema public to service_role, authenticated;
