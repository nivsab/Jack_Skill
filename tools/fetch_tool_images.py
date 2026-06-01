"""
tools/fetch_tool_images.py — בניית manifest מתמונות כלים שנשמרו ידנית.

שים תמונות ב-data/tools/ בשם המפתח (למשל torque_wrench.jpg)
ואז הרץ סקריפט זה כדי לעדכן את data/tools/manifest.json.

שמות קבצים תקינים לכל כלי:
  torque_wrench        — מד מומנט
  oil_filter_wrench    — מפתח מסנן שמן
  drain_pan            — קערת ניקוז שמן
  rubber_gloves        — כפפות ניטריל
  spark_plug_socket    — שקע נרות הצתה
  feeler_gauge         — מד פתח
  screwdriver_philips  — מברג פיליפס
  wrench_10mm          — מפתח ברגים 10mm
  car_jack             — ג'ק רכב
  lug_wrench           — מפתח גלגל (צלב)

פורמטים נתמכים: .jpg .jpeg .png .webp

CLI:
  python tools/fetch_tool_images.py
"""
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = Path(__file__).parent.parent / "data" / "tools"
MANIFEST  = DATA_DIR / "manifest.json"
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

KNOWN_TOOLS = {
    "torque_wrench":       "מד מומנט",
    "oil_filter_wrench":   "מפתח מסנן שמן",
    "drain_pan":           "קערת ניקוז שמן",
    "rubber_gloves":       "כפפות ניטריל",
    "spark_plug_socket":   "שקע נרות הצתה",
    "feeler_gauge":        "מד פתח",
    "screwdriver_philips": "מברג פיליפס",
    "wrench_10mm":         "מפתח ברגים 10mm",
    "car_jack":            "ג'ק רכב",
    "lug_wrench":          "מפתח גלגל (צלב)",
}


def build_manifest() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {}
    found = []
    missing = []

    for key, name_he in KNOWN_TOOLS.items():
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            p = DATA_DIR / f"{key}{ext}"
            if p.exists() and p.stat().st_size > 1_000:
                manifest[key] = str(p)
                found.append(f"  ✅ {key} ({name_he})")
                break
        else:
            missing.append(f"  ❌ {key} ({name_he}) — חסר")

    for line in found:
        print(line)
    for line in missing:
        print(line)

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ {len(found)}/{len(KNOWN_TOOLS)} כלים במאגר.")
    print(f"📄 manifest נשמר: {MANIFEST}")

    if missing:
        print(f"\nכדי להוסיף כלי חסר — שמור קובץ תמונה ב:")
        print(f"  {DATA_DIR}\\<שם_כלי>.jpg")

    return manifest


if __name__ == "__main__":
    build_manifest()
