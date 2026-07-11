-- 0010_embedding_dim.sql - retarget knowledge_chunks.embedding to the shared
-- 384-dim contract (settings.embedding_dim). The default local embedder
-- (BAAI/bge-small-en-v1.5) is natively 384; Azure's text-embedding-3 family
-- truncates to 384 server-side via its dimensions parameter, so local<->azure
-- swaps need no further migration. Existing vectors cannot be converted
-- across dimensions and are nulled - pre-launch there is only dev seed data,
-- and re-running the seed / reprocessing documents re-embeds everything.

drop index knowledge_chunks_embedding_idx;
alter table knowledge_chunks alter column embedding type vector(384) using null;
create index knowledge_chunks_embedding_idx on knowledge_chunks using hnsw (embedding vector_cosine_ops);
