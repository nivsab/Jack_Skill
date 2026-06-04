-- migration 002: add breadcrumbs and chunk_type to doc_chunks

ALTER TABLE doc_chunks
    ADD COLUMN IF NOT EXISTS breadcrumbs text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS chunk_type  text NOT NULL DEFAULT 'text';

-- Update search_docs to return breadcrumbs and chunk_type
CREATE OR REPLACE FUNCTION search_docs(
    query_embedding vector(768),
    match_threshold float DEFAULT 0.5,
    match_count     int   DEFAULT 5
)
RETURNS TABLE (
    id          bigint,
    source      text,
    page        integer,
    chunk       text,
    breadcrumbs text,
    chunk_type  text,
    similarity  float
)
LANGUAGE sql STABLE AS $$
    SELECT
        id, source, page, chunk, breadcrumbs, chunk_type,
        1 - (embedding <=> query_embedding) AS similarity
    FROM doc_chunks
    WHERE 1 - (embedding <=> query_embedding) > match_threshold
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;
