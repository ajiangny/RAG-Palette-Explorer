-- Keep records that aren't paintings out of search without deleting them.
-- Cleveland's "Painting" type includes pages of manuscript text ("Text, Folio 32 ...").
alter table artworks add column if not exists excluded text;  -- reason; null = searchable

update artworks set excluded = 'manuscript text page'
where source = 'cma' and title ~* '^text\M' and excluded is null;

create or replace function match_palettes(query vector(512), k int default 100)
returns table (id bigint, source text, source_url text, title text, artist text, image_url text,
               palette jsonb, similarity float)
language sql stable as $$
  select a.id, a.source, a.source_url, a.title, a.artist, a.image_url, a.palette,
         1 - (a.hist <=> query) as similarity
  from artworks a
  where a.hist is not null and a.excluded is null
  order by a.hist <=> query
  limit k;
$$;
