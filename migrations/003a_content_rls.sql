-- Tables in Supabase's public schema are reachable through its REST API, where
-- the anon role could write to this one. With row level security on and no
-- policies, that API gets nothing. The site connects as the table's owner, which
-- these rules don't restrict.

alter table content enable row level security;
