"""
rag/semantic_search.py — חיפוש semantic ב-doc_chunks דרך Ollama + pgvector.

CLI: python rag/semantic_search.py "<שאלה>" [match_count]
פלט: JSON ל-stdout
"""
import json
import os
import sys
import urllib.request
import warnings

warnings.filterwarnings("ignore")

from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL  = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"


def _embed(text: str) -> list[float] | None:
    try:
        body = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
        req  = urllib.request.Request(
            OLLAMA_URL,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())["embedding"]
    except Exception:
        return None


def _get_client():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    return create_client(url, key)


def search(query: str, match_count: int = 5, match_threshold: float = 0.5) -> dict:
    """
    מחפש chunks רלוונטיים לשאלה.
    מחזיר dict עם:
      - results: רשימת chunks
      - ollama_unavailable: True אם Ollama לא ענה (דורש אזהרה מפורשת)
      - found: bool
    """
    embedding = _embed(query)
    if embedding is None:
        return {
            "found": False,
            "ollama_unavailable": True,
            "results": [],
            "reason": "Ollama לא פעיל — לא ניתן לחפש בספר הרכב",
        }

    try:
        client = _get_client()
        result = client.rpc(
            "search_docs",
            {
                "query_embedding": embedding,
                "match_threshold":  match_threshold,
                "match_count":      match_count,
            },
        ).execute()
        chunks = result.data or []
        if chunks:
            return {"found": True, "ollama_unavailable": False, "results": chunks}
        return {
            "found": False,
            "ollama_unavailable": False,
            "results": [],
            "reason": "לא נמצאו קטעים רלוונטיים בספר הרכב",
        }
    except Exception:
        return {
            "found": False,
            "ollama_unavailable": False,
            "results": [],
            "reason": "שגיאה בחיפוש ב-Supabase",
        }


def get_rag_context(query: str, match_count: int = 4) -> str:
    """מחזיר בלוק טקסט מוכן להזרקה לפרומפט — לשימוש תוכניתי."""
    results = search(query, match_count=match_count)
    if not results:
        return ""

    lines = ["=== מסמכי מקור (RAG) ==="]
    for r in results.get("results", []):
        sim   = round(r.get("similarity", 0) * 100)
        src   = r.get("source", "")
        page  = r.get("page", "")
        bc    = r.get("breadcrumbs", "")
        label = f"{src} p.{page}" + (f" › {bc}" if bc else "")
        lines.append(f"📄 {label} ({sim}%):")
        lines.append(f"   {r.get('chunk', '')[:300]}")
    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        if len(sys.argv) < 2:
            print(json.dumps({"found": False, "error": "usage: semantic_search.py <query> [count]"}))
            sys.exit(0)

        query       = sys.argv[1]
        match_count = int(sys.argv[2]) if len(sys.argv) > 2 else 5

        result = search(query, match_count=match_count)
        print(json.dumps(result, ensure_ascii=False))

    except Exception as exc:
        print(json.dumps({"found": False, "error": str(exc)}))
