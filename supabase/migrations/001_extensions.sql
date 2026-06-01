-- 001_extensions.sql
-- Postgres extensions for the Treadwell AI News Feed.
-- pgcrypto -> gen_random_uuid(); cube + earthdistance -> great-circle math in SQL.
-- All idempotent.

create extension if not exists pgcrypto;
create extension if not exists cube;
create extension if not exists earthdistance;
