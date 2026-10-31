-- Single table for every kind of content. Articles and projects have the same
-- shape today; type-specific fields get added as nullable columns when they
-- actually diverge.

create table if not exists content (
    id          bigint generated always as identity primary key,
    kind        text        not null check (kind in ('article', 'project')),
    title       text        not null,
    slug        text        not null,
    description text        not null default '',
    content     text        not null default '',
    image_url   text,
    tags        text[]      not null default '{}',
    created_at  timestamptz not null default now(),

    -- The public lookup key. Unique per kind so an article and a project may
    -- share a slug without colliding.
    unique (kind, slug)
);

-- Every list query is "filter by kind, newest first".
create index if not exists content_kind_created_at_idx
    on content (kind, created_at desc);

-- Only needed once tag filtering shows up; harmless to create now.
create index if not exists content_tags_idx
    on content using gin (tags);
