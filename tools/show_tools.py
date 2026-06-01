"""
tools/show_tools.py — רשימת כלים + נתיבי תמונה מקומיים לפי פעולה.

מחזיר JSON עם שם כלי, האם קריטי, ונתיב התמונה המקומית (אם קיימת).
ג'ק משתמש בנתיב כדי לקרוא ולהציג את התמונה דרך Read tool.

CLI: python tools/show_tools.py <operation>
פלט: JSON ל-stdout
"""
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

DATA_DIR = Path(__file__).parent.parent / "data" / "tools"
MANIFEST  = DATA_DIR / "manifest.json"


# ─── כלים לפי פעולת DIY ──────────────────────────────────────────────────────
# רק פעולות שמישהו עם ידע מועט יכול לבצע לבד.
# critical=True → ללא הכלי הזה אין לבצע את הפעולה.

_OPERATION_TOOLS: dict[str, list[dict]] = {
    "oil_change": [
        {"key": "torque_wrench",     "name_he": "מד מומנט",           "critical": True},
        {"key": "oil_filter_wrench", "name_he": "מפתח מסנן שמן",      "critical": True},
        {"key": "drain_pan",         "name_he": "קערת ניקוז שמן",      "critical": True},
        {"key": "rubber_gloves",     "name_he": "כפפות ניטריל",        "critical": False},
    ],
    "spark_plug": [
        {"key": "spark_plug_socket", "name_he": "שקע נרות הצתה",       "critical": True},
        {"key": "torque_wrench",     "name_he": "מד מומנט",           "critical": True},
        {"key": "feeler_gauge",      "name_he": "מד פתח",             "critical": True},
    ],
    "air_filter": [
        {"key": "screwdriver_philips","name_he": "מברג פיליפס",        "critical": False},
    ],
    "battery": [
        {"key": "wrench_10mm",       "name_he": "מפתח ברגים 10mm",    "critical": True},
        {"key": "rubber_gloves",     "name_he": "כפפות ניטריל",        "critical": True},
    ],
    "wiper": [
        # ידיים בלבד
    ],
    "headlight_bulb": [
        # ידיים בלבד (ברוב הרכבים)
    ],
    "flat_tire": [
        {"key": "car_jack",           "name_he": "ג'ק רכב",            "critical": True},
        {"key": "lug_wrench",         "name_he": "מפתח גלגל (צלב)",    "critical": True},
    ],
    "stereo": [
        {"key": "screwdriver_philips","name_he": "מברג פיליפס",        "critical": True},
        {"key": "screwdriver_philips","name_he": "כלי הוצאת פנלים (pry tool)", "critical": False},
    ],
    "dashcam": [
        # ידיים בלבד + קבל USB / fuse tap
    ],
    "reverse_camera": [
        {"key": "screwdriver_philips","name_he": "מברג פיליפס",        "critical": True},
    ],
}

# מיפוי מילות מפתח → פעולה (לזיהוי אוטומטי)
_KEYWORD_MAP: list[tuple[tuple[str, ...], str]] = [
    (("שמן", "oil", "מסנן שמן", "oil filter"), "oil_change"),
    (("נרות", "spark", "הצתה", "plug"),        "spark_plug"),
    (("מסנן אוויר", "air filter"),              "air_filter"),
    (("מצבר", "battery", "סוללה"),             "battery"),
    (("מגב", "מגבים", "wiper"),                "wiper"),
    (("נורה", "נורות", "bulb", "headlight"),   "headlight_bulb"),
    (("פנצ'ר", "גלגל פנוי", "flat", "צמיג"), "flat_tire"),
    (("מסך", "מולטימדיה", "רדיו", "סטריאו",
      "stereo", "head unit", "android", "car screen"), "stereo"),
    (("דאשקאם", "dashcam", "dash cam",
      "מצלמת דרך", "מצלמה קדמית"),             "dashcam"),
    (("מצלמת רוורס", "מצלמה אחורית",
      "backup camera", "reverse camera"),       "reverse_camera"),
]


def _load_manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _detect_operation(text: str) -> str | None:
    tl = text.lower()
    for kws, op in _KEYWORD_MAP:
        if any(kw in tl for kw in kws):
            return op
    return None


def get_tools(operation: str) -> list[dict]:
    """
    מחזיר רשימת כלים לפעולה עם נתיב תמונה מקומי.
    כל entry: {key, name_he, critical, image_path (str|null)}.
    """
    tools = _OPERATION_TOOLS.get(operation, [])
    manifest = _load_manifest()

    result = []
    for t in tools:
        image_path = manifest.get(t["key"])
        # בדוק שהקובץ עדיין קיים
        if image_path and not Path(image_path).exists():
            image_path = None
        result.append({
            "key":        t["key"],
            "name_he":    t["name_he"],
            "critical":   t["critical"],
            "image_path": image_path,
        })
    return result


def get_tools_for_message(message: str) -> list[dict]:
    """זיהוי אוטומטי של פעולה מתוך הודעה + החזרת כלים."""
    op = _detect_operation(message)
    if not op:
        return []
    return get_tools(op)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _cli():
    try:
        if len(sys.argv) < 2:
            print(json.dumps({"found": False, "error": "usage: show_tools.py <operation|message>"}))
            return

        arg = sys.argv[1]

        # נסה קודם כ-operation ישיר
        if arg in _OPERATION_TOOLS:
            tools = get_tools(arg)
        else:
            # זהה מתוך הודעה חופשית
            tools = get_tools_for_message(arg)

        if tools is not None and len(tools) == 0 and arg in _OPERATION_TOOLS:
            # פעולה ידועה, פשוט אין כלים (wiper/bulb)
            print(json.dumps({"found": True, "operation": arg, "tools": [], "note": "אין כלים נדרשים — ידיים בלבד"}))
            return

        if not tools:
            print(json.dumps({"found": False, "reason": "operation not detected or no tools"}))
            return

        op = _detect_operation(arg) or arg
        missing_images = [t["key"] for t in tools if not t["image_path"]]
        note = None
        if missing_images:
            note = f"תמונות חסרות — הרץ: python tools/fetch_tool_images.py"

        print(json.dumps({
            "found":     True,
            "operation": op,
            "tools":     tools,
            "note":      note,
        }, ensure_ascii=False))

    except Exception as exc:
        print(json.dumps({"found": False, "error": str(exc)}))


if __name__ == "__main__":
    _cli()
