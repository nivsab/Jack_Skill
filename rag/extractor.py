"""
rag/extractor.py — Structured PDF extraction.

Pipeline per page:
  1. Detect body font size (mode across first 20 pages)
  2. Separate table regions from body text
  3. Detect headings (large/bold font) → update breadcrumb stack
  4. Paragraph-aware chunking for body text
  5. Table chunking: small = one chunk, large = groups with repeated header row

Each DocumentChunk.content starts with "[breadcrumbs]" so the embedding
sees full context without needing a separate metadata lookup.
"""
import re
import sys
import warnings
from collections import Counter
from pathlib import Path
from typing import Literal

warnings.filterwarnings("ignore")

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from pydantic import BaseModel
except ImportError:
    raise ImportError("pydantic required: pip install pydantic")


# ─── Configuration ────────────────────────────────────────────────────────────

CHUNK_MAX_CHARS    = 500   # max body text chars per chunk before splitting
CHUNK_OVERLAP_SENT = 1     # sentences to carry forward as overlap
TABLE_SMALL_ROWS   = 15    # tables with <= this many data rows → single chunk
TABLE_GROUP_ROWS   = 10    # rows per group for large tables
HEADING_SIZE_RATIO = 1.22  # font size >= body * this → heading candidate
LINE_TOP_TOLERANCE = 3.0   # px tolerance for grouping words into the same line
MIN_HEADING_ALPHA  = 0.5   # heading line must be >= this fraction alpha chars


# ─── Pydantic model ───────────────────────────────────────────────────────────

class DocumentChunk(BaseModel):
    source:      str
    page:        int
    chunk_type:  Literal["text", "table"]
    breadcrumbs: str
    content:     str   # includes "[breadcrumbs]\n\n..." prefix when breadcrumbs set


# ─── Quality filter ───────────────────────────────────────────────────────────

_CATALOG_CODE = re.compile(r'^[A-Z]{2,}\d{3,}[A-Z0-9]*$')
_QMARK_WORD   = re.compile(r'^\?+$')


def _is_quality_chunk(text: str) -> bool:
    if len(text) < 30:
        return False
    letters = sum(1 for c in text if c.isalpha())
    if letters / len(text) < 0.25:   # more lenient for tables with numbers
        return False
    words = text.split()
    if not words:
        return False
    qmark_words = sum(1 for w in words if _QMARK_WORD.match(w))
    if qmark_words / len(words) > 0.25:
        return False
    alpha_chars = [c for c in text if c.isalpha()]
    if len(alpha_chars) >= 20:
        pairs = list(zip(alpha_chars, alpha_chars[1:]))
        doubled = sum(1 for a, b in pairs if a.lower() == b.lower()) / len(pairs)
        if doubled > 0.4:
            return False
    if len(set(words)) / len(words) < 0.3:   # more lenient for tables
        return False
    catalog_tokens = sum(1 for w in words if _CATALOG_CODE.match(w))
    if catalog_tokens / len(words) > 0.4:
        return False
    return True


# ─── Text helpers ─────────────────────────────────────────────────────────────

def _last_sentence(text: str) -> str:
    """Return the last complete sentence of text (for overlap)."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return sentences[-1].strip() if sentences else ""


_CID_BULLET = re.compile(r'\(cid:\d+\)')


def _clean_text(text: str) -> str:
    """Replace undecodable PDF characters with readable equivalents."""
    text = _CID_BULLET.sub("•", text)
    return text


def _rows_to_markdown(headers: list[str], rows: list[list[str]]) -> str:
    lines = []
    if headers:
        lines.append(" | ".join(headers))
        lines.append(" | ".join("---" for _ in headers))
    for row in rows:
        lines.append(" | ".join(row))
    return "\n".join(lines)


# ─── TOC parser ───────────────────────────────────────────────────────────────

class TocParser:
    """
    Parses chapter TOC pages to build a page→breadcrumb map.

    Each chapter TOC page has format:
        Chapter Title
        Section Name . . . . . N-K    (chapter N, page K)
        ...

    The TOC page itself is manual page N-1. Section N-K is at PDF page = toc_pdf_page + (K-1).
    """

    _ENTRY_RE      = re.compile(r'^(?:\(cid:\d+\)\s*)?([A-Za-z].+?)[\s.·•]{3,}(\d+)-(\d+)\s*\d*$')
    _LEFT_ENTRY_RE = re.compile(r'^(?:\(cid:\d+\)\s*)?([A-Za-z][^.]+?)[\s.·•]{3,}(\d+)-(\d+)')
    _DOTS_IN_TITLE = re.compile(r'\.{3,}|(?:\s\.){3,}')
    _TRAIL_DOTS    = re.compile(r'[\s.·•]+$')

    def __init__(self):
        self._map: list[tuple[int, str]] = []   # sorted (pdf_page, breadcrumb)

    def build(self, pdf) -> None:
        """Scan all PDF pages and build the page→breadcrumb map."""
        self._map = []
        last_chapter = ""
        for pdf_page_num, page in enumerate(pdf.pages, start=1):
            text  = page.extract_text() or ""
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if not lines:
                continue
            entries = self._parse_toc_entries(lines)
            if entries:
                chapter_title = _CID_BULLET.sub('', lines[0]).strip()
                chapter_title = self._TRAIL_DOTS.sub('', chapter_title).strip()
                last_chapter  = chapter_title
                self._map.append((pdf_page_num, chapter_title))
                for section_title, chapter_num, page_within_chapter in entries:
                    target_pdf_page = pdf_page_num + (page_within_chapter - 1)
                    self._map.append((target_pdf_page, f"{chapter_title} > {section_title}"))
            elif last_chapter and self._ENTRY_RE.match(lines[0]):
                # Continuation TOC page: first line is itself a TOC entry
                for line in lines:
                    m = self._ENTRY_RE.match(line)
                    if m:
                        section = m.group(1).rstrip(". ").strip()
                        if re.search(r'\d+-\d+', section):
                            continue
                        target_pdf_page = pdf_page_num + (int(m.group(3)) - 1)
                        self._map.append((target_pdf_page, f"{last_chapter} > {section}"))
        # Sort by pdf_page, keep last breadcrumb when duplicates
        seen: dict[int, str] = {}
        for pdf_page, bc in self._map:
            seen[pdf_page] = bc          # later entries (deeper) win
        self._map = sorted(seen.items())

    def breadcrumb_for_page(self, pdf_page: int) -> str:
        """Return the most specific breadcrumb for a given PDF page number."""
        if not self._map:
            return ""
        lo, hi = 0, len(self._map) - 1
        result = ""
        while lo <= hi:
            mid = (lo + hi) // 2
            if self._map[mid][0] <= pdf_page:
                result = self._map[mid][1]
                lo = mid + 1
            else:
                hi = mid - 1
        return result

    def _parse_toc_entries(self, lines: list[str]) -> list[tuple[str, int, int]]:
        """
        Returns list of (section_title, chapter_num, page_within_chapter)
        for a valid chapter TOC page. Returns [] if this page is not a TOC.
        """
        if not lines:
            return []
        title = lines[0]

        if self._DOTS_IN_TITLE.search(title):
            # If the first line itself is a full TOC entry (ends with N-K ref), not a chapter title
            if self._ENTRY_RE.match(title):
                return []
            # Otherwise it's a real title with PDF trailing leaders ("Light bulbs . . . .")
            title = self._TRAIL_DOTS.sub('', title).strip()

        if len(title) > 80 or len(title) < 3:
            return []

        entries = []
        for line in lines[1:]:
            m = self._ENTRY_RE.match(line)
            if m:
                section  = m.group(1).rstrip(". ").strip()
                chap_num = int(m.group(2))
                page_k   = int(m.group(3))
                if re.search(r'\d+-\d+', section):
                    # Two-column line: try to recover the left-column entry
                    lm = self._LEFT_ENTRY_RE.match(line)
                    if lm:
                        left_sec = lm.group(1).rstrip(". ").strip()
                        if not re.search(r'\d+-\d+', left_sec):
                            entries.append((left_sec, int(lm.group(2)), int(lm.group(3))))
                    continue
                entries.append((section, chap_num, page_k))

        # Must have >= 3 entries (all already start with a letter due to _ENTRY_RE)
        if len(entries) < 3:
            return []
        return entries


# ─── Main extractor ───────────────────────────────────────────────────────────

class DocumentExtractor:
    """
    Extracts structured chunks from a PDF.

    Usage:
        extractor = DocumentExtractor(Path("manual.pdf"))
        chunks = extractor.extract()          # all pages
        chunks = extractor.extract(pages={5,15,30})  # specific pages only
    """

    def __init__(self, pdf_path: Path):
        self.pdf_path        = pdf_path
        self.source          = pdf_path.name
        self._body_font_size = 10.0
        self._toc            = TocParser()

    # ── Public API ──────────────────────────────────────────────────────────

    def extract(self, pages: set[int] | None = None) -> list[DocumentChunk]:
        """Extract all chunks, optionally limited to specific page numbers (1-indexed)."""
        import pdfplumber
        chunks = []
        with pdfplumber.open(str(self.pdf_path)) as pdf:
            self._body_font_size = self._detect_body_font_size(pdf)
            self._toc = TocParser()
            self._toc.build(pdf)
            for page_num, page in enumerate(pdf.pages, start=1):
                if pages and page_num not in pages:
                    continue
                page_chunks = self._process_page(page, page_num)
                chunks.extend(page_chunks)
        return chunks

    # ── Font size calibration ───────────────────────────────────────────────

    def _detect_body_font_size(self, pdf) -> float:
        sizes: Counter = Counter()
        sample = pdf.pages[:min(20, len(pdf.pages))]
        for page in sample:
            for word in (page.extract_words(extra_attrs=["size"]) or []):
                size = word.get("size")
                if size and 6 < size < 30:
                    sizes[round(size, 1)] += 1
        return sizes.most_common(1)[0][0] if sizes else 10.0

    # ── Per-page processing ─────────────────────────────────────────────────

    def _process_page(self, page, page_num: int) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []

        # Find table regions
        page_tables = page.find_tables() or []
        table_bboxes = [t.bbox for t in page_tables]

        # Extract words with font info
        all_words = page.extract_words(extra_attrs=["size", "fontname"]) or []

        # Filter words outside table regions
        body_words = self._filter_words_outside_tables(all_words, table_bboxes)

        # Body text (excluding table regions)
        body_text = self._extract_body_text(page, table_bboxes, body_words)
        body_chunks = self._chunk_text(body_text, page_num)
        chunks.extend(body_chunks)

        # Tables
        for pt in page_tables:
            table_data = pt.extract()
            if table_data:
                table_chunks = self._chunk_table(table_data, page_num)
                chunks.extend(table_chunks)

        return chunks

    # ── Word grouping helpers ───────────────────────────────────────────────

    def _group_into_lines(self, words: list[dict]) -> list[list[dict]]:
        if not words:
            return []
        sorted_words = sorted(words, key=lambda w: (round(w.get("top", 0) / LINE_TOP_TOLERANCE), w.get("x0", 0)))
        lines: list[list[dict]] = []
        current: list[dict] = [sorted_words[0]]
        current_top = sorted_words[0].get("top", 0)
        for word in sorted_words[1:]:
            if abs(word.get("top", 0) - current_top) <= LINE_TOP_TOLERANCE:
                current.append(word)
            else:
                lines.append(current)
                current = [word]
                current_top = word.get("top", 0)
        if current:
            lines.append(current)
        return lines

    def _filter_words_outside_tables(self, words: list[dict], table_bboxes: list) -> list[dict]:
        if not table_bboxes:
            return words
        result = []
        for w in words:
            wx0, wy0, wx1, wy1 = w.get("x0", 0), w.get("top", 0), w.get("x1", 0), w.get("bottom", 0)
            in_table = any(
                tx0 - 5 <= wx0 and ty0 - 5 <= wy0 and tx1 + 5 >= wx1 and ty1 + 5 >= wy1
                for tx0, ty0, tx1, ty1 in table_bboxes
            )
            if not in_table:
                result.append(w)
        return result

    # ── Body text extraction ────────────────────────────────────────────────

    def _extract_body_text(self, page, table_bboxes: list, body_words: list[dict]) -> str:
        if not table_bboxes:
            raw = page.extract_text() or ""
        elif not body_words:
            return ""
        else:
            lines = self._group_into_lines(body_words)
            raw = "\n".join(" ".join(w["text"] for w in line) for line in lines)
        return _clean_text(raw)

    # ── Text chunking ───────────────────────────────────────────────────────

    def _chunk_text(self, text: str, page_num: int) -> list[DocumentChunk]:
        if not text.strip():
            return []

        breadcrumbs = self._toc.breadcrumb_for_page(page_num)
        paragraphs  = [p.strip() for p in re.split(r'\n\s*\n|\n(?=[A-Z•\-])', text) if p.strip() and len(p.strip()) > 20]

        # Strip redundant page header: first paragraph that matches the chapter title
        chapter_title = breadcrumbs.split(" > ")[0] if breadcrumbs else ""
        if paragraphs and chapter_title and paragraphs[0].strip() == chapter_title.strip():
            paragraphs = paragraphs[1:]

        chunks: list[DocumentChunk] = []
        current_parts: list[str] = []
        current_len   = 0
        prev_sentence = ""

        def _flush():
            if not current_parts:
                return
            body = "\n\n".join(current_parts)
            if prev_sentence:
                body = prev_sentence + "\n\n" + body
            content = f"[{breadcrumbs}]\n\n{body}" if breadcrumbs else body
            if _is_quality_chunk(content):
                chunks.append(DocumentChunk(
                    source=self.source, page=page_num,
                    chunk_type="text", breadcrumbs=breadcrumbs, content=content
                ))

        for para in paragraphs:
            if current_len + len(para) > CHUNK_MAX_CHARS and current_parts:
                _flush()
                prev_sentence = _last_sentence("\n\n".join(current_parts))
                current_parts = [para]
                current_len   = len(para)
            else:
                current_parts.append(para)
                current_len += len(para)

        _flush()
        return chunks

    # ── Table chunking ──────────────────────────────────────────────────────

    def _chunk_table(self, table_data: list[list], page_num: int) -> list[DocumentChunk]:
        breadcrumbs = self._toc.breadcrumb_for_page(page_num)

        # Clean: remove None, strip whitespace, drop fully-empty rows
        cleaned: list[list[str]] = []
        for row in table_data:
            cleaned_row = [str(cell or "").strip() for cell in row]
            if any(cell for cell in cleaned_row):
                cleaned.append(cleaned_row)

        if not cleaned:
            return []

        headers   = cleaned[0]
        data_rows = cleaned[1:] if len(cleaned) > 1 else cleaned

        def make_chunk(rows: list[list[str]], include_header: bool = True) -> DocumentChunk | None:
            content = _rows_to_markdown(headers if include_header else [], rows)
            if breadcrumbs:
                content = f"[{breadcrumbs}]\n\n{content}"
            if not _is_quality_chunk(content):
                return None
            return DocumentChunk(
                source=self.source, page=page_num,
                chunk_type="table", breadcrumbs=breadcrumbs, content=content
            )

        chunks: list[DocumentChunk] = []

        if len(data_rows) <= TABLE_SMALL_ROWS:
            chunk = make_chunk(data_rows)
            if chunk:
                chunks.append(chunk)
        else:
            for i in range(0, len(data_rows), TABLE_GROUP_ROWS):
                group = data_rows[i : i + TABLE_GROUP_ROWS]
                chunk = make_chunk(group, include_header=True)
                if chunk:
                    chunks.append(chunk)

        return chunks
