-- By default HNSW considers only ef_search=40 rows, whatever LIMIT asks for, and filters
-- run afterwards: match_palettes(q, 100) returned ~39 rows, sometimes 0 after exclusions.
-- Search deeper, and keep scanning when filters remove rows.
alter function match_palettes(vector, int) set hnsw.ef_search = 200;
alter function match_palettes(vector, int) set hnsw.iterative_scan = 'strict_order';
alter function match_chunks(vector, text[], int) set hnsw.ef_search = 100;
alter function match_chunks(vector, text[], int) set hnsw.iterative_scan = 'strict_order';
