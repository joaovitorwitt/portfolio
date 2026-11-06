-- Articles are written in Markdown (body_md) and rendered once, when saved, into
-- body_html, which is what pages serve. The legacy `content` column stays until
-- every article has moved over and a backup exists.
--
-- toc and word_count come from that same render, so showing them costs a page
-- nothing. updated_at starts out equal to created_at: no row has been edited yet,
-- and a page shows "Updated on" only when the two differ.
--
-- Safe to run more than once: the backfill only touches rows without a value.

alter table content
    add column if not exists body_md text,
    add column if not exists body_html text,
    add column if not exists has_math boolean not null default false,
    add column if not exists toc jsonb not null default '[]',
    add column if not exists word_count integer not null default 0,
    add column if not exists updated_at timestamptz;

update content set updated_at = created_at where updated_at is null;

alter table content
    alter column updated_at set default now(),
    alter column updated_at set not null;
