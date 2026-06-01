-- migration 001: vehicle_manuals
-- מיפוי רכב ↔ קובץ PDF של ספר היצרן

CREATE TABLE IF NOT EXISTS vehicle_manuals (
    id           bigserial PRIMARY KEY,
    make         text        NOT NULL,
    model        text        NOT NULL,
    start_year   integer     NOT NULL,
    end_year     integer     NOT NULL,
    engine       text        NOT NULL DEFAULT '',
    pdf_filename text        NOT NULL,
    created_at   timestamptz DEFAULT now(),

    UNIQUE (make, model, start_year, end_year, engine)
);

ALTER TABLE vehicle_manuals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "manuals_select" ON vehicle_manuals FOR SELECT USING (true);
CREATE POLICY "manuals_insert" ON vehicle_manuals FOR INSERT WITH CHECK (true);
CREATE POLICY "manuals_update" ON vehicle_manuals FOR UPDATE USING (true);
CREATE POLICY "manuals_delete" ON vehicle_manuals FOR DELETE USING (true);

-- נתוני ברירת מחדל — קבצי PDF שכבר נכנסו ל-doc_chunks
INSERT INTO vehicle_manuals (make, model, start_year, end_year, engine, pdf_filename)
VALUES
    ('Toyota', 'Yaris', 2019, 2020, '1.5 Hybrid', 'BOOK_YARIS_HYBRID_OM52A96H_2019-2020.pdf'),
    ('Kia',    'Rio',   2017, 2024, '1.0T',        'Rio-SC-2017.pdf'),
    ('Kia',    'Rio',   2017, 2024, '1.4',          'Rio-SC-2017.pdf')
ON CONFLICT (make, model, start_year, end_year, engine) DO NOTHING;
