-- Chunks of ~3,500 chars overflow btree's ~2.7 KB row limit in the
-- unique (source_url, content) index. Dedupe on a hash of the content instead.
alter table text_chunks drop constraint if exists text_chunks_source_url_content_key;
create unique index if not exists text_chunks_source_url_content_md5_key
  on text_chunks (source_url, md5(content));
