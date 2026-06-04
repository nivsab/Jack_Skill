"""
tests/test_extractor_golden.py — Visual inspection of extractor output.

Runs DocumentExtractor on specific pages and prints structured output
so you can verify heading detection, table splitting, and paragraph chunking.

Usage:
  python tests/test_extractor_golden.py               # default pages
  python tests/test_extractor_golden.py 5 15 30 45    # specific pages
  python tests/test_extractor_golden.py --json        # full JSON output
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.extractor import DocumentExtractor

PDF_PATH = Path("data/manuals/Rio-SC-2016.pdf")

# Representative pages to inspect (1-indexed):
# Cover/TOC area, first chapter, maintenance chapter,
# a spec table page, warning/safety page
DEFAULT_PAGES = {5, 15, 30, 50, 80}


def print_chunk(chunk, idx: int) -> None:
    print(f"\n{'─' * 60}")
    print(f"  #{idx:03d} | p.{chunk.page} | {chunk.chunk_type.upper()}")
    print(f"  Breadcrumbs: {chunk.breadcrumbs or '(none)'}")
    print(f"  Length: {len(chunk.content)} chars")
    print(f"  {'─' * 56}")
    preview = chunk.content[:500]
    if len(chunk.content) > 500:
        preview += f"\n  ... [{len(chunk.content) - 500} more chars]"
    for line in preview.split("\n"):
        print(f"  {line}")


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    page_args = [a for a in args if a.isdigit()]
    pages = {int(p) for p in page_args} if page_args else DEFAULT_PAGES

    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found at {PDF_PATH}")
        print("Run from the jack/ directory.")
        sys.exit(1)

    print(f"PDF:   {PDF_PATH.name}")
    print(f"Pages: {sorted(pages)}")

    extractor = DocumentExtractor(PDF_PATH)

    # Detect body font size (needs full open — do a quick pass)
    import pdfplumber
    with pdfplumber.open(str(PDF_PATH)) as pdf:
        total_pages = len(pdf.pages)
        extractor._body_font_size = extractor._detect_body_font_size(pdf)

    print(f"Total pages: {total_pages}")
    print(f"Body font size: {extractor._body_font_size:.1f}pt")
    print(f"Heading threshold: >= {extractor._body_font_size * 1.22:.1f}pt")

    chunks = extractor.extract(pages=pages)
    print(f"\nExtracted {len(chunks)} chunks from {len(pages)} pages")

    # Summary by type
    text_chunks  = [c for c in chunks if c.chunk_type == "text"]
    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    print(f"  text:  {len(text_chunks)}")
    print(f"  table: {len(table_chunks)}")

    # Unique breadcrumbs found
    breadcrumbs = sorted({c.breadcrumbs for c in chunks if c.breadcrumbs})
    print(f"\nBreadcrumbs found ({len(breadcrumbs)}):")
    for bc in breadcrumbs:
        print(f"  • {bc}")

    if as_json:
        print("\n" + json.dumps([c.model_dump() for c in chunks], ensure_ascii=False, indent=2))
    else:
        print(f"\n{'=' * 60}")
        print("CHUNK DETAILS")
        for i, chunk in enumerate(chunks, 1):
            print_chunk(chunk, i)

    print(f"\n{'=' * 60}")
    print("QUESTIONS TO CHECK:")
    print("  1. Are headings detected correctly? (check Breadcrumbs)")
    print("  2. Are table headers repeated in each group?")
    print("  3. Are paragraphs split at sentence boundaries?")
    print("  4. Is content free of doubled chars or garbled text?")


if __name__ == "__main__":
    main()
