"""
rag/ingest.py — פייפליין RAG: PDF → chunks → embeddings → Supabase.

תהליך:
  1. קרא PDF מ-data/manuals/
  2. חתוך לחלקים (chunking) — 400 תווים, חפיפה 80
  3. צור embedding לכל chunk דרך Ollama (nomic-embed-text)
  4. העלה ל-Supabase טבלת doc_chunks

דרישות:
  - Ollama רץ מקומית עם nomic-embed-text:
      ollama pull nomic-embed-text
  - SUPABASE_URL + SUPABASE_KEY ב-.env

CLI:
  python rag/ingest.py data/manuals/prius.pdf
  python rag/ingest.py data/manuals/  (כל קבצי ה-PDF בתיקייה)
"""
import json
import os
import sys
import urllib.request
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# Windows encoding fix
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL   = "http://localhost:11434/api/embeddings"
EMBED_MODEL  = "nomic-embed-text"
CHUNK_SIZE    = 400   # תווים
CHUNK_OVERLAP = 150   # חפיפה — גדולה יותר כדי לא לחתוך הקשר


# ─── PDF → טקסט ───────────────────────────────────────────────────────────────

def _extract_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """
    מחלץ טקסט לפי עמוד דרך pdfplumber.
    pdfplumber מצוין לטבלאות — מחלץ אותן כטקסט מסודר בשורות.
    fallback ל-pypdf אם pdfplumber נכשל בעמוד ספציפי.
    מחזיר [(page_num, text), ...].
    """
    import pdfplumber
    from pypdf import PdfReader

    pages = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                # חילוץ טבלאות כטקסט מסודר
                tables_text = ""
                for table in (page.extract_tables() or []):
                    for row in table:
                        line = " | ".join(str(cell or "").strip() for cell in row if cell)
                        if line.strip():
                            tables_text += line + "\n"

                # טקסט רגיל
                body_text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""

                combined = f"{body_text}\n{tables_text}".strip()
                if combined:
                    pages.append((i, combined))
    except Exception:
        # fallback: pypdf
        reader = PdfReader(str(pdf_path))
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append((i, text))

    return pages


# ─── Chunking ─────────────────────────────────────────────────────────────────

def _chunk_text(text: str) -> list[str]:
    """חותך טקסט ל-chunks עם חפיפה."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end].strip())
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if len(c) > 30]  # סינון chunks קצרים מדי


# ─── Ollama Embedding ──────────────────────────────────────────────────────────

def _embed(text: str) -> list[float] | None:
    """שולח טקסט ל-Ollama ומחזיר וקטור 768 ממדים."""
    try:
        body = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
        req  = urllib.request.Request(
            OLLAMA_URL,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())["embedding"]
    except Exception as e:
        print(f"  ⚠️  embedding נכשל: {e}", flush=True)
        return None


# ─── Supabase Upload ──────────────────────────────────────────────────────────

def _get_client():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        raise RuntimeError("חסרים SUPABASE_URL / SUPABASE_KEY ב-.env")
    return create_client(url, key)


def _upload_chunks(client, source: str, rows: list[dict], batch_size: int = 100) -> int:
    """מעלה את ה-chunks ל-Supabase בבאצ'ים. מחזיר מספר שורות שהועלו."""
    if not rows:
        return 0
    uploaded = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        client.table("doc_chunks").insert(batch).execute()
        uploaded += len(batch)
        print(f"  📤 הועלו {uploaded}/{len(rows)} chunks", end="\r", flush=True)
    return uploaded


# ─── פייפליין ראשי ────────────────────────────────────────────────────────────

def ingest_pdf(pdf_path: Path, client) -> int:
    """
    מעבד קובץ PDF אחד מקצה לקצה.
    מחזיר מספר ה-chunks שהועלו.
    """
    source = pdf_path.name
    print(f"\n📄 מעבד: {source}", flush=True)

    # בדוק שלא כבר קיים
    existing = (
        client.table("doc_chunks")
        .select("id", count="exact")
        .eq("source", source)
        .execute()
    )
    if existing.count and existing.count > 0:
        print(f"  ⏭️  כבר קיים ב-DB ({existing.count} chunks) — מדלג.", flush=True)
        return 0

    pages = _extract_pages(pdf_path)
    if not pages:
        print("  ⚠️  לא נמצא טקסט ב-PDF.", flush=True)
        return 0

    print(f"  📖 {len(pages)} עמודים עם טקסט", flush=True)

    rows = []
    for page_num, text in pages:
        chunks = _chunk_text(text)
        for chunk_idx, chunk in enumerate(chunks):
            embedding = _embed(chunk)
            if embedding is None:
                continue
            rows.append({
                "source":    source,
                "page":      page_num,
                "chunk_idx": chunk_idx,
                "chunk":     chunk,
                "embedding": embedding,
            })
            print(f"  ✅ עמוד {page_num} chunk {chunk_idx+1}/{len(chunks)}", end="\r", flush=True)

    uploaded = _upload_chunks(client, source, rows)
    print(f"\n  🚀 הועלו {uploaded} chunks ל-Supabase.", flush=True)
    return uploaded


def ingest_all(path: Path) -> None:
    """מעבד קובץ אחד או כל קבצי PDF בתיקייה."""
    client = _get_client()

    if path.is_file():
        pdfs = [path]
    elif path.is_dir():
        pdfs = sorted(path.glob("*.pdf"))
        if not pdfs:
            print(f"לא נמצאו קבצי PDF ב-{path}")
            return
    else:
        print(f"נתיב לא קיים: {path}")
        return

    total = 0
    for pdf in pdfs:
        total += ingest_pdf(pdf, client)

    print(f"\n✅ סה\"כ: {total} chunks הועלו ל-Supabase.")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("שימוש: python rag/ingest.py <קובץ.pdf | תיקייה>")
        sys.exit(1)

    target = Path(sys.argv[1])
    ingest_all(target)
