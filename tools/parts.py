"""
כלי חיפוש מחירי חלפים — ישראל, אמזון ואליאקספרס.

מחפש דרך DuckDuckGo ומחזיר snippets גולמיים — Claude מחלץ מחירים.
שלושת החיפושים רצים במקביל (asyncio + ThreadPoolExecutor).
כל חיפוש מוגבל ל-8 שניות — timeout → ריק, לא קריסה.

CLI: python tools/parts.py <make> <model> <year> <message>
פלט: JSON ל-stdout
"""
import asyncio
import json
import os
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
warnings.filterwarnings("ignore")

# הוסף project root ל-path כדי שהייבוא יעבוד גם ב-CLI
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from state import VehicleInfo

# ─── קטלוג כלים ───────────────────────────────────────────────────────────────

_CATALOG_PATH = Path(__file__).parent / "tools_catalog.json"
_TOOLS_CATALOG: dict = {}

try:
    with open(_CATALOG_PATH, encoding="utf-8") as _f:
        _TOOLS_CATALOG = json.load(_f)
except Exception:
    pass


# ─── נתוני חלפים לפי פעולה ─────────────────────────────────────────────────────

_OPERATION_PARTS: dict[str, dict] = {
    "oil_change":            {"he": "מסנן שמן",       "en": "oil filter",    "critical": True},
    "brake_pad_replacement": {"he": "רפידות בלמים",    "en": "brake pads",    "critical": True},
    "air_filter":            {"he": "מסנן אוויר",      "en": "air filter",    "critical": False},
    "spark_plug":            {"he": "נרות הצתה",        "en": "spark plugs",   "critical": True},
    "tire_change":           {"he": "צמיגים",           "en": "tires",         "critical": True},
    "battery":               {"he": "מצבר רכב",         "en": "car battery",   "critical": True},
    "wiper":                 {"he": "מגבים",             "en": "wiper blades",  "critical": False},
}

_KEYWORD_TO_OPERATION: list[tuple[tuple[str, ...], str]] = [
    (("שמן", "oil", "מסנן שמן", "oil filter", "פקק שמן"), "oil_change"),
    (("בלמים", "רפידות", "brake", "דיסק"),                 "brake_pad_replacement"),
    (("מסנן אוויר", "air filter"),                          "air_filter"),
    (("נרות", "spark plug", "הצתה"),                        "spark_plug"),
    (("גלגל", "צמיג", "wheel", "tire"),                     "tire_change"),
    (("סוללה", "מצבר", "battery"),                          "battery"),
    (("מגב", "מגבים", "wiper"),                             "wiper"),
]

# ─── רגולציה ישראלית לפי פעולה ────────────────────────────────────────────────
# requires_mot: חייב אישור משרד התחבורה / תקן ישראלי
# customs_risk: low / medium / high — סיכון לעיכוב במכס

_ISRAEL_REGULATION: dict[str, dict] = {
    "brake_pad_replacement": {
        "requires_mot": True,
        "mot_note": "רפידות בלמים הן חלק בטיחות מפוקח — חייבות תקן ECE R90 ואישור משרד התחבורה. חלפים ללא תקן עלולים לפסול את הרכב בטסט.",
        "customs_risk": "high",
        "customs_note": "חלפי בלמים מאליאקספרס עלולים להיתקע במכס 3-6 שבועות ולהגיע לבדיקת מעבדה. אין ערובה לשחרור.",
    },
    "tire_change": {
        "requires_mot": True,
        "mot_note": "צמיגים חייבים תקן ECE R30 ורישום במשרד התחבורה. ייבוא מקביל עלול לפסול ביטוח ולגרום כשל בטסט.",
        "customs_risk": "high",
        "customs_note": "צמיגים מיובאים ישירות ממוסכים בחו\"ל — עיכוב מכס רגיל הוא 4-8 שבועות.",
    },
    "battery": {
        "requires_mot": False,
        "mot_note": "",
        "customs_risk": "medium",
        "customs_note": "מצברי ליתיום (EV/היברידי) מוגדרים כחומר מסוכן ועלולים להיחסם בשחרור מהמכס.",
    },
    "spark_plug": {
        "requires_mot": False,
        "mot_note": "",
        "customs_risk": "low",
        "customs_note": "",
    },
    "oil_change": {
        "requires_mot": False,
        "mot_note": "",
        "customs_risk": "low",
        "customs_note": "",
    },
    "air_filter": {
        "requires_mot": False,
        "mot_note": "",
        "customs_risk": "low",
        "customs_note": "",
    },
    "wiper": {
        "requires_mot": False,
        "mot_note": "",
        "customs_risk": "low",
        "customs_note": "",
    },
}

# ─── כלים נדרשים לפי פעולה ────────────────────────────────────────────────────
# critical=True → ללא הכלי הזה לא ניתן לבצע בבטחה

_TOOLS_REQUIRED: dict[str, list[dict]] = {
    "oil_change": [
        {"name": "מד מומנט",           "name_en": "torque wrench",      "critical": True},
        {"name": "מפתח מסנן שמן",       "name_en": "oil filter wrench",  "critical": True},
        {"name": "קערת ניקוז",           "name_en": "drain pan",          "critical": True},
        {"name": "מגבות / סמרטוטים",    "name_en": "rags",               "critical": False},
        {"name": "כפפות גומי",           "name_en": "gloves",             "critical": False},
        {"name": "גומי/אטם חדש לפקק",   "name_en": "drain plug washer",  "critical": False},
    ],
    "brake_pad_replacement": [
        {"name": "ג'ק רכב + מעמד בטיחות", "name_en": "jack + jack stands",    "critical": True},
        {"name": "מפתח גלגל",              "name_en": "lug wrench",            "critical": True},
        {"name": "מד מומנט",               "name_en": "torque wrench",         "critical": True},
        {"name": "לחץ קליפר (C-clamp)",    "name_en": "C-clamp / piston tool", "critical": True},
        {"name": "ברגים מפתח שקע",         "name_en": "socket set",            "critical": True},
        {"name": "גריז קרמי לרפידות",      "name_en": "brake grease",          "critical": False},
    ],
    "spark_plug": [
        {"name": "שקע נרות הצתה",         "name_en": "spark plug socket",   "critical": True},
        {"name": "מד מומנט",               "name_en": "torque wrench",       "critical": True},
        {"name": "מד פתח (gap gauge)",     "name_en": "feeler gauge",        "critical": True},
        {"name": "אורך הארכה לשקע",        "name_en": "extension bar",       "critical": False},
    ],
    "air_filter": [
        {"name": "מברג שטוח / פיליפס",    "name_en": "screwdriver",         "critical": True},
        {"name": "קליפסים / כלי פתיחה",   "name_en": "trim removal tool",   "critical": False},
    ],
    "tire_change": [
        {"name": "ג'ק רכב",                "name_en": "car jack",            "critical": True},
        {"name": "מפתח גלגל",              "name_en": "lug wrench",          "critical": True},
        {"name": "מד מומנט",               "name_en": "torque wrench",       "critical": True},
        {"name": "מד לחץ צמיגים",         "name_en": "tire pressure gauge", "critical": True},
        {"name": "טריז גלגל",              "name_en": "wheel chock",         "critical": False},
    ],
    "battery": [
        {"name": "מפתח ברגים 10mm",        "name_en": "10mm wrench",         "critical": True},
        {"name": "כפפות גומי",             "name_en": "rubber gloves",       "critical": True},
        {"name": "מולטימטר (בדיקה)",       "name_en": "multimeter",          "critical": False},
    ],
    "wiper": [
        {"name": "ידיים בלבד (ללא כלים)", "name_en": "no tools needed",     "critical": False},
    ],
}


# ─── פונקציות עזר ─────────────────────────────────────────────────────────────

_executor = ThreadPoolExecutor(max_workers=3)
_DDG_TIMEOUT = 8.0  # שניות — timeout per search


def _ddg_search(query: str, max_results: int = 4) -> list[dict]:
    try:
        with DDGS(timeout=5) as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception:
        return []


async def _ddg_search_async(query: str, max_results: int = 4) -> list[dict]:
    """מריץ חיפוש DDG ב-thread נפרד עם timeout. מחזיר רשימה ריקה בכשל."""
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_executor, lambda: _ddg_search(query, max_results)),
            timeout=_DDG_TIMEOUT,
        )
    except Exception:
        return []


async def _fetch_all_prices(israel_q: str, amazon_q: str, aliex_q: str) -> tuple[list, list, list]:
    """שלושה חיפושים במקביל — כישלון חלקי לא משפיע על השאר."""
    israel, amazon, aliex = await asyncio.gather(
        _ddg_search_async(israel_q),
        _ddg_search_async(amazon_q, max_results=3),
        _ddg_search_async(aliex_q),
    )
    return israel, amazon, aliex


def _snippets_to_text(snippets: list[dict]) -> str:
    lines = []
    for i, s in enumerate(snippets):
        body = s.get("body", "").strip()
        href = s.get("href", "")
        if body:
            lines.append(f"[{i+1}] {body}")
        if href:
            lines.append(f"    🔗 {href}")
    return "\n".join(lines) or "לא נמצאו תוצאות"


def _build_recommendation(prices: dict, is_critical: bool) -> tuple[str, str]:
    """
    בונה המלצת קנייה לפי מחירים ורמת קריטיות.
    מחזיר: (recommendation_text, emoji)
    """
    il_min = prices.get("israel_min")
    ax_min = prices.get("aliexpress_min")

    if is_critical:
        return "ישראל (חלף קריטי — אמינות על פני מחיר)", "⚠️"

    if il_min and ax_min:
        savings_pct = round((1 - ax_min / il_min) * 100)
        if savings_pct >= 40:
            return f"אליאקספרס (חיסכון ~{savings_pct}%)", "✅"

    return "ישראל (הפרש מחיר לא מצדיק סיכון)", "🔵"


def _detect_operation(text: str) -> Optional[str]:
    text_lower = text.lower()
    for keywords, operation in _KEYWORD_TO_OPERATION:
        if any(kw in text_lower for kw in keywords):
            return operation
    return None


# ─── פונקציות ציבוריות ────────────────────────────────────────────────────────

def get_regulation_warning(operation: str) -> Optional[dict]:
    """
    מחזיר אזהרת רגולציה ישראלית לפעולה נתונה — או None אם אין סיכון.
    """
    reg = _ISRAEL_REGULATION.get(operation)
    if not reg:
        return None
    if not reg["requires_mot"] and reg["customs_risk"] == "low":
        return None
    return reg


def get_tools_for_operation(operation: str) -> list[dict]:
    """
    מחזיר רשימת כלים נדרשת (hardcoded) לפי פעולה.
    מחזיר רשימה ריקה אם הפעולה לא ידועה.
    """
    return _TOOLS_REQUIRED.get(operation, [])


def get_tool_image_query(tool_name_en: str) -> str:
    """מחזיר DDG image query לכלי — מהקטלוג או query גנרי."""
    for key, entry in _TOOLS_CATALOG.items():
        if entry.get("name_en", "").lower() == tool_name_en.lower():
            return entry.get("ddg_image_query", f"{tool_name_en} tool photo")
    return f"{tool_name_en} tool photo"


def search_parts_price(vehicle: VehicleInfo, operation: str) -> Optional[dict]:
    """
    מחפש מחירי חלפים ב-DDG (ישראל, אמזון, אליאקספרס) ומחזיר snippets גולמיים.
    Claude יחלץ טווחי מחירים מה-snippets.
    """
    part_info = _OPERATION_PARTS.get(operation)
    if not part_info:
        return None

    make  = vehicle.get("manufacturer", "")
    model = vehicle.get("model", "")
    year  = vehicle.get("year", "")

    israel_q = f"{part_info['he']} {make} {model} {year} PartClick מחיר"
    amazon_q = f"site:amazon.co.il {part_info['he']} {make} {model}"
    aliex_q  = f"{part_info['en']} {make} {model} {year} aliexpress"

    israel_snips, amazon_snips, aliex_snips = asyncio.run(
        _fetch_all_prices(israel_q, amazon_q, aliex_q)
    )

    if not israel_snips and not amazon_snips and not aliex_snips:
        return None

    rec, emoji = _build_recommendation({}, part_info["critical"])
    regulation = get_regulation_warning(operation)
    tools      = get_tools_for_operation(operation)

    return {
        "part_he":             part_info["he"],
        "part_en":             part_info["en"],
        "critical":            part_info["critical"],
        "recommendation":      rec,
        "emoji":               emoji,
        "israel_snippets":     _snippets_to_text(israel_snips),
        "amazon_il_snippets":  _snippets_to_text(amazon_snips),
        "aliexpress_snippets": _snippets_to_text(aliex_snips),
        "regulation":          regulation,
        "tools_required":      tools,
    }


def get_parts_context(vehicle: Optional[VehicleInfo], last_message: str) -> str:
    """מחזיר בלוק טקסט מוכן להזרקה — לשימוש תוכניתי בלבד."""
    if not vehicle:
        return ""
    operation = _detect_operation(last_message)
    if not operation:
        return ""
    result = search_parts_price(vehicle, operation)
    if not result:
        return ""

    lines = [
        f"=== מחירי חלפים — {result['part_he']} ===",
        f"💡 המלצה: {result['recommendation']}",
        "תוצאות ישראל (PartClick):",
        result["israel_snippets"],
        "תוצאות אמזון ישראל:",
        result.get("amazon_il_snippets", "לא נמצאו תוצאות"),
        "תוצאות אליאקספרס:",
        result["aliexpress_snippets"],
    ]
    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _cli_main():
    """CLI: python tools/parts.py <make> <model> <year> <message>"""
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        if len(sys.argv) < 5:
            print(json.dumps({"found": False, "error": "usage: parts.py <make> <model> <year> <message>"}))
            return

        make, model, year_str, message = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
        try:
            year = int(year_str)
        except ValueError:
            year = 0

        vehicle: VehicleInfo = {"manufacturer": make, "model": model, "year": year}
        operation = _detect_operation(message)

        if not operation:
            print(json.dumps({"found": False, "reason": "no relevant keywords"}))
            return

        result = search_parts_price(vehicle, operation)
        if result:
            print(json.dumps({"found": True, **result}, ensure_ascii=False))
        else:
            print(json.dumps({"found": False, "reason": "no search results"}))

    except Exception as exc:
        print(json.dumps({"found": False, "error": str(exc)}))


if __name__ == "__main__":
    _cli_main()
