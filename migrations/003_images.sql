-- Intrinsic size of the cover image, so its <img> can reserve the right space
-- before the file loads. Nullable: not every row has a cover, and rows keep
-- working without a size until scripts/migrate_images.py fills it in.

alter table content
    add column if not exists image_width integer,
    add column if not exists image_height integer;
