-- Full-text search on /articles.
--
-- body_text is the plain prose the Markdown renderer produces alongside
-- body_html, without code, math or alt text. render_all.py fills it; until then
-- an article is still found by its title, description and tags.
--
-- search is generated, so it can never drift from the columns it reads. The
-- weights make a title match outrank a description or tag match, which in turn
-- outranks a match in the body.
--
-- pg_trgm backs the typo fallback ("kinmatics") when full-text search finds
-- nothing. Supabase keeps extensions in their own schema, hence the qualified
-- names.
--
-- Safe to run more than once.

create extension if not exists pg_trgm with schema extensions;

alter table content add column if not exists body_text text;

-- array_to_string is only stable, which a generated column refuses. Joining
-- text with a space depends on no setting, so this wrapper is truly immutable.
create or replace function content_tags_text(tags text[]) returns text
    language sql immutable parallel safe
    as $$ select array_to_string(tags, ' ') $$;

alter table content add column if not exists search tsvector
    generated always as (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
        setweight(to_tsvector('english', content_tags_text(tags)), 'B') ||
        setweight(to_tsvector('english', coalesce(body_text, '')), 'C')
    ) stored;

create index if not exists content_search_idx on content using gin (search);

create index if not exists content_title_trgm_idx
    on content using gin (title extensions.gin_trgm_ops);
