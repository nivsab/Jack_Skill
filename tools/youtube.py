"""
כלי חיפוש סרטוני YouTube — מוצא הדרכות DIY לפי רכב ופעולה.

שני מנגנונים:
1. YouTube Data API v3  (אם YOUTUBE_API_KEY מוגדר)
2. DuckDuckGo video     (fallback, ללא API key)

חיפוש בשתי שפות: עברית קודם → אנגלית אם לא נמצא.
תוצאות נשמרות ב-Supabase youtube_cache.

CLI: python tools/youtube.py <make> <model> <year> <message>
פלט: JSON ל-stdout
"""
import os
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from state import VehicleInfo
from rag import cache as db_cache  # שימוש ב-Supabase client של ה-cache הקיים


# ─── מיפוי מילות מפתח → פעולה ─────────────────────────────────────────────────

_KEYWORD_TO_OPERATION: list[tuple[tuple[str, ...], str]] = [
    (("שמן", "oil", "מסנן שמן", "oil filter", "החלפת שמן", "פקק שמן"), "oil_change"),
    (("בלמים", "רפידות", "brake", "דיסק", "brake pad"), "brake_pad_replacement"),
    (("מסנן אוויר", "air filter", "פילטר אוויר", "מסנן מנוע"), "air_filter"),
    (("מסנן קבינה", "מסנן מזגן", "cabin filter", "pollen filter", "מסנן אוויר פנים"), "cabin_filter"),
    (("נרות", "spark plug", "נר הצתה", "הצתה"), "spark_plug"),
    (("גלגל", "צמיג", "wheel", "tire", "גלגלים"), "tire_change"),
    (("סוללה", "מצבר", "battery"), "battery"),
    (("מגב", "מגבים", "wiper", "wipers"), "wiper"),
    (("נורה", "נורות", "bulb", "headlight", "פנס", "רוורס", "backup light",
      "תאורה", "ערפל", "פלאש", "בלם", "brake light", "fog light"), "bulb"),
    (("מסך", "מולטימדיה", "רדיו", "סטריאו", "stereo",
      "head unit", "android", "car screen", "אנדרואיד"), "stereo"),
    (("דאשקאם", "dashcam", "dash cam", "מצלמת דרך"), "dashcam"),
    (("מצלמת רוורס", "מצלמה אחורית", "backup camera", "reverse camera"), "reverse_camera"),
]

# שאילתות חיפוש לכל פעולה — עברית ואנגלית
_OPERATION_QUERIES: dict[str, dict[str, str]] = {
    "oil_change":             {"he": "החלפת שמן מנוע",             "en": "oil change"},
    "brake_pad_replacement":  {"he": "החלפת רפידות בלמים",          "en": "brake pad replacement"},
    "air_filter":             {"he": "החלפת מסנן אוויר",            "en": "air filter change"},
    "cabin_filter":           {"he": "החלפת מסנן קבינה",            "en": "cabin filter change"},
    "spark_plug":             {"he": "החלפת נרות הצתה",             "en": "spark plug replace"},
    "tire_change":            {"he": "החלפת גלגל עצירת חירום",     "en": "tire change"},
    "battery":                {"he": "החלפת מצבר רכב",              "en": "battery replace"},
    "wiper":                  {"he": "החלפת מגבים",                 "en": "wiper change"},
    "bulb":                   {"he": "החלפת נורה",                  "en": "bulb replacement"},
    "stereo":                 {"he": "התקנת מסך מולטימדיה רכב",    "en": "car stereo install"},
    "dashcam":                {"he": "התקנת מצלמת דרך רכב",        "en": "dashcam install"},
    "reverse_camera":         {"he": "התקנת מצלמת רוורס",          "en": "backup camera install"},
}

_YT_KEY = os.getenv("YOUTUBE_API_KEY", "")

# מילות מפתח לבדיקת רלוונטיות הכותרת — אם אף אחת לא נמצאת, הסרטון לא רלוונטי לפעולה
_OPERATION_TITLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "oil_change":            ("oil", "שמן", "filter", "מסנן", "lube"),
    "brake_pad_replacement": ("brake", "pad", "בלם", "רפידה", "disc", "rotor"),
    "air_filter":            ("air filter", "airfilter", "מסנן אוויר"),
    "cabin_filter":          ("cabin", "pollen", "cabin filter", "cabin air", "מסנן קבינה"),
    "spark_plug":            ("spark", "plug", "נר", "ignition", "הצתה"),
    "tire_change":           ("tire", "wheel", "tyre", "צמיג", "גלגל"),
    "battery":               ("battery", "מצבר", "סוללה"),
    "wiper":                 ("wiper", "blade", "מגב", "windshield"),
    "bulb":                  ("bulb", "light", "lamp", "נורה", "תאורה", "פנס",
                              "reverse", "backup", "tail", "brake", "fog",
                              "headlight", "indicator", "signal", "turn"),
}

# מיפוי מילות מפתח עבריות לשם נורה ספציפי באנגלית (לשאילתת YouTube)
_BULB_SUBTYPE: list[tuple[tuple[str, ...], str]] = [
    (("רוורס", "גיבוי", "backup", "reverse"), "reverse"),
    (("בלם", "stop light", "brake light", "brake"), "brake light"),
    (("ערפל", "fog"), "fog light"),
    (("פנס", "הדלקה", "headlight", "קדמי", "קדמית"), "headlight"),
    (("אחורי", "זנב", "tail", "rear"), "tail light"),
    (("פלאש", "signal", "בלינקר", "רצועה"), "turn signal"),
    (("נורה", "bulb"), "bulb"),
]

# מילות מפתח בכותרת שמאמתות שהסרטון אכן עוסק בסוג הנורה הנכון
_BULB_SUBTYPE_TITLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "reverse":      ("reverse", "backup", "back-up", "backing", "רוורס"),
    "brake light":  ("brake light", "stop light", "tail light", "brake lamp", "בלם"),
    "fog light":    ("fog", "ערפל"),
    "headlight":    ("headlight", "head light", "low beam", "high beam", "פנס"),
    "tail light":   ("tail light", "taillight", "rear light", "אחורי"),
    "turn signal":  ("turn signal", "indicator", "blinker", "פלאש"),
}


def _extract_bulb_subtype(text: str) -> str:
    """מחלץ סוג נורה ספציפי מהטקסט — מחזיר מחרוזת אנגלית לחיפוש."""
    t = text.lower()
    for keywords, en_name in _BULB_SUBTYPE:
        if any(kw in t for kw in keywords):
            return en_name
    return "bulb"


# ─── כלי שליפה ────────────────────────────────────────────────────────────────

def _cache_table() -> str:
    """שם טבלת ה-cache ב-Supabase."""
    return "youtube_cache"


def _get_from_supabase(vehicle: VehicleInfo, operation: str, lang: str) -> Optional[dict]:
    """
    בודק אם יש סרטון שמור ב-Supabase עבור רכב+פעולה+שפה.
    מחזיר dict עם video_url, video_title, channel_name, notes — או None.
    """
    try:
        client = db_cache._get_client()
        result = (
            client.table(_cache_table())
            .select("video_url,video_title,channel_name,notes")
            .ilike("make", vehicle.get("manufacturer", ""))
            .ilike("model", vehicle.get("model", ""))
            .eq("year", vehicle.get("year", 0))
            .eq("operation", operation)
            .eq("language", lang)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception:
        return None


def _save_to_supabase(vehicle: VehicleInfo, operation: str, lang: str, video: dict) -> None:
    """
    שומר תוצאת סרטון ב-Supabase.
    upsert — לא יוצר כפילויות אם כבר קיים.
    """
    try:
        client = db_cache._get_client()
        client.table(_cache_table()).upsert(
            {
                "make":         vehicle.get("manufacturer", ""),
                "model":        vehicle.get("model", ""),
                "year":         vehicle.get("year", 0),
                "operation":    operation,
                "language":     lang,
                "video_id":     video.get("video_id", ""),
                "video_title":  video.get("video_title", ""),
                "video_url":    video.get("video_url", ""),
                "channel_name": video.get("channel_name", ""),
                "notes":        video.get("notes", ""),
            },
            on_conflict="make,model,year,operation,language",
        ).execute()
    except Exception:
        pass


def _extract_video_id(url: str) -> str:
    """
    מחלץ video ID מ-YouTube embed URL או URL רגיל.
    לדוגמה: 'https://www.youtube.com/embed/dQw4w9WgXcQ' → 'dQw4w9WgXcQ'
    """
    patterns = [
        r"embed/([A-Za-z0-9_-]{11})",
        r"v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return ""


def _search_youtube_api(query: str) -> Optional[dict]:
    """
    מחפש ב-YouTube Data API v3 — משתמש בו אם YOUTUBE_API_KEY מוגדר.

    מחזיר dict עם video_id, video_title, channel_name — או None.
    מסנן סרטונים קצרים מאוד (shorts) ומעדיף תוצאות ביוטיוב בלבד.
    """
    if not _YT_KEY:
        return None
    try:
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", developerKey=_YT_KEY, cache_discovery=False)
        resp = (
            yt.search()
            .list(
                part="snippet",
                q=query,
                type="video",
                maxResults=5,
                videoDuration="medium",  # 4–20 דקות — הכי שימושי
            )
            .execute()
        )
        items = resp.get("items", [])
        if not items:
            return None
        item = items[0]
        vid_id = item["id"]["videoId"]
        return {
            "video_id":    vid_id,
            "video_title": item["snippet"]["title"],
            "video_url":   f"https://www.youtube.com/watch?v={vid_id}",
            "channel_name": item["snippet"]["channelTitle"],
            "notes":       "",
        }
    except Exception:
        return None


_TUTORIAL_KEYWORDS = (
    "replace", "replacement", "how to", "diy", "install", "change", "repair",
    "החלפת", "החלפה", "כיצד", "איך", "תיקון", "התקנה", "הוראות",
)
_NONTUTORIAL_KEYWORDS = (
    "review", "test drive", "overview", "comparison", "unboxing",
    "ביקורת", "טסט", "השוואה", "מבחן",
)

# פעולות שתלויות בצד ההגה — סרטון RHD (UK/JP/AU) לא מתאים לישראל (LHD)
_SIDE_SPECIFIC_OPERATIONS = {
    "bulb", "stereo", "wiper", "air_filter", "battery",
}

# מונחים שמסמנים RHD — יש להעניש אם המבצע side-specific
_RHD_KEYWORDS = ("rhd", "right hand drive", "uk spec", "jdm", "japan spec", "australia spec")
# מונחים שמסמנים LHD / שוק אירופי — ישראל = Euro spec
_LHD_BONUS_KEYWORDS = ("lhd", "left hand drive", "europe", "european")


def _year_score(title: str, target_year: int) -> int:
    """
    ניקוד לפי התאמת שנת הרכב לכותרת:
      +3 טווח שנים שמכסה את השנה (2012-2017 covers 2016)
      +2 שנה מדויקת בכותרת
      -2 שנה שגויה בבירור (הפרש > 3 שנים)
    """
    if not target_year:
        return 0
    # Range patterns: "2012-2017", "2012 to 2017", "2012–2017"
    for m in re.finditer(r'\b(20\d{2})\s*[-–to]+\s*(20\d{2})\b', title, re.IGNORECASE):
        start, end = int(m.group(1)), int(m.group(2))
        if start <= target_year <= end:
            return 3
        if abs(start - target_year) <= 2 or abs(end - target_year) <= 2:
            return 1
        return -1
    # Exact year
    years = [int(y) for y in re.findall(r'\b(20\d{2})\b', title)]
    if target_year in years:
        return 2
    if years and all(abs(y - target_year) > 3 for y in years):
        return -2
    return 0


def _tutorial_score(title: str, operation: str = "", subtype: Optional[str] = None, year: int = 0) -> int:
    """
    מחזיר ניקוד:
      +1 מילת הדרכה | -2 מילת ביקורת
      -3 RHD (UK/JDM) אם הפעולה תלוית-צד — ישראל LHD
      +1 LHD / Euro spec
      +2 לכל מילת מפתח של subtype נורה שמופיעה בכותרת
      ±  ניקוד שנה (year_score)
    """
    t = title.lower()
    score = sum(1 for kw in _TUTORIAL_KEYWORDS if kw in t)
    score -= sum(2 for kw in _NONTUTORIAL_KEYWORDS if kw in t)
    if operation in _SIDE_SPECIFIC_OPERATIONS:
        score -= sum(3 for kw in _RHD_KEYWORDS if kw in t)
        score += sum(1 for kw in _LHD_BONUS_KEYWORDS if kw in t)
    if subtype and subtype in _BULB_SUBTYPE_TITLE_KEYWORDS:
        score += sum(2 for kw in _BULB_SUBTYPE_TITLE_KEYWORDS[subtype] if kw in t)
    score += _year_score(title, year)
    return score


def _is_relevant(title: str, operation: str, subtype: Optional[str] = None) -> bool:
    """מוודא שכותרת הסרטון רלוונטית לפעולה ולסוג המשנה (אם צוין)."""
    kws = _OPERATION_TITLE_KEYWORDS.get(operation)
    if not kws:
        return True
    t = title.lower()
    if not any(kw in t for kw in kws):
        return False
    # לנורות עם subtype ספציפי — חובה שכותרת תכיל מילת מפתח של אותו subtype
    if operation == "bulb" and subtype and subtype in _BULB_SUBTYPE_TITLE_KEYWORDS:
        subtype_kws = _BULB_SUBTYPE_TITLE_KEYWORDS[subtype]
        if not any(kw in t for kw in subtype_kws):
            return False
    return True


def _search_ddg_video(query: str, operation: str = "", subtype: Optional[str] = None, year: int = 0) -> Optional[dict]:
    """
    מחפש סרטוני YouTube דרך DuckDuckGo — fallback כשאין YouTube API key.

    מסנן רק תוצאות מ-YouTube, מדרג לפי מילות הדרכה, מסנן לפי רלוונטיות לפעולה.
    """
    try:
        with DDGS(timeout=5) as ddgs:
            results = list(ddgs.videos(query, max_results=10))

        candidates = []
        for r in results:
            embed = r.get("embed_url", "")
            publisher = r.get("publisher", "").lower()
            if "youtube" not in embed and "youtube" not in publisher:
                continue
            vid_id = _extract_video_id(embed)
            if not vid_id:
                continue
            title = r.get("title", "")
            if not _is_relevant(title, operation, subtype):
                continue
            candidates.append((
                _tutorial_score(title, operation, subtype, year),
                {
                    "video_id":    vid_id,
                    "video_title": title,
                    "video_url":   f"https://www.youtube.com/watch?v={vid_id}",
                    "channel_name": r.get("publisher", ""),
                    "notes":       "",
                }
            ))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        # אל תחזיר סרטון שמדורג שלילית — כנראה ביקורת/השוואה, לא הדרכה
        best_score, best_video = candidates[0]
        if best_score < 0:
            return None
        return best_video
    except Exception:
        return None


def _search_video(query: str, operation: str = "", subtype: Optional[str] = None, year: int = 0) -> Optional[dict]:
    """
    מחפש סרטון — YouTube API אם זמין, DuckDuckGo אחרת.
    """
    return _search_youtube_api(query) or _search_ddg_video(query, operation, subtype, year)


def find_tutorial(vehicle: VehicleInfo, operation: str, raw_message: str = "") -> Optional[dict]:
    """
    מוצא סרטון הדרכה לפעולה ספציפית — cache → חיפוש עברית → חיפוש אנגלית.

    raw_message: הודעת המשתמש המקורית — משמשת לבניית שאילתה מדויקת יותר.
    """
    queries = _OPERATION_QUERIES.get(operation)
    if not queries:
        return None

    make  = vehicle.get("manufacturer", "")
    model = vehicle.get("model", "")
    year  = vehicle.get("year", "")

    # בנה שאילתות — עברית ואנגלית
    he_term = raw_message.strip() if raw_message else queries["he"]
    en_base = queries["en"]
    year_int = int(year) if str(year).isdigit() else 0

    # לנורות — שלוף סוג ספציפי (רוורס / פנס / בלם) לשיפור שאילתה ו-cache key
    if operation == "bulb":
        subtype = _extract_bulb_subtype(raw_message) if raw_message else "bulb"
        cache_operation = f"bulb_{subtype.replace(' ', '_')}"  # e.g. "bulb_reverse"
        # קצר ופשוט — DDG Video נכשל עם שאילתות ארוכות, מרכאות ו-LHD
        en_specific  = f'{year} {make} {model} {subtype} bulb replacement'
        en_fallback  = f'{make} {model} {subtype} bulb replacement'
        en_fallback2 = f'{make} {model} {subtype} light replace'
    else:
        subtype = None
        cache_operation = operation
        en_specific  = f'{year} {make} {model} {en_base}'
        en_fallback  = f'{make} {model} {en_base}'
        en_fallback2 = None

    # לכל שפה: שאילתה ספציפית → fallback → fallback2
    # עברית קודמת — תוצאות ישראליות טבעיות
    search_pairs = [
        ("he", f"{year} {make} {model} {he_term}", f"{make} {model} {he_term}"),
        ("en", en_specific, en_fallback),
    ]

    bulb_subtype = subtype if operation == "bulb" else None

    for lang, specific_q, fallback_q in search_pairs:
        cached = _get_from_supabase(vehicle, cache_operation, lang)
        if cached:
            # Validate cached title — rejects stale/wrong entries (e.g. headlight cached for reverse)
            if _is_relevant(cached.get("video_title", ""), operation, bulb_subtype):
                return cached

        result = (_search_video(specific_q, operation, bulb_subtype, year_int)
                  or _search_video(fallback_q, operation, bulb_subtype, year_int)
                  or (en_fallback2 and lang == "en" and _search_video(en_fallback2, operation, bulb_subtype, year_int)))
        if result:
            _save_to_supabase(vehicle, cache_operation, lang, result)
            return result

    return None


# ─── פונקציה ציבורית לשימוש בנודים ───────────────────────────────────────────

def _detect_operation(text: str) -> Optional[str]:
    """
    מזהה פעולה לפי מילות מפתח בטקסט — מחזיר שם פעולה או None.
    """
    text_lower = text.lower()
    for keywords, operation in _KEYWORD_TO_OPERATION:
        if any(kw in text_lower for kw in keywords):
            return operation
    return None


def _detect_operation_yt(text: str) -> Optional[str]:
    text_lower = text.lower()
    for keywords, operation in _KEYWORD_TO_OPERATION:
        if any(kw in text_lower for kw in keywords):
            return operation
    return None


def get_tutorial_context(vehicle: Optional[VehicleInfo], last_message: str) -> str:
    """מחזיר בלוק טקסט מוכן להזרקה — לשימוש תוכניתי בלבד."""
    if not vehicle:
        return ""
    operation = _detect_operation_yt(last_message)
    if not operation:
        return ""

    result = find_tutorial(vehicle, operation)
    if not result:
        return ""

    lines = [
        "=== סרטון הדרכה ===",
        f"🎬 {result.get('video_title', '')}",
        f"🔗 {result.get('video_url', '')}",
    ]
    if result.get("channel_name"):
        lines.append(f"📺 {result['channel_name']}")
    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────────────

import json
import sys
import warnings
warnings.filterwarnings("ignore")


def _cli_main():
    """CLI: python tools/youtube.py <make> <model> <year> <message>"""
    try:
        if len(sys.argv) < 5:
            print(json.dumps({"found": False, "error": "usage: youtube.py <make> <model> <year> <message>"}))
            return

        make, model, year_str, message = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
        try:
            year = int(year_str)
        except ValueError:
            year = 0

        from state import VehicleInfo as _VehicleInfo
        vehicle: _VehicleInfo = {"manufacturer": make, "model": model, "year": year}
        operation = _detect_operation_yt(message)

        if not operation:
            print(json.dumps({"found": False, "reason": "no relevant keywords"}))
            return

        result = find_tutorial(vehicle, operation, raw_message=message)
        if result:
            print(json.dumps({"found": True, **result}, ensure_ascii=False))
        else:
            print(json.dumps({"found": False, "reason": "no video found"}))

    except Exception as exc:
        print(json.dumps({"found": False, "error": str(exc)}))


if __name__ == "__main__":
    _cli_main()
