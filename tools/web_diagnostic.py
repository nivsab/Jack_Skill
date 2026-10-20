"""
tools/web_diagnostic.py — חיפוש טכני ברשת לתמיכה בתשובות RAG.

משמש לשאלות אבחון/עומק בלבד (לא מחירים, לא סרטונים).
DDG reserved: prices → parts.py, videos → youtube.py.

מחפש ב-DDG ומחזיר snippets טכניים — Claude מחליט אם הם מוסיפים מידע
שלא קיים בספר הרכב (RAG).

CLI: python tools/web_diagnostic.py "<make>" "<model>" <year> "<query>"
פלט: JSON ל-stdout
"""
import asyncio
import json
import re
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

_executor = ThreadPoolExecutor(max_workers=2)
_DDG_TIMEOUT = 8.0

_SKIP_DOMAINS = [
    # וידאו ומחירים (עוברים דרך youtube.py / parts.py)
    "youtube.com", "youtu.be",
    "aliexpress.com", "amazon.", "ebay.", "partclick.co.il",
    # מדיה חברתית
    "yad2.co.il", "facebook.com", "instagram.com", "twitter.com", "tiktok.com",
    # מכירות ומפרטים — לא תוכן אבחוני
    "avito.ru", "auto.ru/cars", "drom.ru", "avto.ru",
    "110km.ru", "autodata.ru", "cars.ru/catalog",
    "onliner.by", "av.by", "car.gr",
]

_DIAGNOSTIC_TERMS = {
    # אנגלית
    "problem", "fault", "issue", "repair", "fix", "diagnosis", "warning",
    "light", "error", "code", "trouble", "symptom", "failure", "malfunction",
    "check engine", "obd", "tsb", "recall", "cause",
    # עברית
    "בעיה", "תקלה", "תיקון", "אבחון", "שגיאה", "נורה", "כשל",
}

_HEB_RE = re.compile(r'[א-ת]')

# מיפוי מונחי אבחון עברי → אנגלי לבניית שאילתות DDG
_HEB_TO_EN: list[tuple[str, str]] = [
    ("נורת מנוע", "check engine light"),
    ("נורת בלמים", "brake warning light"),
    ("נורת שמן", "oil warning light"),
    ("נורת מצבר", "battery warning light"),
    ("נורת טמפרטורה", "temperature warning light"),
    ("נורת לחץ צמיגים", "tire pressure warning light"),
    ("נורת tpms", "tpms warning light"),
    ("נורה", "warning light"),
    ("מנוע מתחמם", "engine overheating"),
    ("לא מתניע", "won't start"),
    ("לא עולה", "won't start"),
    ("קשה להתניע", "hard to start"),
    ("רעש חריקה", "squeaking noise"),
    ("רעש נקישה", "knocking noise"),
    ("חריקה בבלמים", "brake squeal"),
    ("בלמים רכים", "soft brakes"),
    ("דלק גבוה", "high fuel consumption"),
    ("תיבת הילוכים", "transmission problem"),
    ("מצמד", "clutch problem"),
    ("היגוי כבד", "heavy steering"),
    ("רטט בהגה", "steering vibration"),
    ("מנוע", "engine"),
    ("בלמים", "brakes"),
    ("שמן", "oil"),
    ("קירור", "cooling"),
    ("רטט", "vibration"),
    ("רעש", "noise"),
    ("תקלה", "problem"),
    ("נורה", "warning light"),
    ("מצבר", "battery"),
]


def _has_hebrew(text: str) -> bool:
    return bool(_HEB_RE.search(text))


def _heb_to_english(query: str) -> str:
    """ממיר שאילתה עברית לאנגלית לצורך חיפוש DDG."""
    result = query.lower()
    for he, en in _HEB_TO_EN:
        result = result.replace(he, en)
    # ניקוי תווים עבריים שנשארו
    result = re.sub(r'[א-ת]+', '', result).strip()
    return result or "common problem diagnosis"


def _gen_range(year: int) -> str:
    """מחזיר טווח שנים קירוב לדור הרכב — מצמצם תוצאות לא-רלוונטיות ב-DDG."""
    start = year - 3
    end   = year + 2
    return f"{start}-{end}"


def _build_queries(make: str, model: str, year: int, query: str) -> tuple[str, str]:
    """בונה שתי שאילתות אנגליות — DDG עובד הרבה יותר טוב באנגלית."""
    gen = _gen_range(year)
    vehicle = f"{make} {model} {gen}"  # e.g. "Kia Rio 2013-2018"
    en_query = _heb_to_english(query) if _has_hebrew(query) else query
    q1 = f"{vehicle} {en_query} common problem fix"
    q2 = f"{make} {model} {year} {en_query} forum owner diagnosis"
    return q1, q2


_YEAR_RE = re.compile(r'\b(19|20)\d{2}\b')
_YEAR_TOLERANCE = 4  # מרחק מקסימלי בשנים


def _is_technical(result: dict) -> bool:
    href = result.get("href", "").lower()
    return not any(skip in href for skip in _SKIP_DOMAINS)


def _is_year_relevant(result: dict, target_year: int) -> bool:
    """
    אם הטקסט מציין שנה ספציפית — היא חייבת להיות בטווח ±TOLERANCE משנת הרכב.
    אם אין שנה — נניח שהמידע כללי ונשמור את התוצאה.
    """
    text = result.get("title", "") + " " + result.get("body", "")
    years = [int(y) for y in _YEAR_RE.findall(text)]
    if not years:
        return True
    return any(abs(y - target_year) <= _YEAR_TOLERANCE for y in years)


def _is_relevant(result: dict, make: str, model: str) -> bool:
    """תוצאה תקפה אם: (א) מזכירה את הרכב, (ב) מכילה תוכן אבחוני."""
    text = (result.get("title", "") + " " + result.get("body", "")).lower()
    mentions_car = make.lower() in text or model.lower() in text
    is_diagnostic = any(term in text for term in _DIAGNOSTIC_TERMS)
    return mentions_car and is_diagnostic


def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    try:
        with DDGS(timeout=5) as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
        return [r for r in raw if _is_technical(r)][:5]
    except Exception:
        return []


async def _search_async(query: str) -> list[dict]:
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_executor, lambda: _ddg_search(query)),
            timeout=_DDG_TIMEOUT,
        )
    except Exception:
        return []


def search_diagnostic(make: str, model: str, year: int, query: str) -> dict:
    """
    מחפש מידע טכני/אבחוני ברשת — שתי שאילתות אנגליות במקביל.

    מחזיר dict עם:
      - found: bool
      - results: רשימת {title, snippet, url}
    """
    q1, q2 = _build_queries(make, model, year, query)

    async def _run():
        return await asyncio.gather(
            _search_async(q1),
            _search_async(q2),
        )

    r1, r2 = asyncio.run(_run())

    seen_urls: set[str] = set()
    merged: list[dict] = []
    for r in (r1 + r2):
        url = r.get("href", "")
        if not url or url in seen_urls:
            continue
        if not _is_relevant(r, make, model):
            continue
        if not _is_year_relevant(r, year):
            continue
        seen_urls.add(url)
        merged.append({
            "title":   r.get("title", ""),
            "snippet": r.get("body", "")[:300],
            "url":     url,
        })
        if len(merged) >= 4:
            break

    if merged:
        return {"found": True, "results": merged}
    return {"found": False, "results": [], "reason": "לא נמצאו מקורות טכניים רלוונטיים"}


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        if len(sys.argv) < 5:
            print(json.dumps({"found": False, "error": "usage: web_diagnostic.py <make> <model> <year> <query>"}))
            sys.exit(0)

        make, model, year_str, query = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
        try:
            year = int(year_str)
        except ValueError:
            year = 0

        result = search_diagnostic(make, model, year, query)
        print(json.dumps(result, ensure_ascii=False))

    except Exception as exc:
        print(json.dumps({"found": False, "error": str(exc)}))
