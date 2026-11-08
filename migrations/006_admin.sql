-- The admin login: one row per account, created by scripts/create_admin.py.
--
-- Only the password's scrypt hash is stored. After too many wrong attempts the
-- account locks for a while; the count lives here rather than in memory because
-- every Vercel function instance has its own.
--
-- Tables in Supabase's public schema are reachable through its REST API. Row
-- level security with no policies, plus the revoke, keeps the anon and
-- authenticated roles away from the hash. The site connects as the owner, which
-- these rules don't restrict.
--
-- Safe to run more than once. Nothing in `content` changes.

create table if not exists admin_users (
    id              bigint generated always as identity primary key,
    username        text        not null unique,
    password_hash   text        not null,
    failed_attempts integer     not null default 0,
    locked_until    timestamptz,
    created_at      timestamptz not null default now()
);

alter table admin_users enable row level security;

revoke all on admin_users from anon, authenticated;
