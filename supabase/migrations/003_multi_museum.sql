-- Paintings can now come from more than one museum (AIC, Cleveland Museum of Art).
alter table artworks add column if not exists source     text not null default 'aic';
alter table artworks add column if not exists source_id  text;   -- the museum's own object id
alter table artworks add column if not exists source_url text;   -- the object's page on the museum site

update artworks
set source_id  = aic_id::text,
    source_url = 'https://www.artic.edu/artworks/' || aic_id
where source = 'aic' and source_id is null;

alter table artworks alter column source_id set not null;
alter table artworks alter column aic_id drop not null;
alter table artworks drop constraint if exists artworks_source_key;
alter table artworks add constraint artworks_source_key unique (source, source_id);

-- Return types change (aic_id → source, source_url), so the functions are recreated.
drop function if exists match_palettes_by_id(bigint, int);
drop function if exists match_palettes(vector, int);

create function match_palettes(query vector(512), k int default 100)
returns table (id bigint, source text, source_url text, title text, artist text, image_url text,
               palette jsonb, similarity float)
language sql stable as $$
  select a.id, a.source, a.source_url, a.title, a.artist, a.image_url, a.palette,
         1 - (a.hist <=> query) as similarity
  from artworks a
  where a.hist is not null
  order by a.hist <=> query
  limit k;
$$;

create function match_palettes_by_id(seed_id bigint, k int default 100)
returns table (id bigint, source text, source_url text, title text, artist text, image_url text,
               palette jsonb, similarity float)
language sql stable as $$
  select m.*
  from artworks s, match_palettes(s.hist, k + 1) m
  where s.id = seed_id and m.id <> seed_id
  limit k;
$$;
