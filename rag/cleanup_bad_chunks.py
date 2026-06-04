"""
rag/cleanup_bad_chunks.py — מוחק chunks גרועים מ-Supabase.

chunk נחשב גרוע אם alpha_ratio < 0.35 (בעיקר תווי זבל/קטלוג).
משתמש ב-SUPABASE_SERVICE_KEY לעקיפת RLS.

שימוש:
  python rag/cleanup_bad_chunks.py [--dry-run]
"""
import os
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


import re as _re
_CATALOG_CODE = _re.compile(r'^[A-Z]{2,}\d{3,}[A-Z0-9]*$')
_QMARK_WORD   = _re.compile(r'^\?+$')


def _is_bad_chunk(text: str) -> bool:
    if not text or len(text) < 30:
        return True
    letters = sum(1 for c in text if c.isalpha())
    if letters / len(text) < 0.35:
        return True
    words = text.split()
    if not words:
        return True
    qmark_words = sum(1 for w in words if _QMARK_WORD.match(w))
    if qmark_words / len(words) > 0.25:
        return True
    alpha_chars = [c for c in text if c.isalpha()]
    if len(alpha_chars) >= 20:
        pairs = list(zip(alpha_chars, alpha_chars[1:]))
        doubled_ratio = sum(1 for a, b in pairs if a.lower() == b.lower()) / len(pairs)
        if doubled_ratio > 0.4:
            return True
    if len(set(words)) / len(words) < 0.4:
        return True
    catalog_tokens = sum(1 for w in words if _CATALOG_CODE.match(w))
    if catalog_tokens / len(words) > 0.4:
        return True
    return False




def cleanup(dry_run: bool = False):
    from supabase import create_client

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        print("❌ חסרים SUPABASE_URL / SUPABASE_SERVICE_KEY ב-.env")
        sys.exit(1)

    client = create_client(url, key)

    print("🔍 מושך את כל ה-chunks מ-DB...", flush=True)
    batch_size = 1000
    offset = 0
    bad_ids = []

    while True:
        resp = (
            client.table("doc_chunks")
            .select("id, chunk")
            .range(offset, offset + batch_size - 1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            break
        for row in rows:
            if _is_bad_chunk(row["chunk"]):
                bad_ids.append(row["id"])
        offset += len(rows)
        print(f"  סרוק {offset} chunks, נמצאו {len(bad_ids)} גרועים עד כה...", end="\r", flush=True)
        if len(rows) < batch_size:
            break

    print(f"\n📊 סה\"כ: {offset} chunks, {len(bad_ids)} גרועים")

    if not bad_ids:
        print("✅ אין chunks גרועים — DB נקי!")
        return

    if dry_run:
        print(f"🔎 Dry-run: היו נמחקים {len(bad_ids)} chunks (לא בוצע)")
        return

    print(f"🗑️  מוחק {len(bad_ids)} chunks...", flush=True)
    delete_batch = 200
    deleted = 0
    for i in range(0, len(bad_ids), delete_batch):
        batch = bad_ids[i : i + delete_batch]
        client.table("doc_chunks").delete().in_("id", batch).execute()
        deleted += len(batch)
        print(f"  נמחקו {deleted}/{len(bad_ids)}", end="\r", flush=True)

    print(f"\n✅ נמחקו {deleted} chunks גרועים מ-DB.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    cleanup(dry_run=dry_run)
