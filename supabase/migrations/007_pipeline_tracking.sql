-- 007_pipeline_tracking.sql
-- In-app pipeline tracking: a free-text notes field + two new pipeline statuses
-- (won, passed) so Kyle can track opportunities through to an outcome.
-- Idempotent.

-- notes
alter table projects add column if not exists notes text;

-- Expand the status CHECK to include 'won' and 'passed'.
do $$ begin
    if exists (select 1 from pg_constraint where conname = 'projects_status_check') then
        alter table projects drop constraint projects_status_check;
    end if;
    alter table projects add constraint projects_status_check
        check (status in ('new','active','watching','pursuing','won','passed','archived','dismissed'));
end $$;
