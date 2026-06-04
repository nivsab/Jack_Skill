"""
rag/ingest.py — PDF → structured chunks → embeddings → Supabase.

Pipeline:
  1. Extract via DocumentExtractor (headings, tables, paragraphs)
  2. Embed each chunk via Ollama (nomic-embed-text)
  3. Upload to Supabase doc_chunks

Requirements:
  - Ollama running locally: ollama pull nomic-embed-text
  - SUPABASE_URL + SUPABASE_KEY in .env
  - SUPABASE_SERVICE_KEY in .env (required for --force delete)

CLI:
  python rag/ingest.py data/manuals/Rio-SC-2016.pdf
  python rag/ingest.py data/manuals/          # all PDFs in directory
  python rag/ingest.py data/manuals/Rio-SC-2016.pdf --force
"""
import json
import os
import sys
import urllib.request
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from rag.extractor import DocumentExtractor

OLLAMA_URL  = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
BATCH_SIZE  = 25


# ─── Embedding ────────────────────────────────────────────────────────────────

def _embed(text: str) -> list[float] | None:
    try:
        body = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
        req  = urllib.request.Request(
            OLLAMA_URL, data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())["embedding"]
    except Exception as e:
        print(f"  ⚠️  embedding failed: {e}", flush=True)
        return None


# ─── Supabase client ──────────────────────────────────────────────────────────

def _get_client(admin: bool = False):
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "")
    key = (
        os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY", "")
        if admin else
        os.getenv("SUPABASE_KEY", "")
    )
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL / SUPABASE_KEY in .env")
    return create_client(url, key)


# ─── Ingest pipeline ──────────────────────────────────────────────────────────

def ingest_pdf(pdf_path: Path, force: bool = False) -> int:
    source = pdf_path.name
    client = _get_client(admin=force)

    print(f"\n📄 Processing: {source}", flush=True)

    existing = (
        client.table("doc_chunks")
        .select("id", count="exact")
        .eq("source", source)
        .execute()
    )
    if existing.count and existing.count > 0:
        if not force:
            print(f"  ⏭️  Already in DB ({existing.count} chunks). Use --force to re-ingest.", flush=True)
            return 0
        print(f"  🗑️  Deleting {existing.count} existing chunks...", flush=True)
        client.table("doc_chunks").delete().eq("source", source).execute()

    print("  🔍 Extracting structured chunks...", flush=True)
    extractor = DocumentExtractor(pdf_path)
    chunks    = extractor.extract()
    print(f"  📋 {len(chunks)} chunks extracted (body font: {extractor._body_font_size:.1f}pt)", flush=True)

    if not chunks:
        print("  ⚠️  No chunks produced — check PDF encoding.", flush=True)
        return 0

    rows: list[dict] = []
    skipped = 0
    for i, chunk in enumerate(chunks):
        embedding = _embed(chunk.content)
        if embedding is None:
            skipped += 1
            continue
        rows.append({
            "source":      chunk.source,
            "page":        chunk.page,
            "chunk_idx":   i,
            "chunk":       chunk.content,
            "breadcrumbs": chunk.breadcrumbs,
            "chunk_type":  chunk.chunk_type,
            "embedding":   embedding,
        })
        print(f"  ✅ Embedded {i + 1}/{len(chunks)}", end="\r", flush=True)

    if skipped:
        print(f"\n  ⚠️  Skipped {skipped} chunks (embedding failed)", flush=True)

    uploaded = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("doc_chunks").insert(batch).execute()
        uploaded += len(batch)
        print(f"  📤 Uploaded {uploaded}/{len(rows)}", end="\r", flush=True)

    print(f"\n  🚀 Done: {uploaded} chunks uploaded to Supabase.", flush=True)
    return uploaded


def ingest_all(path: Path, force: bool = False) -> None:
    if path.is_file():
        pdfs = [path]
    elif path.is_dir():
        pdfs = sorted(path.glob("*.pdf"))
        if not pdfs:
            print(f"No PDF files found in {path}")
            return
    else:
        print(f"Path does not exist: {path}")
        return

    total = 0
    for pdf in pdfs:
        total += ingest_pdf(pdf, force=force)

    print(f"\n✅ Total: {total} chunks uploaded.")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args  = [a for a in sys.argv[1:] if not a.startswith("-")]
    force = "--force" in sys.argv

    if not args:
        print("Usage: python rag/ingest.py <file.pdf | directory> [--force]")
        sys.exit(1)

    ingest_all(Path(args[0]), force=force)
