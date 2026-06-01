"""
setup.py — התקנה ראשונית של ג'ק עבור משתמש חדש.

מה הסקריפט עושה:
  1. בודק שדרישות הסביבה קיימות (Python, pip packages, Ollama)
  2. מאתחל את סכמת Supabase (טבלאות + פונקציות pgvector)
  3. מנחה את המשתמש לאן להוסיף את קובץ ה-PDF

שימוש:
  python setup.py                        # בדיקה + יצירת טבלאות
  python setup.py --check-only           # בדיקת תקינות בלבד
  python setup.py --ingest <file.pdf>    # העלאת PDF לאחר ההגדרה
"""
import argparse
import os
import subprocess
import sys
import warnings

warnings.filterwarnings("ignore")

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent

# ─── SQL: כל הטבלאות + הפונקציות ──────────────────────────────────────────────

_SCHEMA_SQL = """
-- ── הפעל pgvector ────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;

-- ── doc_chunks: chunks ממדריכי יצרן + embeddings ──────────────────────────────
CREATE TABLE IF NOT EXISTS doc_chunks (
    id        bigserial PRIMARY KEY,
    source    text NOT NULL,
    page      integer NOT NULL,
    chunk_idx integer NOT NULL DEFAULT 0,
    chunk     text NOT NULL,
    embedding vector(768),
    created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS doc_chunks_source_idx ON doc_chunks(source);
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
    make        text NOT NULL,
    model       text NOT NULL,
    year        integer NOT NULL DEFAULT 0,
    start_year  integer NOT NULL DEFAULT 0,
    end_year    integer NOT NULL DEFAULT 9999,
    engine      text NOT NULL DEFAULT '',
    engine_code text NOT NULL DEFAULT '',
    spec_type   text NOT NULL,
    value       text NOT NULL,
    unit        text NOT NULL DEFAULT '',
    source_url  text NOT NULL DEFAULT '',
    confidence  text NOT NULL DEFAULT 'llm',
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

-- ── search_docs: פונקציית pgvector לחיפוש semantic ────────────────────────────
CREATE OR REPLACE FUNCTION search_docs(
    query_embedding vector(768),
    match_threshold float DEFAULT 0.5,
    match_count     int   DEFAULT 5
)
RETURNS TABLE (
    id         bigint,
    source     text,
    page       integer,
    chunk      text,
    similarity float
)
LANGUAGE sql STABLE AS $$
    SELECT
        id, source, page, chunk,
        1 - (embedding <=> query_embedding) AS similarity
    FROM doc_chunks
    WHERE 1 - (embedding <=> query_embedding) > match_threshold
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;
"""

_REQUIREMENTS = [
    "supabase",
    "python-dotenv",
    "pdfplumber",
    "pypdf",
    "duckduckgo-search",
    "groq",
]

_OPTIONAL = ["ollama"]


# ─── בדיקות סביבה ──────────────────────────────────────────────────────────────

def _check_env() -> bool:
    ok = True
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    groq = os.getenv("GROQ_API_KEY", "")

    if not url or not key:
        print("  ❌ .env: חסרים SUPABASE_URL / SUPABASE_KEY")
        ok = False
    else:
        print("  ✅ .env: Supabase מוגדר")

    if not groq:
        print("  ⚠️  .env: GROQ_API_KEY חסר — fill_missing.py ו-extract_from_manual.py לא יפעלו")
    else:
        print("  ✅ .env: GROQ_API_KEY מוגדר")

    return ok


def _check_packages() -> bool:
    ok = True
    for pkg in _REQUIREMENTS:
        try:
            __import__(pkg.replace("-", "_").split("[")[0])
            print(f"  ✅ {pkg}")
        except ImportError:
            print(f"  ❌ {pkg} — הרץ: pip install {pkg}")
            ok = False
    return ok


def _check_ollama() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            data = r.read().decode()
            if "nomic-embed-text" in data:
                print("  ✅ Ollama: nomic-embed-text קיים")
                return True
            else:
                print("  ⚠️  Ollama: nomic-embed-text חסר — הרץ: ollama pull nomic-embed-text")
                return False
    except Exception:
        print("  ⚠️  Ollama: לא רץ — נדרש רק ל-ingest.py (הכנסת PDFs)")
        return False


def _check_data_dir() -> None:
    data_dir = ROOT / "data" / "manuals"
    pdfs = list(data_dir.glob("*.pdf")) if data_dir.exists() else []
    if pdfs:
        print(f"  ✅ data/manuals/: {len(pdfs)} PDF(s) קיימים")
        for p in pdfs:
            print(f"     • {p.name}")
    else:
        print(f"  📂 data/manuals/: ריק — הוסף את ספר היצרן של הרכב שלך")


# ─── אתחול Supabase ─────────────────────────────────────────────────────────────

def _init_supabase() -> bool:
    try:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
        client = create_client(url, key)
        client.rpc("pg_catalog.version").execute()
    except Exception:
        pass

    try:
        from supabase import create_client
        import httpx
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")

        # Execute SQL via REST API (direct query endpoint)
        db_url = url.rstrip("/") + "/rest/v1/rpc/exec_sql"
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        # Supabase doesn't expose raw SQL via client library — use psycopg2 if available
        try:
            import psycopg2
            db_host = url.replace("https://", "").replace("http://", "").split(".")[0]
            pg_url  = f"postgresql://postgres:{key}@db.{db_host}.supabase.co:5432/postgres"
            conn = psycopg2.connect(pg_url, connect_timeout=10)
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(_SCHEMA_SQL)
            conn.close()
            print("  ✅ Supabase: סכמה אותחלה בהצלחה")
            return True
        except ImportError:
            print("  ⚠️  psycopg2 לא מותקן — לא ניתן לאתחל סכמה אוטומטית.")
            print("     הרץ את הSQL ב-Supabase SQL Editor:")
            sql_file = ROOT / "migrations" / "000_full_schema.sql"
            _dump_schema_sql(sql_file)
            print(f"     קובץ: {sql_file}")
            return False
    except Exception as e:
        print(f"  ❌ שגיאת Supabase: {e}")
        return False


def _dump_schema_sql(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_SCHEMA_SQL, encoding="utf-8")


# ─── ראשי ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="הגדרת ג'ק — עוזר DIY לרכב")
    parser.add_argument("--check-only", action="store_true", help="בדוק סביבה בלי לשנות")
    parser.add_argument("--ingest",     metavar="PDF",        help="העלה PDF לאחר הגדרה")
    args = parser.parse_args()

    print("\n🔧 ג'ק — בדיקת סביבה\n")

    print("📦 חבילות Python:")
    pkg_ok = _check_packages()

    print("\n🔑 משתני סביבה (.env):")
    env_ok = _check_env()

    print("\n🤖 Ollama:")
    _check_ollama()

    print("\n📂 קבצי מדריך יצרן:")
    _check_data_dir()

    if args.check_only:
        print("\n✅ בדיקה הסתיימה." if (pkg_ok and env_ok) else "\n❌ יש שגיאות — תקן לפני שימוש.")
        return

    if not env_ok:
        print("\n❌ תקן את ה-.env לפני המשך.")
        return

    print("\n🗄️  Supabase — יצירת טבלאות:")
    _init_supabase()

    # Dump schema SQL for manual application
    schema_file = ROOT / "migrations" / "000_full_schema.sql"
    _dump_schema_sql(schema_file)
    print(f"\n📄 קובץ SQL מלא נשמר ב: migrations/000_full_schema.sql")
    print("   (הרץ ב-Supabase SQL Editor אם הטבלאות לא נוצרו אוטומטית)")

    if args.ingest:
        pdf = Path(args.ingest)
        if not pdf.exists():
            print(f"\n❌ קובץ לא נמצא: {pdf}")
            return
        print(f"\n📥 מעלה PDF: {pdf.name}")
        subprocess.run([sys.executable, "rag/ingest.py", str(pdf)], check=False)

    print("\n🚀 הגדרה הושלמה!")
    print("   הצעד הבא: python rag/ingest.py data/manuals/<your_manual.pdf>")
    print("   לאחר מכן:  python rag/extract_from_manual.py --make <make> --model <model> "
          "--start-year <Y> --end-year <Y> --engine <eng> --pdf <filename.pdf>")


if __name__ == "__main__":
    main()
