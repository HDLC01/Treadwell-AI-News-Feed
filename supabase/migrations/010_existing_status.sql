-- 010_existing_status.sql
-- Add an 'existing' project status: a feed project Treadwell already has a bid on
-- or already owns (matched against the Dropbox $$ Potential Bids / Projects folders
-- by the local dedup matcher). 'existing' is excluded from the default feed, map,
-- stats, and connector outreach so we never re-pitch a project we already have.
-- Idempotent (mirrors the 007 pattern).
do $$ begin
    if exists (select 1 from pg_constraint where conname = 'projects_status_check') then
        alter table projects drop constraint projects_status_check;
    end if;
    alter table projects add constraint projects_status_check
        check (status in ('new','active','watching','pursuing','won','passed','archived','dismissed','existing'));
end $$;
