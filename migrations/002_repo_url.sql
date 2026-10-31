-- Projects carry a link to their repository; articles do not. First real
-- divergence between the two kinds, absorbed as a nullable column rather than
-- a second table.

alter table content
    add column if not exists repo_url text;
