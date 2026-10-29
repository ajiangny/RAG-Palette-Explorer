-- Palette RAG Explorer: initial schema
create extension if not exists vector;

-- One row per public-domain painting from the Art Institute of Chicago.
create table if not exists artworks (
  id          bigserial primary key,
  aic_id      integer unique not null,
  title       text not null,
  artist      text,
  date        text,
  style       text,
  image_id    text not null,           -- AIC IIIF image id
  image_url   text not null,           -- https://www.artic.edu/iiif/2/{image_id}/full/843,/0/default.jpg
  description text,                    -- AIC description (HTML stripped)
  palette     jsonb,                   -- [{"lab":[L,a,b],"hex":"#rrggbb","weight":0.31}, ...]
  -- CIELAB histogram, 8x8x8 bins, L1-normalized then sqrt (Hellinger) so cosine works.
  -- If bin config changes after tuning, alter this dimension and re-run build_index.
  hist        vector(512),
  created_at  timestamptz default now()
);

create index if not exists artworks_hist_hnsw
  on artworks using hnsw (hist vector_cosine_ops);

-- Text the explainer can cite: Wikipedia artist/style pages + AIC descriptions.
create table if not exists text_chunks (
  id           bigserial primary key,
  artwork_id   bigint references artworks(id) on delete cascade,  -- null for Wikipedia chunks
  artist       text,
  source_title text not null,
  source_url   text not null,
  content      text not null,
  embedding    vector(768),
  unique (source_url, content)
);

create index if not exists text_chunks_embedding_hnsw
  on text_chunks using hnsw (embedding vector_cosine_ops);
create index if not exists text_chunks_artist_idx on text_chunks (artist);

-- Stage 1 retrieval: nearest paintings by histogram (cosine).
create or replace function match_palettes(query vector(512), k int default 100)
returns table (id bigint, aic_id int, title text, artist text, image_url text,
               palette jsonb, similarity float)
language sql stable as $$
  select a.id, a.aic_id, a.title, a.artist, a.image_url, a.palette,
         1 - (a.hist <=> query) as similarity
  from artworks a
  where a.hist is not null
  order by a.hist <=> query
  limit k;
$$;

-- Web map: start from a painting already in the collection.
create or replace function match_palettes_by_id(seed_id bigint, k int default 100)
returns table (id bigint, aic_id int, title text, artist text, image_url text,
               palette jsonb, similarity float)
language sql stable as $$
  select m.*
  from artworks s, match_palettes(s.hist, k + 1) m
  where s.id = seed_id and m.id <> seed_id
  limit k;
$$;

-- Precomputed neighbors for fast graph expansion. `kind` leaves room for
-- artist/style edges later; for now only 'palette' edges are written.
create table if not exists artwork_edges (
  source_id bigint references artworks(id) on delete cascade,
  target_id bigint references artworks(id) on delete cascade,
  kind      text not null default 'palette',
  score     float not null,
  primary key (source_id, target_id, kind)
);

-- Row Level Security: on, with no policies. Supabase's public REST API (anon /
-- authenticated keys) can't read or write these tables. The FastAPI backend
-- connects directly as the `postgres` role via DATABASE_URL, which bypasses RLS.
alter table artworks      enable row level security;
alter table text_chunks   enable row level security;
alter table artwork_edges enable row level security;

-- RAG retrieval: best text chunks for a set of artists.
create or replace function match_chunks(query vector(768), artists text[], k int default 8)
returns table (id bigint, artist text, source_title text, source_url text,
               content text, similarity float)
language sql stable as $$
  select c.id, c.artist, c.source_title, c.source_url, c.content,
         1 - (c.embedding <=> query) as similarity
  from text_chunks c
  where c.embedding is not null and c.artist = any(artists)
  order by c.embedding <=> query
  limit k;
$$;
