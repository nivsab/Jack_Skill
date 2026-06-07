-- ג'ק — סכמה מלאה ל-Supabase
-- הרץ קובץ זה ב-Supabase Dashboard → SQL Editor → New Query

-- ── הפעל pgvector ─────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;

-- ── doc_chunks: chunks ממדריכי יצרן + embeddings ─────────────────────────────
CREATE TABLE IF NOT EXISTS doc_chunks (
    id          bigserial PRIMARY KEY,
    source      text    NOT NULL,
    page        integer NOT NULL,
    chunk_idx   integer NOT NULL DEFAULT 0,
    chunk       text    NOT NULL,
    breadcrumbs text    NOT NULL DEFAULT '',
    chunk_type  text    NOT NULL DEFAULT 'text',
    embedding   vector(768),
    created_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS doc_chunks_source_idx
    ON doc_chunks(source);

CREATE INDEX IF NOT EXISTS doc_chunks_embedding_idx
    ON doc_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

ALTER TABLE doc_chunks ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "chunks_select" ON doc_chunks FOR SELECT USING (true);
  EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "chunks_insert" ON doc_chunks FOR INSERT WITH CHECK (true);
  EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── vehicle_specs: ספציפיקציות רכב ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vehicle_specs (
    id          bigserial PRIMARY KEY,
    make        text    NOT NULL,
    model       text    NOT NULL,
    year        integer NOT NULL DEFAULT 0,
    start_year  integer NOT NULL DEFAULT 0,
    end_year    integer NOT NULL DEFAULT 9999,
    engine      text    NOT NULL DEFAULT '',
    engine_code text    NOT NULL DEFAULT '',
    spec_type   text    NOT NULL,
    value       text    NOT NULL,
    unit        text    NOT NULL DEFAULT '',
    source_url  text    NOT NULL DEFAULT '',
    confidence  text    NOT NULL DEFAULT 'llm',
    created_at  timestamptz DEFAULT now(),

    UNIQUE (make, model, start_year, end_year, engine, spec_type)
);

CREATE INDEX IF NOT EXISTS vehicle_specs_lookup_idx
    ON vehicle_specs(make, model, start_year, end_year, spec_type);

ALTER TABLE vehicle_specs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "specs_select" ON vehicle_specs FOR SELECT USING (true);
  EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "specs_insert" ON vehicle_specs FOR INSERT WITH CHECK (true);
  EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "specs_update" ON vehicle_specs FOR UPDATE USING (true);
  EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── vehicle_manuals: מיפוי רכב ↔ PDF ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vehicle_manuals (
    id           bigserial PRIMARY KEY,
    make         text    NOT NULL,
    model        text    NOT NULL,
    start_year   integer NOT NULL,
    end_year     integer NOT NULL,
    engine       text    NOT NULL DEFAULT '',
    pdf_filename text    NOT NULL,
    created_at   timestamptz DEFAULT now(),

    UNIQUE (make, model, start_year, end_year, engine)
);

ALTER TABLE vehicle_manuals ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "manuals_select" ON vehicle_manuals FOR SELECT USING (true);
  EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "manuals_insert" ON vehicle_manuals FOR INSERT WITH CHECK (true);
  EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "manuals_update" ON vehicle_manuals FOR UPDATE USING (true);
  EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── search_docs: חיפוש semantic דרך pgvector ──────────────────────────────────
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
